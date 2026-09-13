"""Verify the locally built V2 image using a disposable private volume and secret."""

import secrets
import subprocess
import tempfile
import time
from pathlib import Path

from cryptography.fernet import Fernet


def run(arguments):
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Container check failed; raw output withheld")
    return result.stdout.strip()


def main():
    name = "thryv-v2-check-" + secrets.token_hex(4)
    volume = name + "-data"
    stage = "temporary configuration"
    try:
        with tempfile.TemporaryDirectory(prefix="thryv-container-") as folder:
            env = Path(folder) / "config.env"
            env.write_text(
                "APP_ENV=production\nFRONTEND_ORIGIN=https://app.example.com\n"
                "CREDENTIAL_ENCRYPTION_KEY=" + Fernet.generate_key().decode() + "\n"
            )
            env.chmod(0o600)
            run(["volume", "create", volume])
            common = [
                "--env-file",
                str(env),
                "--mount",
                f"type=volume,source={volume},target=/data",
            ]
            stage = "non-root volume migration"
            run(["run", "--rm", *common, "thryv-backend:v2", "alembic", "upgrade", "head"])
            print("PASS " + stage)
            stage = "production health, data permissions, schema and artifact exclusion"
            run(["run", "-d", "--name", name, *common, "thryv-backend:v2"])
            script = """
import os, pathlib, sqlite3, urllib.request, urllib.error
assert urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200
assert os.getuid() == 10001
assert not pathlib.Path('/app/.env').exists()
assert not pathlib.Path('/app/tests').exists()
assert pathlib.Path('/data').stat().st_mode & 0o777 == 0o700
assert pathlib.Path('/data/thryv.db').stat().st_mode & 0o077 == 0
with sqlite3.connect('/data/thryv.db') as db:
    assert db.execute('select version_num from alembic_version').fetchone()[0] == '6c9c73ac0555'
try:
    urllib.request.urlopen('http://127.0.0.1:8000/docs')
except urllib.error.HTTPError as error:
    assert error.code == 404
else:
    raise AssertionError('Production docs must be disabled')
"""
            for attempt in range(30):
                try:
                    run(["exec", name, "python", "-c", script])
                    break
                except RuntimeError:
                    if attempt == 29:
                        raise
                    time.sleep(0.5)
            print("PASS " + stage)
            stage = "container migration consistency"
            run(["exec", name, "alembic", "check"])
            print("PASS " + stage)
        return 0
    except Exception:
        print("FAIL " + stage + "; raw configuration withheld")
        return 1
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "volume", "rm", volume], capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
