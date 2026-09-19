from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any


class JsonStore:
    """Small atomic JSON store used for user-facing state."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def read(self, default: Any) -> Any:
        with self._lock:
            if not self.path.exists():
                return default
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return default

    def write(self, value: Any) -> None:
        with self._lock:
            payload = json.dumps(value, ensure_ascii=False, indent=2)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self.path)
