from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

from pydantic import SecretStr


class ProviderMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Completion:
    content: str
    truncated: bool = False


class ChatProvider(Protocol):
    async def verify(self, credential: SecretStr) -> None: ...

    async def complete(
        self, credential: SecretStr, messages: list[ProviderMessage]
    ) -> Completion: ...
