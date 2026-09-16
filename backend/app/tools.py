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


class WorkspaceArgs(SystemInfo):
    workspace_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class WorkspacePath(WorkspaceArgs):
    path: str = Field(min_length=1, max_length=500)


class WorkspaceSearch(WorkspaceArgs):
    query: str = Field(min_length=1, max_length=200)


class WorkspaceWrite(WorkspacePath):
    content: str = Field(max_length=48000)
    sha256: str = Field(pattern=r"^(?:[0-9a-f]{64})?$")


class DevelopmentRun(WorkspaceArgs):
    command: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,29}$")
    test_path: str = Field(default="", max_length=300)


class WorkspaceGit(WorkspaceArgs):
    operation: Literal["status", "diff", "log", "branch"]


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

for name, description, schema, permission in [
    (
        "workspace_list",
        "List bounded files in an explicitly authorized project.",
        WorkspaceArgs,
        "SAFE",
    ),
    (
        "workspace_read",
        "Read a project text file; protected secrets are withheld.",
        WorkspacePath,
        "SAFE",
    ),
    ("workspace_metadata", "Inspect project file size and content hash.", WorkspacePath, "SAFE"),
    (
        "workspace_search",
        "Search literal text in authorized project files.",
        WorkspaceSearch,
        "SAFE",
    ),
    (
        "workspace_write",
        "Create/edit one file after confirmation. Supply its read sha256 for edits; "
        "empty hash for exclusive creation. Never overwrite unreviewed changes.",
        WorkspaceWrite,
        "CONFIRM",
    ),
]:
    REGISTRY[name] = Tool(name, description, schema, permission)

REGISTRY.update(
    {
        "development_commands": Tool(
            "development_commands",
            "List locally approved development commands.",
            WorkspaceArgs,
            "SAFE",
        ),
        "development_run": Tool(
            "development_run",
            "Run an approved test/lint/type/build command in an isolated snapshot. "
            "First use development_commands and copy its exact command name; do not guess. "
            "Requires confirmation. Optional test_path selects a focused pytest node.",
            DevelopmentRun,
            "CONFIRM",
        ),
        "workspace_git": Tool(
            "workspace_git",
            "Inspect actual project Git status, diff, latest five commits or branch.",
            WorkspaceGit,
            "SAFE",
        ),
    }
)


class DevelopmentStart(WorkspaceArgs):
    command: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,29}$")
    port: int = Field(ge=1024, le=65535)


class DevelopmentStop(WorkspaceArgs):
    process_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class WorkspaceGitWrite(WorkspaceArgs):
    operation: Literal["add", "commit", "push"]
    paths: list[str] = Field(default_factory=list, max_length=20)
    message: str = Field(default="", max_length=200)
    branch: str = Field(default="", max_length=100)
    review_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


REGISTRY.update(
    {
        "workspace_open": Tool(
            "workspace_open",
            "Open the authorized project in VS Code; confirmation "
            "and window verification required.",
            WorkspaceArgs,
            "CONFIRM",
        ),
        "development_start": Tool(
            "development_start",
            "Start an approved server in an isolated namespace (no host preview port).",
            DevelopmentStart,
            "CONFIRM",
        ),
        "development_stop": Tool(
            "development_stop",
            "Stop only a THRYV-started workspace process.",
            DevelopmentStop,
            "CONFIRM",
        ),
        "development_processes": Tool(
            "development_processes",
            "Inspect THRYV-started processes and configured isolated ports.",
            WorkspaceArgs,
            "SAFE",
        ),
    }
)


REGISTRY.update(
    {
        "workspace_git_write": Tool(
            "workspace_git_write",
            "Stage explicit files, commit staged changes, or push "
            "one branch to the existing GitHub origin. Requires "
            "current review_hash from workspace_git and "
            "confirmation. Never force.",
            WorkspaceGitWrite,
            "CONFIRM",
        ),
        "workspace_git_fetch": Tool(
            "workspace_git_fetch",
            "Fetch the existing fixed GitHub origin; no arbitrary remote or credentials.",
            WorkspaceArgs,
            "SAFE",
        ),
    }
)


def permission_for(name: str) -> str:
    return REGISTRY[name].permission if name in REGISTRY else "BLOCKED"


def validate_tool(name: str, arguments: dict):
    if permission_for(name) == "BLOCKED":
        raise AppError("tool_blocked", "This capability is blocked in THRYV.", 403)
    try:
        return REGISTRY[name], REGISTRY[name].schema.model_validate(arguments).model_dump()
    except ValidationError:
        raise AppError("invalid_tool", "The tool arguments are not allowed.", 422) from None
