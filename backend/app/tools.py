from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.errors import AppError


class OpenApplication(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    application: Literal["chrome", "vscode"]


class SystemInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OpenURL(SystemInfo):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        from app.public_web import public_url

        return public_url(value)


class SearchWeb(SystemInfo):
    query: str = Field(min_length=3, max_length=300)
    source_urls: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("source_urls")
    @classmethod
    def validate_sources(cls, values):
        return [OpenURL(url=value).url for value in values]


class FollowLink(SystemInfo):
    link_id: int = Field(ge=1, le=150)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: type[BaseModel]
    permission: Literal["SAFE", "CONFIRM"]
    target: str = "companion"

    def definition(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema.model_json_schema(),
            },
        }


REGISTRY = {
    "search_web": Tool(
        "search_web",
        "Research public web information: search, read relevant sources, and synthesize. "
        "Put the topic first in query. Optionally supply up to 3 likely official source_urls; "
        "these are unverified hints until fetched. No paired device needed.",
        SearchWeb,
        "SAFE",
        "public_web",
    ),
    "open_webpage": Tool(
        "open_webpage",
        "Read a public URL in this conversation's isolated research context.",
        OpenURL,
        "SAFE",
        "public_web",
    ),
    "inspect_webpage": Tool(
        "inspect_webpage",
        "Inspect the current research page title, URL, content and numbered links.",
        SystemInfo,
        "SAFE",
        "public_web",
    ),
    "follow_web_link": Tool(
        "follow_web_link",
        "Read a numbered link from the current research page.",
        FollowLink,
        "SAFE",
        "public_web",
    ),
    "back_webpage": Tool(
        "back_webpage",
        "Return to the previous captured research page in this conversation.",
        SystemInfo,
        "SAFE",
        "public_web",
    ),
    "open_url": Tool(
        "open_url",
        "Open a public HTTP(S) URL in Chrome on the selected computer. "
        "Requires confirmation. Does not read the user's browser.",
        OpenURL,
        "CONFIRM",
    ),
    "open_application": Tool(
        "open_application",
        "Open Chrome or VS Code on the selected paired computer. Requires user confirmation.",
        OpenApplication,
        "CONFIRM",
    ),
    "get_system_info": Tool(
        "get_system_info",
        "Read basic OS and architecture information from the selected paired computer.",
        SystemInfo,
        "SAFE",
    ),
}


def permission_for(name: str) -> str:
    return REGISTRY[name].permission if name in REGISTRY else "BLOCKED"


def validate_tool(name: str, arguments: dict):
    if permission_for(name) == "BLOCKED":
        raise AppError("tool_blocked", "This capability is blocked in THRYV.", 403)
    try:
        return REGISTRY[name], REGISTRY[name].schema.model_validate(arguments).model_dump()
    except ValidationError:
        raise AppError("invalid_tool", "The tool arguments are not allowed.", 422) from None
