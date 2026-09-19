from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid

from .models import now_iso


@dataclass
class Memory:
    content: str
    category: str = "fact"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    source_chat_id: str | None = None
    source_message_index: int | None = None
    source_message_id: str | None = None
    confidence: float | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Memory":
        return cls(
            id=value.get("id") or str(uuid.uuid4()),
            content=str(value.get("content", "")).strip(),
            category=str(value.get("category", "fact")),
            created_at=value.get("created_at", now_iso()),
            updated_at=value.get("updated_at", now_iso()),
            source_chat_id=value.get("source_chat_id"),
            source_message_index=value.get("source_message_index"),
            source_message_id=value.get("source_message_id"),
            confidence=value.get("confidence"), reason=value.get("reason"),
        )
