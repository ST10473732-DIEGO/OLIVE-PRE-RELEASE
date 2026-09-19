from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid

from .models import now_iso

JOB_STATES = {"queued", "running", "paused", "completed", "failed", "cancelled"}


@dataclass
class IndexingJob:
    chat_id: str
    document_id: str
    filename: str
    job_type: str
    version: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: str = "queued"
    progress: float = 0.0
    semantic: bool = False
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IndexingJob":
        state = data.get("state", "queued")
        return cls(
            id=data.get("id") or str(uuid.uuid4()), chat_id=str(data.get("chat_id", "")),
            document_id=str(data.get("document_id", "")), filename=str(data.get("filename", "document")),
            job_type=str(data.get("job_type", "index")), version=str(data.get("version", "unknown")),
            state=state if state in JOB_STATES else "queued", progress=float(data.get("progress", 0.0)),
            semantic=bool(data.get("semantic", False)), error=data.get("error"),
            created_at=data.get("created_at", now_iso()), updated_at=data.get("updated_at", now_iso()),
        )
