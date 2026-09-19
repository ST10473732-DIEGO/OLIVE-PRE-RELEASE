from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import uuid

from .models import now_iso

WORKSPACE_TYPES = {"generic", "python", "dotnet", "node", "java", "git_repository"}


@dataclass(slots=True)
class Workspace:
    title: str
    root_path: str
    workspace_type: str = "generic"
    project_id: str | None = None
    language_hints: list[str] = field(default_factory=list)
    framework_hints: list[str] = field(default_factory=list)
    git_repository: bool = False
    preferred_terminal: str = "powershell"
    preferred_ide: str = ""
    instructions: str = ""
    trust_level: str = "approved"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=now_iso)
    last_accessed_at: str = field(default_factory=now_iso)

    def __post_init__(self):
        self.root_path = str(Path(self.root_path).expanduser().resolve(strict=False))
        if self.workspace_type not in WORKSPACE_TYPES:
            raise ValueError(f"Unsupported workspace type: {self.workspace_type}")
        if self.trust_level not in {"trusted", "approved", "untrusted"}:
            raise ValueError("Unsupported workspace trust level")

    def resolve(self, value: str | Path = ".") -> Path:
        root = Path(self.root_path)
        candidate = (root / value).resolve(strict=False) if not Path(value).is_absolute() else Path(value).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PermissionError("Path is outside the approved workspace") from exc
        return candidate

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls, value):
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value[key] for key in allowed if key in value})
