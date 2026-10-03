"""Persisted locations of OLIVE-owned runtimes (paths and provenance only, never secrets)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .json_store import JsonStore

SCHEMA = 'olive-runtimes/1'
FILENAME = 'runtimes.json'
# Only plain location fields are ever stored; anything else in a hand-edited file is ignored.
ALLOWED_FIELDS = {'executable', 'models', 'root', 'python', 'url', 'path'}


class RuntimeConfigRepository:
    def __init__(self, profile: Path):
        self.path = Path(profile) / FILENAME
        self.store = JsonStore(self.path)

    def load(self) -> tuple[dict[str, dict[str, Any]], bool]:
        """(entries, readable). An unreadable file is reported, never silently replaced."""
        if not self.path.exists():
            return {}, True
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}, False
        if not isinstance(value, dict) or value.get('schema') != SCHEMA or not isinstance(value.get('runtimes'), dict):
            return {}, False
        entries = {}
        for name, entry in value['runtimes'].items():
            if not isinstance(entry, dict) or not isinstance(entry.get('paths'), dict):
                continue
            paths = {k: v for k, v in entry['paths'].items() if k in ALLOWED_FIELDS and isinstance(v, str) and v}
            if paths:
                entries[str(name)] = {'paths': paths, 'origin': str(entry.get('origin', 'configured')),
                                      'adopted': bool(entry.get('adopted', False))}
        return entries, True

    def save(self, entries: dict[str, dict[str, Any]]) -> None:
        clean = {}
        for name, entry in sorted(entries.items()):
            paths = {k: str(v) for k, v in entry['paths'].items() if k in ALLOWED_FIELDS and v}
            clean[name] = {'paths': paths, 'origin': entry.get('origin', 'configured'),
                           'adopted': bool(entry.get('adopted', False))}
        self.store.write({'schema': SCHEMA, 'runtimes': clean})
