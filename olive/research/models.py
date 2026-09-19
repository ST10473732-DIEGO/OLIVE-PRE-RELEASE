from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import uuid


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier():
    return str(uuid.uuid4())


ACTIVE_STATES = {"planning", "searching", "reading", "evaluating", "synthesizing"}
STATES = ACTIVE_STATES | {"created", "paused", "completed", "failed", "cancelled"}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    provider: str = ""
    rank: int = 0
    publication_date: str | None = None
    domain: str = ""


@dataclass
class PageObservation:
    url: str
    title: str
    text: str
    content_hash: str
    retrieved_at: str = field(default_factory=timestamp)
    canonical_url: str = ""
    author: str = ""
    publication_date: str | None = None
    updated_date: str | None = None
    content_type: str = "text/html"
    links: list[dict] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    trust_label: str = "untrusted_web"

    def to_dict(self):
        return asdict(self)


@dataclass
class ResearchSource:
    url: str
    title: str
    id: str = field(default_factory=identifier)
    domain: str = ""
    canonical_url: str = ""
    content_hash: str = ""
    retrieved_at: str = ""
    publication_date: str | None = None
    updated_date: str | None = None
    author: str = ""
    content_type: str = "text/html"
    status: str = "visited"
    error: str = ""
    quality: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    saved_source_id: str | None = None
    duplicate_of: str | None = None
    trust_label: str = "untrusted_web"


@dataclass
class ResearchEvidence:
    source_id: str
    subquestion: str
    claim: str
    quote: str
    start: int
    end: int
    id: str = field(default_factory=identifier)
    score: float = 0.0
    created_at: str = field(default_factory=timestamp)
    metadata: dict = field(default_factory=dict)


@dataclass
class ResearchSession:
    question: str
    id: str = field(default_factory=identifier)
    project_id: str | None = None
    status: str = "created"
    plan: dict = field(default_factory=dict)
    queries: list[dict] = field(default_factory=list)
    sources: list[ResearchSource] = field(default_factory=list)
    evidence: list[ResearchEvidence] = field(default_factory=list)
    started_at: str = field(default_factory=timestamp)
    updated_at: str = field(default_factory=timestamp)
    completed_at: str | None = None
    final_report: str = ""
    error: str = ""
    settings: dict = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)
    activity: str = "Ready"
    context: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def transition(self, status, activity=""):
        if status not in STATES:
            raise ValueError("Invalid Research state")
        self.status, self.activity, self.updated_at = status, activity, timestamp()
        if status in {"completed", "cancelled"}:
            self.completed_at = self.updated_at

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        value["sources"] = [ResearchSource(**v) for v in value.get("sources", [])]
        value["evidence"] = [ResearchEvidence(**v) for v in value.get("evidence", [])]
        session = cls(**value)
        if session.status not in STATES:
            raise ValueError("Invalid persisted Research state")
        return session


@dataclass
class SourceSubscription:
    source_id: str
    scope: dict
    project_id: str | None = None
    refresh_schedule: str = "manual"
    last_checked: str | None = None
    last_changed: str | None = None
    status: str = "disabled"
    id: str = field(default_factory=identifier)
