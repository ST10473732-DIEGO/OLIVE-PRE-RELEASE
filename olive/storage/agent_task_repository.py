from __future__ import annotations

from pathlib import Path
from ..agent.agent_task import AgentTask
from .json_store import JsonStore


class AgentTaskRepository:
    def __init__(self, path: Path): self.store = JsonStore(path)
    def load_all(self):
        value = self.store.read({"schema_version": 1, "tasks": []})
        tasks = [AgentTask.from_dict(item) for item in value.get("tasks", [])]
        return {task.id: task for task in tasks}
    def save(self, task):
        values = self.load_all(); values[task.id] = task
        self.store.write({"schema_version": 1, "tasks": [item.to_dict() for item in values.values()]})
    def recover_interrupted(self):
        values = self.load_all(); recovered = []
        for task in values.values():
            if task.state in {"planning", "running", "waiting_for_confirmation"}:
                task.transition("paused"); task.error = "Paused after application restart; review before resuming"; recovered.append(task)
        if recovered:
            self.store.write({"schema_version": 1, "tasks": [item.to_dict() for item in values.values()]})
        return recovered
