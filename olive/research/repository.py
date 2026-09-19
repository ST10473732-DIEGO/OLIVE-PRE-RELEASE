from pathlib import Path
from ..storage.json_store import JsonStore
from .models import ResearchSession, ACTIVE_STATES


class ResearchRepository:
    """Additive storage, separate from conversations and approved Knowledge."""

    def __init__(self, path):
        self.store = JsonStore(Path(path))

    def load_all(self):
        value = self.store.read({"schema_version": 1, "sessions": []})
        if value.get("schema_version") != 1:
            raise ValueError("Unsupported Research repository schema")
        sessions = [ResearchSession.from_dict(v) for v in value["sessions"]]
        return {s.id: s for s in sessions}

    def save(self, session):
        values = self.load_all()
        values[session.id] = session
        self.store.write({"schema_version": 1, "sessions": [s.to_dict() for s in values.values()]})
        return session

    def recover_interrupted(self):
        sessions = self.load_all()
        for session in sessions.values():
            if session.status in ACTIVE_STATES:
                for source in session.sources:
                    if source.status == "reading":
                        source.status = "visited"
                session.transition("paused", "Interrupted; resume explicitly to continue")
                self.save(session)
        return sessions
