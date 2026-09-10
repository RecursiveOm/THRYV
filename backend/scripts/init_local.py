"""Initialize local encryption configuration without printing a secret."""

import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values

path = Path(".env")
if not path.exists():
    path.write_text(Path(".env.example").read_text())
values = dotenv_values(path)
if not values.get("CREDENTIAL_ENCRYPTION_KEY"):
    with path.open("a") as file:
        file.write("\nCREDENTIAL_ENCRYPTION_KEY=" + Fernet.generate_key().decode() + "\n")
os.chmod(path, 0o600)
print("Local encryption configuration is ready in ignored .env. No secrets were displayed.")

if Path("thryv.db").exists():
    Path("thryv.db").chmod(0o600)
