from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os

from ..models import now_iso
from ..workspace import Workspace

MARKERS = {"pyproject.toml", "requirements.txt", "package.json", "pom.xml", "build.gradle", "Cargo.toml"}
IGNORED = {".git", ".venv", "venv", "node_modules", "bin", "obj", "dist", "build", "__pycache__"}


@dataclass(frozen=True, slots=True)
class WorkspaceCandidate:
    path: str
    workspace_type: str
    markers: tuple[str, ...]
    modified_at: float


class WorkspaceService:
    def __init__(self, repository): self.repository = repository

    def create(self, title: str, root_path: str | Path, project_id: str | None = None,
               instructions: str = "") -> Workspace:
        root = Path(root_path).expanduser().resolve(strict=True)
        if not root.is_dir(): raise NotADirectoryError(root)
        kind, markers = detect_workspace_type(root)
        workspace = Workspace(title, str(root), kind, project_id, language_hints=_language_hints(markers),
                              framework_hints=_framework_hints(markers), git_repository=(root / ".git").exists(),
                              instructions=instructions)
        self.repository.save(workspace); return workspace

    def touch(self, workspace: Workspace) -> None:
        workspace.last_accessed_at = now_iso(); self.repository.save(workspace)

    def discover(self, roots: list[str | Path], max_depth: int = 4, limit: int = 200) -> list[WorkspaceCandidate]:
        found: dict[str, WorkspaceCandidate] = {}
        max_depth = min(8, max(0, int(max_depth))); limit = min(1000, max(1, int(limit)))
        for supplied in roots:
            root = Path(supplied).expanduser().resolve(strict=True)
            if not root.is_dir(): continue
            for current, dirs, files in os.walk(root):
                path = Path(current); depth = len(path.relative_to(root).parts)
                dirs[:] = [name for name in dirs if name not in IGNORED and not name.startswith(".")]
                if depth >= max_depth: dirs[:] = []
                marker_names = set(files) & MARKERS
                marker_names.update(name for name in files if name.endswith((".sln", ".csproj")))
                if ".git" in set(os.listdir(path)) or marker_names:
                    kind, markers = detect_workspace_type(path)
                    found[str(path).casefold()] = WorkspaceCandidate(str(path), kind, tuple(sorted(markers)), path.stat().st_mtime)
                    dirs[:] = []
                    if len(found) >= limit: break
            if len(found) >= limit: break
        return sorted(found.values(), key=lambda item: (-item.modified_at, item.path.casefold()))

    def find(self, text: str) -> list[Workspace]:
        query = text.casefold().strip()
        values = self.repository.load_all().values()
        return sorted((item for item in values if query in item.title.casefold() or query in Path(item.root_path).name.casefold()),
                      key=lambda item: item.last_accessed_at, reverse=True)


def require_approved_workspace(repository, identifier: str) -> Workspace:
    if repository is None: raise PermissionError("An approved workspace repository is required")
    values=repository.load_all()
    if identifier in values:return values[identifier]
    requested=Path(identifier).expanduser().resolve(strict=False)
    matches=[item for item in values.values() if Path(item.root_path)==requested]
    if len(matches)!=1:raise PermissionError("Workspace has not been approved")
    return matches[0]


def detect_workspace_type(root: Path) -> tuple[str, set[str]]:
    names = {item.name for item in root.iterdir()}
    if any(name.endswith((".sln", ".csproj")) for name in names): kind = "dotnet"
    elif "pyproject.toml" in names or "requirements.txt" in names: kind = "python"
    elif "package.json" in names: kind = "node"
    elif "pom.xml" in names or "build.gradle" in names or any(name.endswith('.java') for name in names): kind = "java"
    elif ".git" in names: kind = "git_repository"
    else: kind = "generic"
    return kind, names & (MARKERS | {".git"}) | {name for name in names if name.endswith((".sln", ".csproj", ".java"))}


def _language_hints(markers: set[str]) -> list[str]:
    values=[]
    if markers & {"pyproject.toml","requirements.txt"}: values.append("python")
    if any(name.endswith((".sln",".csproj")) for name in markers): values.append("csharp")
    if "package.json" in markers: values.append("javascript")
    if markers & {"pom.xml","build.gradle"} or any(name.endswith('.java') for name in markers): values.append("java")
    return values


def _framework_hints(markers: set[str]) -> list[str]: return sorted(markers - {".git"})
