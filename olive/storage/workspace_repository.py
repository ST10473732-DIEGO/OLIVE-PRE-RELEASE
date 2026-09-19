from pathlib import Path

from ..workspace import Workspace
from .json_store import JsonStore


class WorkspaceRepository:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path): self.store = JsonStore(path)

    def load_all(self) -> dict[str, Workspace]:
        value = self.store.read({"schema_version": self.SCHEMA_VERSION, "workspaces": []})
        items = [Workspace.from_dict(item) for item in value.get("workspaces", [])]
        return {item.id: item for item in items}

    def save(self, workspace: Workspace) -> None:
        values = self.load_all(); values[workspace.id] = workspace
        self.store.write({"schema_version": self.SCHEMA_VERSION, "workspaces": [item.to_dict() for item in values.values()]})

    def delete(self, workspace_id: str) -> bool:
        values = self.load_all(); removed = values.pop(workspace_id, None)
        if removed:
            self.store.write({"schema_version": self.SCHEMA_VERSION, "workspaces": [item.to_dict() for item in values.values()]})
        return bool(removed)
