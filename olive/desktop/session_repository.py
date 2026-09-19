from ..storage.json_store import JsonStore
from .models import DesktopControlSession


class DesktopSessionRepository:
    def __init__(self, path):
        self.store = JsonStore(path)

    def load(self):
        value = self.store.read({"schema_version": 1, "sessions": {}})
        if value.get("schema_version") != 1:
            raise ValueError("Unsupported Desktop Control session schema")
        return {key: DesktopControlSession(**item) for key, item in value["sessions"].items()}

    def save(self, session):
        sessions = self.load()
        sessions[session.id] = session
        self.store.write({"schema_version": 1, "sessions": {key: item.to_dict() for key, item in sessions.items()}})

    def recover(self):
        for session in self.load().values():
            if session.status in {"running", "waiting", "paused"}:
                session.status = "PAUSED_REVIEW_REQUIRED"
                self.save(session)
