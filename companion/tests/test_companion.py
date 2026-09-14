import json
import time
import uuid

import httpx
import pytest

from thryv_companion import client, executor


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?token=secret",
        "file:///tmp/a",
        "http://localhost.evil.example",
    ],
)
def test_reject_unsafe_server(value):
    with pytest.raises(ValueError):
        client.server_url(value)


@pytest.mark.parametrize(
    "value", ["http://localhost:8000", "http://127.0.0.1:8000", "https://thryv.example.com"]
)
def test_allowed_server(value):
    assert client.server_url(value) == value


def test_credentials_private_and_exclusive(tmp_path):
    directory = client.state_directory(tmp_path / "state")
    path = directory / "device.json"
    data = {"server": "https://example.com", "credential": "x" * 43}
    client.write_credentials(path, data)
    assert path.stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700
    assert client.read_credentials(path) == data
    with pytest.raises(FileExistsError):
        client.write_credentials(path, data)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        client.read_credentials(path)


@pytest.mark.parametrize(
    "tool,args",
    [
        ("run_command", {"command": "touch /tmp/pwned"}),
        ("open_application", {"application": "chrome; touch /tmp/pwned"}),
        ("open_application", {"application": "/bin/sh"}),
        ("open_application", {"application": "chrome", "args": ["--no-sandbox"]}),
        ("open_application", {"application": ["chrome"]}),
        ("get_system_info", {"command": "id"}),
    ],
)
def test_injection_never_reaches_process(monkeypatch, tool, args):
    def forbidden(*a, **kw):
        pytest.fail("Blocked input reached a process")

    monkeypatch.setattr(executor.subprocess, "Popen", forbidden)
    assert executor.execute(tool, args, time.time() + 30) == {"code": "blocked"}


@pytest.mark.parametrize("url", [None, "https://fastapi.tiangolo.com/"])
def test_verified_launch_uses_fixed_argv(monkeypatch, tmp_path, url):
    monkeypatch.setattr(executor.Path, "home", lambda: tmp_path)
    seen = []

    class Windows:
        def __init__(self):
            self.count = 0

        def matching(self, classes):
            self.count += 1
            return {1} if self.count == 1 else {1, 2}

        def close(self):
            pass

    class Process:
        def poll(self):
            return 0

    def launch(argv, **kwargs):
        seen.append((argv, kwargs))
        return Process()

    monkeypatch.setattr(executor, "Windows", Windows)
    monkeypatch.setattr(executor, "trusted_executable", lambda paths: paths[0])
    monkeypatch.setattr(executor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(executor.subprocess, "Popen", launch)
    assert executor.execute(
        "open_url" if url else "open_application",
        {"url": url} if url else {"application": "chrome"},
        time.time() + 30,
    ) == {"code": "url_opened" if url else "application_opened"}
    assert seen[0][0][:4] == [
        "/opt/google/chrome/google-chrome",
        "--new-window",
        url or "about:blank",
        "--ozone-platform=x11",
    ]
    assert seen[0][1]["shell"] is False


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost",
        "http://127.0.0.1",
        "http://[::1]",
        "https://a:b@example.com",
        "--no-sandbox",
        "https://example.com:22",
        "https://example.com\n--no-sandbox",
    ],
)
def test_public_url_blocks_injection(monkeypatch, url):
    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe URL reached process launch")

    monkeypatch.setattr(executor.subprocess, "Popen", forbidden)
    assert executor.execute("open_url", {"url": url}, time.time() + 30) == {"code": "blocked"}


def test_missing_and_unverified_launch(monkeypatch):
    monkeypatch.setattr(executor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(executor, "trusted_executable", lambda paths: None)
    assert (
        executor.execute("open_application", {"application": "chrome"}, time.time() + 30)["code"]
        == "application_missing"
    )
    monkeypatch.setattr(executor, "trusted_executable", lambda paths: paths[0])

    def unavailable():
        raise OSError("private desktop info")

    monkeypatch.setattr(executor, "Windows", unavailable)
    assert (
        executor.execute("open_application", {"application": "chrome"}, time.time() + 30)["code"]
        == "launch_unconfirmed"
    )
    assert executor.execute("open_application", {"application": "chrome"}, 0)["code"] == "timeout"


def test_system_info_is_bounded(monkeypatch):
    monkeypatch.setattr(executor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(executor.platform, "machine", lambda: "x86_64")
    assert executor.execute("get_system_info", {}, time.time() + 30) == {
        "code": "system_info",
        "platform": "Linux",
        "architecture": "x86_64",
    }


def test_authenticated_execution_and_durable_replay_guard(tmp_path, monkeypatch):
    identifier = str(uuid.uuid4())
    executed = []
    results = []

    def handler(request):
        assert request.headers["authorization"] == "Bearer test-device-token"
        if request.url.path.endswith("/poll"):
            return httpx.Response(
                200,
                json={
                    "action": {
                        "id": identifier,
                        "tool": "open_application",
                        "arguments": {"application": "chrome"},
                        "expires_at": int(time.time()) + 30,
                    }
                },
            )
        if request.url.path.endswith("/authorize"):
            return httpx.Response(200, json={"authorized": True})
        results.append(json.loads(request.content))
        return httpx.Response(200, json={"recorded": True})

    def execute(*args):
        executed.append(args)
        return {"code": "application_opened"}

    monkeypatch.setattr(client, "execute", execute)
    with httpx.Client(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer test-device-token"},
    ) as http:
        for _ in range(2):
            ledger = client.Ledger(tmp_path / "ledger.sqlite")
            client.run_once(http, ledger)
            ledger.close()
    assert len(executed) == 1
    assert results == [{"code": "application_opened"}, {"code": "execution_uncertain"}]


def test_revoked_before_execution_stops_without_side_effect(tmp_path, monkeypatch):
    def handler(request):
        if request.url.path.endswith("/poll"):
            return httpx.Response(
                200,
                json={
                    "action": {
                        "id": str(uuid.uuid4()),
                        "tool": "open_application",
                        "arguments": {"application": "chrome"},
                        "expires_at": int(time.time()) + 30,
                    }
                },
            )
        return httpx.Response(401)

    def forbidden(*args):
        pytest.fail("Revoked request executed")

    monkeypatch.setattr(client, "execute", forbidden)
    ledger = client.Ledger(tmp_path / "ledger.sqlite")
    with httpx.Client(
        base_url="https://example.com", transport=httpx.MockTransport(handler)
    ) as http:
        with pytest.raises(client.Revoked):
            client.run_once(http, ledger)
    ledger.close()


def test_result_retry_does_not_repeat_execution(tmp_path, monkeypatch):
    executions = []
    attempts = []

    def handler(request):
        if request.url.path.endswith("/poll"):
            return httpx.Response(
                200,
                json={
                    "action": {
                        "id": str(uuid.uuid4()),
                        "tool": "get_system_info",
                        "arguments": {},
                        "expires_at": int(time.time()) + 30,
                    }
                },
            )
        if request.url.path.endswith("/authorize"):
            return httpx.Response(200, json={"authorized": True})
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("secret-token")
        return httpx.Response(409)

    def execute(*args):
        executions.append(1)
        return {"code": "system_info", "platform": "Linux", "architecture": "x86_64"}

    monkeypatch.setattr(client, "execute", execute)
    monkeypatch.setattr(client.time, "sleep", lambda _: None)
    ledger = client.Ledger(tmp_path / "ledger.sqlite")
    with httpx.Client(
        base_url="https://example.com", transport=httpx.MockTransport(handler)
    ) as http:
        client.run_once(http, ledger)
    ledger.close()
    assert len(executions) == 1 and len(attempts) == 2
