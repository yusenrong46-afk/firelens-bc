"""Provider-neutral chat-turn records for the bounded tool loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatTurn:
    content: str | None
    tool_calls: tuple[ChatToolCall, ...] = ()
