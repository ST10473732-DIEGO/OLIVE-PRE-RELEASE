from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re
from threading import RLock

_SECRET = re.compile(r"(?i)(password|api[_ -]?key|token|secret)\s*[:=]\s*\S+")


class AuditService:
    def __init__(self, path: Path):
        self.path = path; self.path.parent.mkdir(parents=True, exist_ok=True); self._lock = RLock()

    def record(self, *, task_id: str, tool: str, requested_action: str, result_status: str,
               permission_decision: str, confirmation_result: str | None = None) -> None:
        record = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "task_id": task_id,
                  "tool": tool, "requested_action": _SECRET.sub(r"\1=[REDACTED]", requested_action)[:500],
                  "result_status": result_status, "permission_decision": permission_decision,
                  "confirmation_result": confirmation_result,
                  "authorized_by": "owner_task_policy" if confirmation_result == "owner_task_policy" else confirmation_result}
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_recent(self, limit: int = 100) -> list[dict]:
        if not self.path.exists(): return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-max(0, limit):]
        return [json.loads(line) for line in reversed(lines) if line.strip()]
