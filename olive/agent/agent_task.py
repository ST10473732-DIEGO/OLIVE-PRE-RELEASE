from __future__ import annotations

from dataclasses import asdict, dataclass, field
from ..models import now_iso
import uuid

TASK_STATES = {"created", "planning", "waiting_for_confirmation", "running", "paused", "completed", "failed", "cancelled"}


@dataclass(slots=True)
class AgentStep:
    description: str
    tool_name: str | None = None
    arguments: dict = field(default_factory=dict)
    state: str = "pending"
    result: dict | None = None


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

    def transition(self, state: str):
        if state not in TASK_STATES: raise ValueError(f"Invalid task state: {state}")
        self.state, self.updated_at = state, now_iso()

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls, value):
        fields = {key: value.get(key) for key in ("user_request", "project_id", "workspace_id", "id", "state", "created_at", "updated_at", "error", "completion_summary")}
        fields["plan"] = [AgentStep(**step) for step in value.get("plan", [])]
        fields["tool_calls"] = list(value.get("tool_calls", []))
        fields["files_changed"] = list(value.get("files_changed", []))
        fields["validation_status"] = value.get("validation_status", "not_run")
        fields["implementation_status"] = value.get("implementation_status", "not_started")
        fields["completion_conditions"] = list(value.get("completion_conditions", []))
        fields["completion_evidence"] = list(value.get("completion_evidence", []))
        fields["reasoning_summary"] = value.get("reasoning_summary", "")
        return cls(**fields)
