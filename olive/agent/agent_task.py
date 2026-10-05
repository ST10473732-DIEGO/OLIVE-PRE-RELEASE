from __future__ import annotations

from dataclasses import asdict, dataclass, field
from ..models import now_iso
import uuid

# One authoritative task state model for Chat, Studio and Agent.
# `waiting_for_confirmation` is the historical name the executor still uses for
# an approval prompt; it is kept so stored records and callers stay readable.
TASK_STATES = {"created", "planning", "ready", "running", "waiting_permission", "waiting_confirmation",
               "waiting_for_confirmation", "waiting_user", "paused", "stopping", "completed", "failed", "cancelled"}
TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"planning", "ready", "running", "waiting_permission", "waiting_confirmation",
                 "waiting_for_confirmation", "stopping"}
# Public, user-safe failure categories. Raw tracebacks never become a category.
FAILURE_CATEGORIES = {
    "workspace unavailable", "file changed", "build failed", "test failed", "tool unavailable",
    "application not found", "window unavailable", "control changed", "authorization required",
    "task timed out", "no progress", "preview failed", "port unavailable", "command cancelled",
    "external outcome uncertain", "model unavailable", "invalid proposal", "unsaved editor changes",
    # Desktop navigation (docs/features/desktop-navigation.md).
    "application not installed", "application did not open", "multiple windows match", "window disappeared",
    "control unavailable", "control ambiguous", "stale observation", "target not visible",
    "destination unverified", "dialog requires user", "authentication required", "captcha required",
    "desktop control unavailable", "input refused", "navigation timed out", "desktop outcome uncertain",
}
# Bounded history so a long task cannot grow its record without limit.
MAX_TIMELINE = 60
MAX_OBSERVATIONS = 30
MAX_RECEIPTS = 200


@dataclass(slots=True)
class AgentStep:
    description: str
    tool_name: str | None = None
    arguments: dict = field(default_factory=dict)
    state: str = "pending"
    result: dict | None = None
    # OLIVE-authored, never model-authored: what must be observed for success.
    step_id: str = ""
    expected: str = ""


@dataclass(slots=True)
class AgentTask:
    user_request: str
    project_id: str | None = None
    workspace_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: str = "created"
    plan: list[AgentStep] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    error: str | None = None
    completion_summary: str | None = None
    files_changed: list[str] = field(default_factory=list)
    validation_status: str = "not_run"
    implementation_status: str = "not_started"
    completion_conditions: list[str] = field(default_factory=list)
    completion_evidence: list[str] = field(default_factory=list)
    reasoning_summary: str = ""
    # --- durable task engine fields (schema 2) ---
    kind: str = "tool"
    chat_id: str | None = None
    message_id: str | None = None
    status_text: str = ""
    current_step: int = 0
    constraints: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    receipts: list[dict] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    commands: list[dict] = field(default_factory=list)
    validation: dict = field(default_factory=dict)
    preview: dict = field(default_factory=dict)
    owned_sessions: list[str] = field(default_factory=list)
    pending: dict | None = None
    failure_category: str = ""
    resume_state: dict = field(default_factory=dict)
    replans: int = 0

    def transition(self, state: str):
        if state not in TASK_STATES: raise ValueError(f"Invalid task state: {state}")
        if self.state in TERMINAL_STATES and state != self.state:
            # A finished task never silently starts executing again; resume
            # creates explicit new work from a paused/waiting state instead.
            raise ValueError(f"Task is already {self.state}")
        self.state, self.updated_at = state, now_iso()

    def note(self, text: str, status: str = "done", **evidence):
        """Factual timeline entry. Never hidden reasoning; bounded length."""
        entry = {"time": now_iso(), "status": status, "text": str(text)[:300]}
        if evidence:
            entry["evidence"] = {k: v for k, v in evidence.items() if v is not None}
        self.timeline.append(entry)
        del self.timeline[:-MAX_TIMELINE]
        self.updated_at = now_iso()
        return entry

    def observe(self, kind: str, **values):
        self.observations.append({"time": now_iso(), "kind": kind, **values})
        del self.observations[:-MAX_OBSERVATIONS]

    def fail(self, category: str, detail: str = ""):
        self.failure_category = category if category in FAILURE_CATEGORIES else "tool unavailable"
        self.error = (detail or category)[:2000]
        if self.state not in TERMINAL_STATES:
            self.transition("failed")

    @property
    def terminal(self): return self.state in TERMINAL_STATES

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls, value):
        fields = {key: value.get(key) for key in ("user_request", "project_id", "workspace_id", "id", "state", "created_at", "updated_at", "error", "completion_summary")}
        fields["plan"] = [AgentStep(**{k: v for k, v in step.items() if k in AgentStep.__dataclass_fields__}) for step in value.get("plan", [])]
        fields["tool_calls"] = list(value.get("tool_calls", []))
        fields["files_changed"] = list(value.get("files_changed", []))
        fields["validation_status"] = value.get("validation_status", "not_run")
        fields["implementation_status"] = value.get("implementation_status", "not_started")
        fields["completion_conditions"] = list(value.get("completion_conditions", []))
        fields["completion_evidence"] = list(value.get("completion_evidence", []))
        fields["reasoning_summary"] = value.get("reasoning_summary", "")
        # Schema 1 records have none of these; defaults keep them readable.
        for key, default in (("kind", "tool"), ("chat_id", None), ("message_id", None), ("status_text", ""),
                             ("current_step", 0), ("pending", None), ("failure_category", ""), ("replans", 0)):
            fields[key] = value.get(key, default)
        for key in ("constraints", "timeline", "observations", "receipts", "changes", "commands", "owned_sessions"):
            fields[key] = list(value.get(key) or [])
        for key in ("validation", "preview", "resume_state"):
            fields[key] = dict(value.get(key) or {})
        if fields["state"] not in TASK_STATES:
            fields["state"] = "failed"
        return cls(**fields)
