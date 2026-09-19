from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

RISK_LEVELS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    category: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    risk_level: str = "low"
    required_permissions: tuple[str, ...] = ()
    confirmation_required: bool = False
    timeout_seconds: float = 30.0

    def __post_init__(self):
        if not self.name or "." not in self.name: raise ValueError("Tool names must be namespaced")
        if self.risk_level not in RISK_LEVELS: raise ValueError("Invalid tool risk level")
        if self.timeout_seconds <= 0: raise ValueError("Tool timeout must be positive")

    def to_dict(self) -> dict[str, Any]: return asdict(self)

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict): raise ValueError("Tool arguments must be an object")
        missing = [key for key in self.input_schema.get("required", []) if key not in arguments]
        if missing: raise ValueError(f"Missing required tool arguments: {', '.join(missing)}")


class Tool(Protocol):
    definition: ToolDefinition
    async def execute(self, arguments: dict[str, Any], context: "ToolContext"): ...


@dataclass(slots=True)
class ToolContext:
    task_id: str
    cancellation_event: Any = None
    working_directory: str | None = None
    progress_callback: Any = None
    direct_action: Any = None
