from __future__ import annotations

from pathlib import Path
from ..projects import Project
from .json_store import JsonStore


class ProjectRepository:
    def __init__(self, path: Path): self.store = JsonStore(path)
    def load_all(self):
        value = self.store.read({"schema_version": 1, "projects": []})
        projects = [Project.from_dict(item) for item in value.get("projects", [])]
        return {project.id: project for project in projects}
    def save_all(self, projects): self.store.write({"schema_version": 1, "projects": [p.to_dict() for p in projects]})
    def save(self, project):
        values = self.load_all(); values[project.id] = project; self.save_all(values.values())
    def delete(self, project_id):
        values = self.load_all(); removed = values.pop(project_id, None)
        if removed: self.save_all(values.values())
        return bool(removed)
    def resolve(self, text: str):
        lowered = text.lower(); matches = [p for p in self.load_all().values() if p.title.lower() in lowered]
        return matches[0] if len(matches) == 1 else None
