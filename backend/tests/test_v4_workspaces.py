import uuid

from tests.test_v1 import BROWSER, action, pair, signup, use

pytest_plugins = ["tests.test_v1"]


def grant(client, headers, identifier=None):
    identifier = identifier or str(uuid.uuid4())
    response = client.post(
        "/api/companion/workspaces",
        headers=headers,
        json={"workspaces": [{"id": identifier, "name": "Project", "path": "/home/owner/Project"}]},
    )
    assert response.status_code == 200
    return identifier


def test_owned_workspace_permissions_and_revocation(v1):
    client, _, _, _ = v1
    signup(client)
    device, headers, _ = pair(client)
    identifier = grant(client, headers)
    assert client.post(f"/api/workspaces/{identifier}/select", headers=BROWSER).status_code == 200
    assert client.get("/api/workspaces").json()[0]["active"]
    args = {"workspace_id": identifier, "path": "main.py"}
    response = action(client, device, "workspace_read", args)
    assert response.status_code == 200 and response.json()["permission"] == "SAFE"
    write = action(client, device, "workspace_write", {**args, "content": "new", "sha256": ""})
    assert write.json()["status"] == "pending_confirmation"
    assert client.delete(f"/api/workspaces/{identifier}", headers=BROWSER).status_code == 200
    assert action(client, device, "workspace_read", args).status_code == 403
    assert (
        identifier
        in client.post(
            "/api/companion/workspaces", headers=headers, json={"workspaces": []}
        ).json()["revoked"]
    )


def test_workspace_cross_user_device_isolation(v1):
    client, _, _, _ = v1
    owner = signup(client)
    device, headers, _ = pair(client)
    identifier = grant(client, headers)
    other_device, _, _ = pair(client)
    args = {"workspace_id": identifier}
    assert action(client, other_device, "workspace_list", args).status_code == 403
    signup(client, "other@example.com")
    assert client.get("/api/workspaces").json() == []
    assert client.post(f"/api/workspaces/{identifier}/select", headers=BROWSER).status_code == 403
    _, other_headers, _ = pair(client)
    response = client.post(
        "/api/companion/workspaces",
        headers=other_headers,
        json={"workspaces": [{"id": identifier, "name": "Stolen", "path": "/tmp/x"}]},
    )
    assert response.status_code == 409
    use(client, owner)
    assert action(client, device, "workspace_list", args).status_code == 200


def test_workspace_routes_require_csrf(v1):
    client, _, _, _ = v1
    signup(client)
    _, headers, _ = pair(client)
    identifier = grant(client, headers)
    assert client.post(f"/api/workspaces/{identifier}/select").status_code == 403
    assert client.delete(f"/api/workspaces/{identifier}").status_code == 403


def test_workflow_never_claims_unverified_edit_fixed(v1):
    from contextlib import asynccontextmanager

    from app.providers.base import Completion, ToolCall
    from tests.test_v1 import save_key
    from tests.test_v4_integrations import wait_action

    client, _, runtime, _ = v1
    signup(client)
    save_key(client)
    device, headers, _ = pair(client)
    identifier = grant(client, headers)
    client.post(f"/api/workspaces/{identifier}/select", headers=BROWSER)

    async def initial(*args):
        return Completion(
            "",
            tool_call=ToolCall(
                "workspace_write",
                {
                    "workspace_id": identifier,
                    "path": "main.py",
                    "sha256": "",
                    "content": "print(1)",
                },
            ),
        )

    runtime.plan = initial

    class Model:
        async def plan(self, *args):
            import json

            observed = json.loads(args[1][-1]["content"].split("\n", 1)[1])
            assert observed["arguments"]["path"] == "main.py"
            assert observed["tool"] == "workspace_write"
            return Completion("Everything is fixed and verified!")

    @asynccontextmanager
    async def provider(settings):
        yield Model()

    client.app.state.workflows.provider_context = provider
    conversation = client.post("/api/conversations", headers=BROWSER, json={}).json()["id"]
    reply = client.post(
        f"/api/conversations/{conversation}/messages",
        headers=BROWSER,
        json={
            "message": "Create main.py then test it.",
            "device_id": device,
            "request_id": str(uuid.uuid4()),
        },
    ).json()
    root = reply["action"]
    child = wait_action(client, root["id"], False)["details"]["children"][0]
    client.post(f"/api/actions/{child}/decision", headers=BROWSER, json={"allow": True})
    claimed = client.post("/api/companion/poll", headers=headers).json()["action"]
    assert claimed["id"] == child
    response = client.post(
        f"/api/companion/actions/{child}/result",
        headers=headers,
        json={"code": "workspace_result", "data": {"path": "main.py", "sha256": "0" * 64}},
    )
    assert response.status_code == 200
    result = wait_action(client, root["id"])
    assert result["status"] == "failed" and "verification has not passed" in result["result"]


def test_revocation_stops_running_workspace_authorization(v1):
    client, _, _, _ = v1
    signup(client)
    device, headers, _ = pair(client)
    identifier = grant(client, headers)
    response = action(client, device, "workspace_list", {"workspace_id": identifier})
    child = response.json()["id"]
    client.post("/api/companion/poll", headers=headers)
    assert (
        client.post(f"/api/companion/actions/{child}/authorize", headers=headers).status_code == 200
    )
    client.delete(f"/api/workspaces/{identifier}", headers=BROWSER)
    assert (
        client.post(f"/api/companion/actions/{child}/authorize", headers=headers).status_code == 409
    )
