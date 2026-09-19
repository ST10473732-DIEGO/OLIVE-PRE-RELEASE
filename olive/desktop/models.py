"""Platform-neutral, data-only desktop targets and observations."""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import uuid


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int
    coordinate_system: str = "physical_screen_pixels"

    def contains(self, x, y):
        return self.left <= x < self.right and self.top <= y < self.bottom

    def logical_to_physical(self, x, y, dpi=96):
        if not 48 <= dpi <= 768:
            raise ValueError("Invalid DPI")
        return self.left + round(x * dpi / 96), self.top + round(y * dpi / 96)


@dataclass(frozen=True)
class WindowTarget:
    hwnd: int
    pid: int
    application: str
    executable: str = ""

    def __post_init__(self):
        if type(self.hwnd) is not int or self.hwnd <= 0 or type(self.pid) is not int or self.pid <= 0:
            raise ValueError("A concrete window handle and process are required")


@dataclass(frozen=True)
class ControlTarget:
    name: str = ""
    control_type: str = ""
    automation_id: str = ""
    runtime_id: str = ""
    parent_id: str = ""


@dataclass
class DesktopControlSession:
    task: str
    application: str = ""
    window: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "created"
    started_at: str = field(default_factory=timestamp)
    last_activity: str = field(default_factory=timestamp)
    capabilities: list[str] = field(default_factory=list)
    current_action: str = ""
    verification: str = ""
    history: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
