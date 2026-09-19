from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid


@dataclass(slots=True)
class ArtifactReference:
    path: str
    kind: str = "file"
    label: str | None = None


@dataclass(slots=True)
class ToolResult:
    success: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    artifacts: list[ArtifactReference] = field(default_factory=list)
    elapsed_ms: float = 0.0
    tool_call_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]: return asdict(self)

    @classmethod
    def failure(cls, summary: str, error_type: str = "ToolError", **data):
        return cls(False, summary, data, error_type)
