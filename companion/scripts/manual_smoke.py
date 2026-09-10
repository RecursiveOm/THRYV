"""Opt-in REAL Chrome window test against a running local backend; no model is mocked or called."""

import secrets
import tempfile
import uuid
from pathlib import Path

import httpx

from thryv_companion.client import Ledger, Revoked, run_once


def main():
    base = "http://localhost:8000"
    headers = {"Origin": "http://localhost:3000", "X-THRYV-Request": "1"}
    device = None
    with httpx.Client(base_url=base, headers=headers, timeout=20, trust_env=False) as account:
        try:
            email = f"desktop-check-{uuid.uuid4()}@example.com"
            password = secrets.token_urlsafe(24)
            account.post(
                "/api/auth/register", json={"email": email, "password": password}
            ).raise_for_status()
            account.post(
                "/api/auth/login", data={"username": email, "password": password}
            ).raise_for_status()
            token = account.post("/api/devices/pairing").json()["token"]
            paired = account.post(
                "/api/companion/pair",
                json={"token": token, "name": "Manual Chrome verification", "platform": "Linux"},
            )
            paired.raise_for_status()
            device = paired.json()["device_id"]
            with httpx.Client(
                base_url=base,
                timeout=10,
                trust_env=False,
                headers={"Authorization": "Bearer " + paired.json()["credential"]},
            ) as http:
                with tempfile.TemporaryDirectory(prefix="thryv-manual-") as directory:
                    ledger = Ledger(Path(directory) / "ledger.sqlite")
                    try:
                        action = account.post(
                            "/api/actions",
                            json={
                                "device_id": device,
                                "request_id": str(uuid.uuid4()),
                                "tool": "open_application",
                                "arguments": {"application": "chrome"},
                            },
                        )
                        action.raise_for_status()
                        identifier = action.json()["id"]
                        assert action.json()["status"] == "pending_confirmation"
                        assert http.post("/api/companion/poll").json()["action"] is None
                        print("PASS pairing, ownership and pre-approval dispatch block")
                        account.post(
                            f"/api/actions/{identifier}/decision", json={"allow": True}
                        ).raise_for_status()
                        run_once(http, ledger)
                        result = next(
                            a for a in account.get("/api/actions").json() if a["id"] == identifier
                        )
                        if result["status"] != "succeeded":
                            print("FAIL real Chrome launch: " + result["status"])
                            return 1
                        print("PASS real Chrome window observed, structured result saved in audit")
                        assert http.post("/api/companion/poll").json()["action"] is None
                        account.delete(f"/api/devices/{device}").raise_for_status()
                        try:
                            run_once(http, ledger)
                        except Revoked:
                            print("PASS revocation stops Companion; no repeated execution")
                        else:
                            raise AssertionError()
                    finally:
                        ledger.close()
        except Exception:
            print("FAIL manual Companion verification; credentials and raw errors withheld")
            return 1
        finally:
            if device:
                account.delete(f"/api/devices/{device}")
            account.post("/api/auth/logout")
    print("Live DeepSeek-to-tool demo remains a separate acceptance check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
