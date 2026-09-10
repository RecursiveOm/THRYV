from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

from pydantic import SecretStr


class ProviderMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


@dataclass(frozen=True)
class Completion:
    content: str
    truncated: bool = False
    tool_call: ToolCall | None = None


class ChatProvider(Protocol):
    async def verify(self, credential: SecretStr) -> None: ...

    async def complete(
        self, credential: SecretStr, messages: list[ProviderMessage]
    ) -> Completion: ...

    async def plan(
        self, credential: SecretStr, messages: list[ProviderMessage], tools: list[dict]
    ) -> Completion: ...
