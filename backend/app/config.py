from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    frontend_origin: str = "http://localhost:3000"
    deepseek_model: str = Field(default="deepseek-flash", min_length=1, max_length=100)
    provider_timeout_seconds: float = Field(default=60, ge=1, le=120)
    max_concurrent_requests: int = Field(default=20, ge=1, le=200)

    @model_validator(mode="after")
    def validate_origin(self):
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
