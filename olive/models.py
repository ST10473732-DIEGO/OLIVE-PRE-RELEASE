from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
import uuid

from .config import DEFAULT_GENERATION, DEFAULT_SYSTEM_PROMPT


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Message:
    role: str
    content: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=now_iso)
    sources: list[dict[str, Any]] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)
    grounding: dict[str, Any] | None = None
    completion_state: str = "complete"
    provider: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            id=data.get("id") or str(uuid.uuid4()),
            created_at=data.get("created_at", now_iso()),
            sources=list(data.get("sources") or []),
            memory_ids=list(data.get("memory_ids") or []),
            grounding=data.get("grounding"),
            completion_state=data.get("completion_state") if data.get("completion_state") in {"complete", "incomplete", "unverified"} else "complete",
            provider=data.get("provider", {}) if isinstance(data.get("provider", {}), dict) else {},
        )


@dataclass
class DocumentRef:
    id: str
    name: str
    kind: str = "text"
    page_count: int | None = None
    stored_path: str | None = None
    indexed: bool = False
    embedding_indexed: bool = False
    temporary: bool = False
    chunk_count: int = 0
    original_path: str | None = None
    content_hash: str | None = None
    source_size: int | None = None
    source_mtime_ns: int | None = None
    unreadable_pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentRef":
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            name=data.get("name", "document"),
            kind=data.get("kind", "text"),
            page_count=data.get("page_count"),
            unreadable_pages=[p for p in data.get("unreadable_pages", []) if type(p) is int and p > 0],
            stored_path=data.get("stored_path"),
            indexed=bool(data.get("indexed", False)),
            embedding_indexed=bool(data.get("embedding_indexed", False)),
            temporary=bool(data.get("temporary", False)),
            chunk_count=max(0, int(data.get("chunk_count", 0))),
            original_path=data.get("original_path"), content_hash=data.get("content_hash"),
            source_size=data.get("source_size"), source_mtime_ns=data.get("source_mtime_ns"),
        )


def chat_title(text: str, limit: int = 60) -> str:
    """A conversation title from its first message: one line, cut at a word boundary."""
    line = " ".join(text.split())
    if len(line) <= limit:
        return line
    cut = line[:limit - 1]
    space = cut.rfind(" ")
    if space >= limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "…"


@dataclass
class Chat:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Chat"
    model: str = ""
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    messages: list[Message] = field(default_factory=list)
    response_branches: dict[str, list[str]] = field(default_factory=dict)
    branch_index: dict[str, int] = field(default_factory=dict)
    documents: list[DocumentRef] = field(default_factory=list)
    notes: str = ""
    summary: str = ""
    summary_message_count: int = 0
    params: dict[str, Any] = field(default_factory=lambda: asdict(DEFAULT_GENERATION))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    project_id: str | None = None
    draft: str = ""
    preset: str = ""
    research_session_ids: list[str] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def add_message(self, role: str, content: str, *, sources=None, memory_ids=None, grounding=None) -> Message:
        message = Message(role=role, content=content, sources=list(sources or []),
                          memory_ids=list(memory_ids or []), grounding=grounding)
        self.messages.append(message)
        self.touch()
        return message

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "messages": [m.to_dict() for m in self.messages],
            "response_branches": self.response_branches,
            "branch_index": self.branch_index,
            "documents": [d.to_dict() for d in self.documents if not d.temporary],
            "notes": self.notes,
            "summary": self.summary,
            "summary_message_count": self.summary_message_count,
            "params": self.params,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "project_id": self.project_id,
            "draft": self.draft,
            "preset": self.preset,
            "research_session_ids": self.research_session_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chat":
        # Supports both the legacy message_branches/current_branch_index fields and OLIVE v2 fields.
        params = asdict(DEFAULT_GENERATION)
        params.update(data.get("params") or {})
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            title=data.get("title", "Untitled"),
            model=data.get("model", ""),
            system_prompt=data.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            response_branches=data.get("response_branches", data.get("message_branches", {})) or {},
            branch_index=data.get("branch_index", data.get("current_branch_index", {})) or {},
            documents=[DocumentRef.from_dict(d) for d in data.get("documents", [])],
            notes=data.get("notes", ""),
            summary=data.get("summary", ""),
            summary_message_count=max(0, int(data.get("summary_message_count", 0))),
            params=params,
            created_at=data.get("created_at", now_iso()),
            updated_at=data.get("updated_at", now_iso()),
            project_id=data.get("project_id"),
            draft=data.get("draft", "") if isinstance(data.get("draft", ""), str) else "",
            preset=data.get("preset", "") if data.get("preset", "") in {"", "fast", "normal", "max", "deep", "reimagine"} else "",
            research_session_ids=[v for v in data.get("research_session_ids", []) if isinstance(v, str)],
        )
