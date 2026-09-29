from __future__ import annotations

from pathlib import Path
from ..agent.agent_task import AgentTask, ACTIVE_STATES
from .json_store import JsonStore

# Schema 2 adds durable engine fields (timeline, receipts, changes, evidence).
# Schema 1 files load unchanged: every new field has a default.
SCHEMA_VERSION = 2


class AgentTaskRepository:
    def __init__(self, path: Path): self.store = JsonStore(path)
    def load_all(self):
        value = self.store.read({"schema_version": SCHEMA_VERSION, "tasks": []})
        tasks = [AgentTask.from_dict(item) for item in value.get("tasks", [])]
        return {task.id: task for task in tasks}
    def save(self, task):
        values = self.load_all(); values[task.id] = task
        self._write(values)
    def _write(self, values):
        self.store.write({"schema_version": SCHEMA_VERSION, "tasks": [item.to_dict() for item in values.values()]})
    def for_chat(self, chat_id, limit=20):
        tasks = [t for t in self.load_all().values() if t.chat_id == chat_id]
        return sorted(tasks, key=lambda t: t.created_at)[-limit:]
    def recover_interrupted(self):
        """Never resume after a restart: reconcile receipts, then pause or wait for the user.

        Verified finished effects are recorded as done; unproven ones are marked
        uncertain and the task waits for the user instead of retrying them.
        """
        from ..agent.receipts import reconcile
        values = self.load_all(); recovered = []
        for task in values.values():
            if task.state in ACTIVE_STATES:
                summary = reconcile(task)
                task.resume_state = {**task.resume_state, "reason": "application restart", **summary}
                task.pending = None
                if summary["uncertain"]:
                    task.transition("waiting_user")
                    task.failure_category = "external outcome uncertain" if any(
                        r["effect"] == "external" and r["state"] == "uncertain" for r in task.receipts) else "file changed"
                    task.error = "Interrupted by an application restart. Some effects could not be verified; check them before continuing."
                else:
                    task.transition("paused")
                    task.error = "Paused after application restart; review before resuming"
                task.note("Interrupted by an application restart", "info",
                          verified=len(summary["verified"]), uncertain=len(summary["uncertain"]))
                recovered.append(task)
        if recovered:
            self._write(values)
        return recovered
