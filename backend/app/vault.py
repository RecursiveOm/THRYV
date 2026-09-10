import json

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.errors import AppError


def cipher(settings) -> Fernet:
    if not settings.credential_encryption_key:
        raise AppError(
            "vault_unavailable", "The host must configure credential encryption first.", 503
        )
    try:
        return Fernet(settings.credential_encryption_key.get_secret_value().encode())
    except (ValueError, TypeError):
        raise AppError("vault_unavailable", "Credential storage is unavailable.", 503) from None


def encrypt_key(settings, owner, key: SecretStr) -> str:
    payload = json.dumps({"owner": str(owner), "key": key.get_secret_value()}).encode()
    return cipher(settings).encrypt(payload).decode()


def decrypt_key(settings, owner, ciphertext: str) -> SecretStr:
    try:
        payload = json.loads(cipher(settings).decrypt(ciphertext.encode()))
        if payload["owner"] != str(owner):
            raise ValueError("Owner mismatch")
        return SecretStr(payload["key"])
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise AppError(
            "vault_unavailable", "Reconnect your DeepSeek key in provider settings.", 503
        ) from None
