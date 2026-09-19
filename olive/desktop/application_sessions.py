"""Application-neutral task state. Observations describe controls, never authority."""

from dataclasses import dataclass, field
from enum import Enum

from .models import timestamp


@dataclass(frozen=True)
class ApplicationIdentity:
    id: str
    display_name: str
    executable: str = ""
    package_identity: str = ""
    launch_mechanism: str = ""
    launch_target: str = ""
    adapter: str = ""
    capabilities: tuple[str, ...] = ()


class ContextTrust(str, Enum):
    USER = "user_provided"
    METADATA = "application_metadata"
    OBSERVATION = "untrusted_observation"
    SENSITIVE = "sensitive"


@dataclass(frozen=True)
class TaskValue:
    value: str
    trust: ContextTrust
    source_application: str = ""


@dataclass
class ApplicationSession:
    identity: ApplicationIdentity
    task_id: str
    window: dict = field(default_factory=dict)
    observations: list[dict] = field(default_factory=list)
    authorized_capabilities: set[str] = field(default_factory=set)
    last_verified_state: dict = field(default_factory=dict)
    status: str = "WAITING_FOR_APP"
    key: str = ""

    def observe(self, observation):
        window = observation["window"]
        if self.window and any(window.get(key) != self.window.get(key) for key in ("hwnd", "pid", "process_created")):
            self.authorized_capabilities.clear()
            self.last_verified_state.clear()
            self.status = "PAUSED_REVIEW_REQUIRED"
            raise PermissionError("Application window changed; authorization requires review")
        self.window = dict(window)
        self.observations.append({**observation, "untrusted_content": True, "observed_at": timestamp()})
        self.observations[:] = self.observations[-5:]
        self.status = "READY"


class ApplicationSessions:
    """One task may revisit many applications; switching never implies focus."""

    def __init__(self, task_id):
        self.task_id = task_id
        self.sessions = {}
        self.current = None
        self.values = {}

    def select(self, identity):
        self.sessions.setdefault(identity.id, ApplicationSession(identity, self.task_id, key=identity.id))
        return self.select_session(identity.id)

    def attach(self, identity, window):
        key = identity.id + ":" + str(window["pid"]) + ":" + str(window["hwnd"])
        if key not in self.sessions and len(self.sessions) >= 16:
            raise ValueError("Desktop task application-session limit reached")
        self.sessions.setdefault(key, ApplicationSession(identity, self.task_id, window=dict(window), key=key))
        return self.select_session(key)

    def select_session(self, key):
        session = self.sessions[key]
        session.status = "OBSERVING"
        session.last_verified_state.clear()
        self.current = key
        return session

    def put_value(self, name, value):
        if not isinstance(value, TaskValue) or not isinstance(value.trust, ContextTrust):
            raise ValueError("Cross-application values require explicit provenance")
        if len(self.values) >= 50 and name not in self.values:
            raise ValueError("Task context limit reached")
        if len(value.value) > 8192:
            raise ValueError("Task value exceeds limit")
        self.values[name] = value

    def transfer(self, name, *, sensitive_authorized=False):
        value = self.values[name]
        if value.trust == ContextTrust.SENSITIVE and not sensitive_authorized:
            raise PermissionError("Sensitive cross-application transfer requires authorization")
        return value  # Preserve provenance; never promote observations to instructions.
