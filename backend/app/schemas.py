from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_MESSAGE_CHARS = 8000
MAX_HISTORY_MESSAGES = 20
MAX_CONTEXT_CHARS = 32000
MAX_REPLY_CHARS = 32000

UserText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
]
HistoryText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_REPLY_CHARS)
]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Literal["user", "assistant"]
    content: HistoryText


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: UserText
    history: list[Message] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)

    @model_validator(mode="after")
    def validate_history(self):
        if len(self.history) % 2:
            raise ValueError("History must contain complete user/assistant turns")
        for i, item in enumerate(self.history):
            if item.role != ("user" if i % 2 == 0 else "assistant"):
                raise ValueError("History must alternate user and assistant messages")
            if item.role == "user" and len(item.content) > MAX_MESSAGE_CHARS:
                raise ValueError("History user message is too long")
        if sum(len(item.content) for item in self.history) + len(self.message) > MAX_CONTEXT_CHARS:
            raise ValueError("Conversation context is too large")
        return self


class ChatResponse(BaseModel):
    message: Message
    truncated: bool = False


class ConnectionResponse(BaseModel):
    provider: Literal["deepseek"] = "deepseek"
    connected: bool = True
