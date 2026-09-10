import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api import provider
from app.auth import COOKIE_NAME, digest
from app.config import Settings
from app.errors import AppError
from app.main import create_app
from app.providers.base import Completion, ToolCall
from app.tools import permission_for
from app.vault import decrypt_key

BROWSER = {"Origin": "http://localhost:3000", "X-THRYV-Request": "1"}
KEY = "test-only-valid-key"
PASSWORD = "test-password-for-V1"


class Runtime:
    def __init__(self):
        self.calls = []

    async def verify(self, key):
        assert key.get_secret_value() == KEY

    async def plan(self, key, messages, tools):
        assert key.get_secret_value() == KEY
        self.calls.append(messages)
        message = messages[-1]["content"]
        if message.startswith("Open"):
            return Completion(
                "UNTRUSTED SUCCESS",
                tool_call=ToolCall("open_application", {"application": "chrome"}),
            )
        return Completion("Saved reply: " + message)


@pytest.fixture
def v1(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    settings = Settings(
        app_env="test",
        database_url=url,
        credential_encryption_key=Fernet.generate_key().decode(),
        _env_file=None,
    )
    app = create_app(settings)
    runtime = Runtime()
    app.dependency_overrides[provider] = lambda: runtime
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, tmp_path / "test.db", runtime, config


def signup(client, email="owner@example.com"):
    client.cookies.clear()
    response = client.post(
        "/api/auth/register", headers=BROWSER, json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    login(client, email)
    return client.cookies.get(COOKIE_NAME)


def login(client, email="owner@example.com"):
    response = client.post(
        "/api/auth/login", headers=BROWSER, data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 204, response.text
    return response


def use(client, token):
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, token)


def sql(path, query, args=()):
    with sqlite3.connect(path) as connection:
        return connection.execute(query, args).fetchall()


def save_key(client):
    response = client.post(
        "/api/account/provider", headers=BROWSER, json={"api_key": KEY, "consent_to_store": True}
    )
    assert response.status_code == 200, response.text


def pair(client):
    token = client.post("/api/devices/pairing", headers=BROWSER).json()["token"]
    response = client.post(
        "/api/companion/pair", json={"token": token, "name": "Laptop", "platform": "Linux"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return data["device_id"], {"Authorization": "Bearer " + data["credential"]}, token


def action(client, device, tool="open_application", arguments=None, request_id=None):
    return client.post(
        "/api/actions",
        headers=BROWSER,
        json={
            "device_id": device,
            "request_id": request_id or str(uuid.uuid4()),
            "tool": tool,
            "arguments": {"application": "chrome"} if arguments is None else arguments,
        },
    )


def approve(client, identifier, allow=True):
    return client.post(
        f"/api/actions/{identifier}/decision", headers=BROWSER, json={"allow": allow}
    )


def test_auth_session_logout_and_hashed_secrets(v1, caplog):
    client, path, _, _ = v1
    assert client.get("/api/account").status_code == 401
    token = signup(client)
    response = login(client)
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert "Max-Age=604800" in response.headers["set-cookie"]
    token = client.cookies.get(COOKIE_NAME)
    assert client.get("/api/account").status_code == 200
    assert sql(path, "SELECT token FROM accesstoken WHERE token=?", (digest(token),))
    assert not sql(path, "SELECT token FROM accesstoken WHERE token=?", (token,))
    assert sql(path, "SELECT hashed_password FROM user")[0][0].startswith("$argon2")
    assert client.post("/api/auth/logout", headers=BROWSER).status_code == 204
    use(client, token)
    assert client.get("/api/account").status_code == 401
    assert token not in caplog.text and PASSWORD not in caplog.text


def test_session_absolute_expiry(v1):
    client, path, _, _ = v1
    signup(client)
    past = (datetime.now(UTC) - timedelta(days=8)).replace(tzinfo=None).isoformat(" ")
    sql(path, "UPDATE accesstoken SET created_at=?", (past,))
    assert client.get("/api/account").status_code == 401


def test_csrf_and_auth_rate_limit(v1):
    client, _, _, _ = v1
    signup(client)
    for headers in (
        {},
        {**BROWSER, "Origin": "https://evil.example"},
        {"Origin": BROWSER["Origin"]},
    ):
        assert client.post("/api/conversations", json={}, headers=headers).status_code == 403
    for _ in range(18):
        assert (
            client.post(
                "/api/auth/login",
                headers=BROWSER,
                data={"username": "wrong@example.com", "password": PASSWORD},
            ).status_code
            == 400
        )
    assert client.post("/api/auth/login", headers=BROWSER, data={}).status_code == 429


def test_provider_encryption_consent_and_owner_binding(v1, caplog):
    client, path, _, _ = v1
    token = signup(client)
    for consent in (False, "true", 1):
        assert (
            client.post(
                "/api/account/provider",
                headers=BROWSER,
                json={"api_key": KEY, "consent_to_store": consent},
            ).status_code
            == 422
        )
    save_key(client)
    cipher = sql(path, "SELECT ciphertext FROM provider_credential")[0][0]
    assert KEY not in cipher and KEY not in caplog.text
    assert KEY not in client.get("/api/account").text
    signup(client, "other@example.com")
    assert client.get("/api/account").json()["provider_connected"] is False
    assert client.delete("/api/account/provider", headers=BROWSER).status_code == 200
    assert sql(path, "SELECT COUNT(*) FROM provider_credential")[0][0] == 1
    with pytest.raises(AppError):
        decrypt_key(client.app.state.settings, uuid.uuid4(), cipher)
    use(client, token)
    client.delete("/api/account/provider", headers=BROWSER)
    assert not sql(path, "SELECT * FROM provider_credential")


def test_conversations_persist_order_deduplicate_and_isolate(v1):
    client, path, runtime, _ = v1
    token = signup(client)
    save_key(client)
    chat = client.post("/api/conversations", headers=BROWSER, json={}).json()["id"]
    for index in range(3):
        body = {"request_id": str(uuid.uuid4()), "message": f"Message {index}"}
        response = client.post(f"/api/conversations/{chat}/messages", headers=BROWSER, json=body)
        assert response.status_code == 200, response.text
        assert client.post(
            f"/api/conversations/{chat}/messages", headers=BROWSER, json=body
        ).json() == {"message": response.json()["message"], "truncated": False}
    assert len(runtime.calls) == 3
    # A new app instance using the same migrated database and encryption key restores the session.
    restored = create_app(client.app.state.settings)
    with TestClient(restored) as other:
        use(other, token)
        data = other.get(f"/api/conversations/{chat}").json()
        assert [m["content"] for m in data["messages"][::2]] == [f"Message {i}" for i in range(3)]
    signup(client, "other@example.com")
    assert client.get("/api/conversations").json() == []
    assert client.get(f"/api/conversations/{chat}").status_code == 404
    assert client.delete(f"/api/conversations/{chat}", headers=BROWSER).status_code == 404
    assert (
        client.post(
            f"/api/conversations/{chat}/messages",
            headers=BROWSER,
            json={"request_id": str(uuid.uuid4()), "message": "Steal"},
        ).status_code
        == 404
    )
    assert len(runtime.calls) == 3
    use(client, token)
    assert client.delete(f"/api/conversations/{chat}", headers=BROWSER).status_code == 200
    assert not sql(path, "SELECT * FROM chat_turn")


def test_pairing_expiry_replay_owner_and_revocation(v1):
    client, path, _, _ = v1
    owner = signup(client)
    device, auth, token = pair(client)
    assert token not in str(sql(path, "SELECT * FROM pairing"))
    assert auth["Authorization"][7:] not in str(sql(path, "SELECT * FROM device"))
    assert (
        client.post(
            "/api/companion/pair", json={"token": token, "name": "Replay", "platform": "Linux"}
        ).status_code
        == 400
    )
    expired = client.post("/api/devices/pairing", headers=BROWSER).json()["token"]
    sql(path, "UPDATE pairing SET expires_at=0")
    assert (
        client.post(
            "/api/companion/pair", json={"token": expired, "name": "Expired", "platform": "Linux"}
        ).status_code
        == 400
    )
    signup(client, "other@example.com")
    assert client.get("/api/devices").json() == []
    assert client.delete(f"/api/devices/{device}", headers=BROWSER).status_code == 404
    assert action(client, device).status_code == 404
    use(client, owner)
    assert client.get("/api/devices").json()[0]["status"] == "online"
    sql(path, "UPDATE device SET last_seen=0")
    assert client.get("/api/devices").json()[0]["status"] == "offline"
    assert action(client, device).status_code == 409
    assert client.post("/api/companion/poll", headers=auth).status_code == 200
    assert client.get("/api/devices").json()[0]["status"] == "online"
    client.delete(f"/api/devices/{device}", headers=BROWSER)
    assert client.get("/api/devices").json()[0]["status"] == "revoked"
    assert client.post("/api/companion/poll", headers=auth).status_code == 401
    assert client.post("/api/companion/poll").status_code == 401
    assert action(client, device).status_code == 409


@pytest.mark.parametrize(
    "tool,args,status",
    [
        ("open_application", {"application": "chrome"}, 200),
        ("open_application", {"application": "vscode"}, 200),
        ("get_system_info", {}, 200),
        ("run_command", {"command": "id"}, 403),
        ("open_application", {"application": "chrome; touch /tmp/pwned"}, 422),
        ("open_application", {"application": "/bin/sh"}, 422),
        ("open_application", {"application": "chrome", "permission": "SAFE"}, 422),
        ("get_system_info", {"command": "id"}, 422),
    ],
)
def test_tools_and_permissions(v1, tool, args, status):
    client, _, _, _ = v1
    signup(client)
    device, _, _ = pair(client)
    response = action(client, device, tool, args)
    assert response.status_code == status, response.text
    if status == 200:
        assert response.json()["permission"] == ("SAFE" if tool == "get_system_info" else "CONFIRM")
    assert permission_for("run_command") == "BLOCKED"


def test_confirmation_ownership_session_expiry_and_single_use(v1):
    client, path, _, _ = v1
    owner = signup(client)
    device, auth, _ = pair(client)
    identifier = action(client, device).json()["id"]
    assert client.post("/api/companion/poll", headers=auth).json()["action"] is None
    stranger = signup(client, "other@example.com")
    assert approve(client, identifier).status_code == 404
    assert client.get("/api/actions").json() == []
    login(client)
    assert approve(client, identifier).status_code == 403  # Same user, different session.
    use(client, owner)
    assert approve(client, identifier).status_code == 200
    assert approve(client, identifier).status_code == 409
    claimed = client.post("/api/companion/poll", headers=auth).json()["action"]
    assert claimed["id"] == identifier
    assert client.post("/api/companion/poll", headers=auth).json()["action"] is None
    use(client, stranger)
    other_device, other_auth, _ = pair(client)
    assert (
        client.post(
            f"/api/companion/actions/{identifier}/authorize", headers=other_auth
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/companion/actions/{identifier}/result",
            headers=other_auth,
            json={"code": "application_opened"},
        ).status_code
        == 404
    )
    use(client, owner)
    assert (
        client.post(f"/api/companion/actions/{identifier}/authorize", headers=auth).status_code
        == 200
    )
    for status in (200, 409):
        assert (
            client.post(
                f"/api/companion/actions/{identifier}/result",
                headers=auth,
                json={"code": "application_opened"},
            ).status_code
            == status
        )
    expired = action(client, device).json()["id"]
    sql(path, "UPDATE action SET expires_at=0 WHERE id=?", (expired,))
    assert approve(client, expired).status_code == 409
    assert any(a["status"] == "expired" for a in client.get("/api/actions").json())
    denied = action(client, device).json()["id"]
    assert approve(client, denied, False).json()["status"] == "cancelled"
    assert approve(client, denied).status_code == 409


def test_safe_execution_timeout_and_revocation_cancel(v1):
    client, path, _, _ = v1
    signup(client)
    device, auth, _ = pair(client)
    identifier = action(client, device, "get_system_info", {}).json()["id"]
    assert client.post("/api/companion/poll", headers=auth).json()["action"]["id"] == identifier
    assert (
        client.post(
            f"/api/companion/actions/{identifier}/result",
            headers=auth,
            json={"code": "application_opened"},
        ).status_code
        == 422
    )
    sql(path, "UPDATE action SET expires_at=0")
    assert (
        client.post(f"/api/companion/actions/{identifier}/authorize", headers=auth).status_code
        == 409
    )
    assert client.get("/api/actions").json()[0]["status"] == "expired"
    queued = action(client, device, "get_system_info", {}).json()["id"]
    client.delete(f"/api/devices/{device}", headers=BROWSER)
    assert client.post("/api/companion/poll", headers=auth).status_code == 401
    assert (
        client.post(
            f"/api/companion/actions/{queued}/result", headers=auth, json={"code": "system_info"}
        ).status_code
        == 401
    )
    assert all(a["status"] in ("cancelled", "expired") for a in client.get("/api/actions").json())


def test_model_tool_flow_truthful_result_and_idempotency(v1):
    client, path, runtime, _ = v1
    signup(client)
    save_key(client)
    device, auth, _ = pair(client)
    chat = client.post("/api/conversations", headers=BROWSER, json={}).json()["id"]
    body = {
        "message": "Open Chrome on my laptop.",
        "device_id": device,
        "request_id": str(uuid.uuid4()),
    }
    response = client.post(f"/api/conversations/{chat}/messages", headers=BROWSER, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert "UNTRUSTED SUCCESS" not in response.text
    assert "Nothing has executed" in result["message"]["content"]
    identifier = result["action"]["id"]
    assert approve(client, identifier).status_code == 200
    client.post("/api/companion/poll", headers=auth)
    client.post(
        f"/api/companion/actions/{identifier}/result",
        headers=auth,
        json={"code": "application_opened"},
    )
    messages = client.get(f"/api/conversations/{chat}").json()["messages"]
    assert messages[-1]["content"] == "The application window opened on your device."
    client.post(f"/api/conversations/{chat}/messages", headers=BROWSER, json=body)
    assert len(runtime.calls) == 1
    assert sql(path, "SELECT COUNT(*) FROM action")[0][0] == 1
    assert sql(path, "SELECT status, permission FROM action")[0] == ("succeeded", "CONFIRM")
    request_id = str(uuid.uuid4())
    first = action(client, device, request_id=request_id)
    assert action(client, device, request_id=request_id).json()["id"] == first.json()["id"]
    assert action(client, device, "get_system_info", {}, request_id).status_code == 409


def test_migration_consistency_and_roundtrip(v1):
    _, path, _, config = v1
    command.check(config)
    command.downgrade(config, "base")
    assert sql(path, "SELECT name FROM sqlite_master WHERE type='table'") == [("alembic_version",)]
    command.upgrade(config, "head")
    command.check(config)


def test_concurrent_pairing_and_action_replays(v1):
    from concurrent.futures import ThreadPoolExecutor

    client, path, _, _ = v1
    signup(client)
    token = client.post("/api/devices/pairing", headers=BROWSER).json()["token"]

    def redeem(_):
        return client.post(
            "/api/companion/pair", json={"token": token, "name": "Race test", "platform": "Linux"}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(redeem, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 400]
    data = next(r.json() for r in responses if r.status_code == 200)
    request_id = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: action(client, data["device_id"], request_id=request_id), range(2))
        )
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()["id"] == responses[1].json()["id"]
    identifier = responses[0].json()["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        approvals = list(pool.map(lambda _: approve(client, identifier), range(2)))
    assert sorted(r.status_code for r in approvals) == [200, 409]
    headers = {"Authorization": "Bearer " + data["credential"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        polls = list(
            pool.map(lambda _: client.post("/api/companion/poll", headers=headers), range(2))
        )
    assert all(r.status_code == 200 for r in polls)
    assert sum(r.json()["action"] is not None for r in polls) == 1
    assert sql(path, "SELECT COUNT(*) FROM action")[0][0] == 1


def test_api_and_device_keys_do_not_authenticate_an_account(v1):
    client, _, _, _ = v1
    signup(client)
    _, device_auth, _ = pair(client)
    client.cookies.clear()
    for headers in (device_auth, {"Authorization": "Bearer " + KEY}):
        assert client.get("/api/account", headers=headers).status_code == 401
        assert client.get("/api/devices", headers=headers).status_code == 401
        assert client.get("/api/actions", headers=headers).status_code == 401


def test_registration_cannot_grant_privileges(v1):
    client, path, _, _ = v1
    response = client.post(
        "/api/auth/register",
        headers=BROWSER,
        json={
            "email": "privilege@example.com",
            "password": PASSWORD,
            "is_superuser": True,
            "is_verified": True,
        },
    )
    assert response.status_code == 201
    assert sql(path, "SELECT is_superuser,is_verified FROM user")[0] == (0, 0)


def test_production_cookie_and_missing_vault(v1):
    client, _, _, _ = v1
    settings = client.app.state.settings.model_copy(
        update={"app_env": "production", "frontend_origin": "https://thryv.example.com"}
    )
    with TestClient(create_app(settings), base_url="https://api.thryv.example.com") as https:
        headers = {"Origin": "https://thryv.example.com", "X-THRYV-Request": "1"}
        https.post(
            "/api/auth/register",
            headers=headers,
            json={"email": "secure@example.com", "password": PASSWORD},
        )
        response = https.post(
            "/api/auth/login",
            headers=headers,
            data={"username": "secure@example.com", "password": PASSWORD},
        )
        assert response.status_code == 204
        assert "Secure" in response.headers["set-cookie"]
        assert https.get("/api/account").status_code == 200
    settings = settings.model_copy(update={"credential_encryption_key": None})
    with pytest.raises(AppError):
        with TestClient(create_app(settings)):
            pass
