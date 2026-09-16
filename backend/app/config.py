from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    frontend_origin: str = "http://localhost:3000"
    deepseek_model: str = Field(default="deepseek-flash", min_length=1, max_length=100)
    provider_timeout_seconds: float = Field(default=60, ge=1, le=120)
    max_concurrent_requests: int = Field(default=20, ge=1, le=200)
    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///./thryv.db")
    credential_encryption_key: SecretStr | None = None
    auth_attempts_per_minute: int = Field(default=20, ge=1, le=1000)
    stt_model_path: str = ".models/whisper-base.en"
    wake_model_path: str = ".models/thryv-wake"
    oauth_origin: str = "http://localhost:8000"
    github_client_id: str = ""
    github_client_secret: SecretStr | None = None
    google_client_id: str = ""
    google_client_secret: SecretStr | None = None
    tts_model_path: str = ".models/en_US-lessac-medium.onnx"
    session_lifetime_seconds: int = Field(default=604800, ge=60, le=2592000)

    @model_validator(mode="after")
    def validate_origin(self):
        oauth = urlsplit(self.oauth_origin)
        if (
            oauth.path
            or oauth.query
            or oauth.fragment
            or oauth.username
            or oauth.password
            or not oauth.hostname
            or (
                oauth.scheme != "https"
                and not (oauth.scheme == "http" and oauth.hostname in {"localhost", "127.0.0.1"})
            )
        ):
            raise ValueError("OAuth requires an exact HTTPS origin (loopback HTTP for development)")
        if (
            self.app_env == "production"
            and (self.github_client_id or self.google_client_id)
            and oauth.scheme != "https"
        ):
            raise ValueError("Production OAuth requires HTTPS")
        origin = urlsplit(self.frontend_origin)
        if (
            origin.scheme not in ("http", "https")
            or not origin.netloc
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
            or "*" in self.frontend_origin
        ):
            raise ValueError("FRONTEND_ORIGIN must be one explicit origin without a trailing slash")
        if self.app_env == "production" and origin.scheme != "https":
            raise ValueError("Production FRONTEND_ORIGIN must use HTTPS")
        return self
