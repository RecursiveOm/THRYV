from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.errors import AppError


class OpenApplication(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    application: Literal["chrome", "vscode"]


class SystemInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


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
        raise AppError("tool_blocked", "This capability is blocked in THRYV V1.", 403)
    try:
        return REGISTRY[name], REGISTRY[name].schema.model_validate(arguments).model_dump()
    except ValidationError:
        raise AppError("invalid_tool", "The tool arguments are not allowed.", 422) from None
