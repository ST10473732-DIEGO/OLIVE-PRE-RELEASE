from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import uuid


@dataclass(slots=True)
class SourceProvenance:
    provider: str
    origin: str
    imported_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    retrieved_at: str | None = None
    trust_label: str = "user_provided"
    reliability_notes: str = ""


@dataclass(slots=True)
class KnowledgeSource:
    source_type: str
    title: str
    provenance: SourceProvenance
    content_hash: str
    metadata: dict = field(default_factory=dict)
    chunk_ids: list[str] = field(default_factory=list)
    version_hash: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    url: str | None = None
    canonical_url: str | None = None
    domain: str | None = None
    author: str | None = None
    publication_date: str | None = None
    updated_date: str | None = None
    retrieved_at: str | None = None
    content_type: str | None = None
    project_id: str | None = None
    research_session_id: str | None = None
    collection: str | None = None

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, value):
        copy = dict(value); copy["provenance"] = SourceProvenance(**copy["provenance"]); return cls(**copy)
