import argparse
import getpass
import json
import logging
import os
import platform
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from thryv_companion.executor import execute
from thryv_companion.workspaces import Workspaces


class Revoked(Exception):
    pass


def server_url(value):
    url = urlsplit(value)
    if (
        url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ("", "/")
        or not url.hostname
        or (
            url.scheme != "https"
            and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1"))
        )
    ):
        raise ValueError("Use an HTTPS server origin (HTTP is allowed only on loopback).")
    return value.rstrip("/")


def state_directory(path):
    path = Path(path).expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise ValueError("Companion state must be owned by this desktop user.")
    path.chmod(0o700)
    return path


def write_credentials(path, value):
    # Exclusive creation prevents overwriting a paired device or following symlinks.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())


def read_credentials(path):
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError("Device credentials must be private to this desktop user (mode 0600).")
    data = json.loads(path.read_text())
    server_url(data["server"])
    if not isinstance(data["credential"], str) or len(data["credential"]) != 43:
        raise ValueError("Invalid device credential.")
    return data


def request(client, path, body=None):
    with client.stream("POST", path, json=body) as response:
        if response.status_code == 401:
            raise Revoked()
        response.raise_for_status()
        payload = bytearray()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > 100000:
                raise ValueError("Oversized server response")
        return json.loads(payload)


class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        Path(path).chmod(0o600)
        self.db.execute("CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY)")
        self.db.commit()

    def claim(self, identifier):
        try:
            self.db.execute("INSERT INTO executions(id) VALUES (?)", (identifier,))
            # Persist before the side effect; crashes never cause automatic replay.
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def close(self):
        self.db.close()


def run_once(client, ledger, workspaces=None):
    if workspaces is not None:
        from thryv_companion.development import prune_servers

        prune_servers(workspaces)
        grants = workspaces.grants()
        result = request(
            client,
            "/api/companion/workspaces",
            {
                "workspaces": [
                    {"id": identifier, "name": grant["name"], "path": grant["path"]}
                    for identifier, grant in grants.items()
                ]
            },
        )
        for identifier in result.get("revoked", []):
            workspaces.remove(identifier)
    action = request(client, "/api/companion/poll").get("action")
    if not action:
        return
    identifier = str(uuid.UUID(action["id"]))
    if not isinstance(action["expires_at"], int) or action["expires_at"] <= time.time():
        return
    if not ledger.claim(identifier):
        result = {"code": "execution_uncertain"}
    else:
        authorization = request(client, f"/api/companion/actions/{identifier}/authorize")
        if authorization.get("authorized") is not True:
            return
        if action["tool"].startswith(("workspace_", "development_")) and workspaces is not None:
            try:
                if action["tool"] == "workspace_open":
                    workspace_id = action["arguments"]["workspace_id"]
                    if set(action["arguments"]) != {"workspace_id"}:
                        raise ValueError("Invalid project launch")
                    with workspaces.root(workspace_id):
                        outcome = execute(
                            "open_application",
                            {"application": "vscode"},
                            action["expires_at"],
                            project_path=workspaces.grants()[workspace_id]["path"],
                        )
                    data = {
                        "launch_result": outcome["code"],
                        "verified": outcome["code"] == "application_opened",
                    }
                elif action["tool"].startswith(("development_", "workspace_git")):
                    from thryv_companion.development import execute as develop

                    def cancelled():
                        try:
                            request(client, f"/api/companion/actions/{identifier}/authorize")
                            return action["arguments"]["workspace_id"] not in workspaces.grants()
                        except (httpx.HTTPError, Revoked):
                            return True

                    data = develop(
                        workspaces,
                        action["tool"],
                        action["arguments"],
                        action["expires_at"],
                        cancelled,
                    )
                else:
                    data = workspaces.execute(action["tool"], action["arguments"])
                result = {"code": "workspace_result", "data": data}
            except Exception:
                result = {"code": "blocked"}
        else:
            result = execute(action["tool"], action["arguments"], action["expires_at"])
    # Retry only the sanitized RESULT; never repeat the side effect.
    for attempt in range(3):
        try:
            request(client, f"/api/companion/actions/{identifier}/result", result)
            return
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 409:
                return
            raise
        except httpx.TransportError:
            if attempt == 2:
                raise
            time.sleep(1)


def main():
    os.umask(0o077)
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).disabled = True
    parser = argparse.ArgumentParser(description="THRYV outbound Companion")
    parser.add_argument(
        "command",
        choices=("pair", "run", "workspace-add", "workspace-remove", "workspaces", "command-add"),
    )
    parser.add_argument("path_or_id", nargs="?")
    parser.add_argument("--command-name", default="tests")
    parser.add_argument("--runner", default="pytest")
    parser.add_argument("--cwd", default=".")
    parser.add_argument(
        "--allow-git-ssh",
        action="store_true",
        help="Authorize existing SSH agent for fixed GitHub-origin fetch/push only",
    )
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--name", default="My Linux laptop")
    parser.add_argument("--state-dir", default="~/.local/share/thryv-companion")
    args = parser.parse_args()
    try:
        directory = state_directory(args.state_dir)
        credentials = directory / "device.json"
        if args.command == "pair":
            origin = server_url(args.server)
            if credentials.exists():
                raise ValueError(
                    "Already paired. Revoke this device before using a new state directory."
                )
            token = getpass.getpass("Single-use pairing token (hidden): ").strip()
            with httpx.Client(
                base_url=origin, timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                data = request(
                    client,
                    "/api/companion/pair",
                    {"token": token, "name": args.name, "platform": platform.system()},
                )
            write_credentials(credentials, {"server": origin, **data})
            print("Paired. Run thryv-companion run in your desktop session.")
            return
        data = read_credentials(credentials)
        workspaces = Workspaces(directory)
        if args.command == "command-add":
            from thryv_companion.development import configure

            configure(workspaces, args.path_or_id, args.command_name, args.runner, args.cwd)
            print("Configured fixed development runner. Each run still requires confirmation.")
            return
        if args.command == "workspace-add":
            identifier = workspaces.add(args.path_or_id or "")
            if args.allow_git_ssh:
                grants = workspaces.grants()
                grants[identifier]["git_ssh"] = True
                workspaces.save(grants)
            print("Authorized workspace:", identifier)
            return
        if args.command == "workspace-remove":
            workspaces.remove(str(uuid.UUID(args.path_or_id or "")))
            print("Workspace removed. Running Companion will sync revocation.")
            return
        if args.command == "workspaces":
            for identifier, grant in workspaces.grants().items():
                print(identifier, grant["path"])
            return
        ledger = Ledger(directory / "executions.sqlite")
        try:
            with httpx.Client(
                base_url=data["server"],
                timeout=10,
                follow_redirects=False,
                trust_env=False,
                headers={"Authorization": "Bearer " + data["credential"]},
            ) as client:
                print("Companion online. Press Ctrl+C to stop.")
                delay = 2
                while True:
                    try:
                        run_once(client, ledger, workspaces)
                        delay = 2
                    except (httpx.HTTPError, ValueError, KeyError, TypeError):
                        print("Connection or request unavailable; retrying with bounded backoff.")
                        delay = min(delay * 2, 30)
                    time.sleep(delay)
        finally:
            ledger.close()
            from thryv_companion.development import close_servers

            close_servers()
    except Revoked:
        print("Device credential invalid or revoked. Companion stopped.")
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError, httpx.HTTPError):
        print(
            "Companion could not start or pair. Check server, token, and private state directory."
        )
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("Companion stopped.")


if __name__ == "__main__":
    main()
