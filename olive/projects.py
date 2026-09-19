from __future__ import annotations

from dataclasses import asdict, dataclass, field
from .models import now_iso
import uuid


@dataclass(slots=True)
class Project:
    title: str
    description: str = ""
    root_folders: list[str] = field(default_factory=list)
    chat_ids: list[str] = field(default_factory=list)
    knowledge_ids: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    instructions: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls, value):
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value[key] for key in allowed if key in value})
