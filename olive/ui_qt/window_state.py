"""Non-critical desktop layout state, isolated from application repositories."""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class WindowStateStore:
    def __init__(self, path):
        self.path = Path(path)
        self.values = {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                isinstance(value, dict)
                and value.get("schema_version") == 1
                and isinstance(value.get("windows"), dict)
            ):
                self.values = value["windows"]
        except FileNotFoundError:
            self.values = {}
        except (OSError, ValueError):
            log.warning("Invalid Qt layout state; using defaults")

    def get(self, key):
        value = self.values.get(key, {})
        return value if isinstance(value, dict) else {}

    def save(self, key, value):
        self.values[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"schema_version": 1, "windows": self.values}), encoding="utf-8")
        temporary.replace(self.path)
