from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..config import MEMORIES_FILE
from ..memory import Memory
from .json_store import JsonStore


class MemoryRepository:
    SCHEMA_VERSION = 1
    def __init__(self, path: Path = MEMORIES_FILE):
        self.store = JsonStore(path)

    def load_all(self) -> dict[str, Memory]:
        payload = self.store.read({"memories": []})
        result = {}
        for value in payload.get("memories", []):
            if not isinstance(value, dict):
                continue
            memory = Memory.from_dict(value)
            if memory.content:
                result[memory.id] = memory
        return result

    def save_all(self, memories: Iterable[Memory]) -> None:
        self.store.write({"schema_version": self.SCHEMA_VERSION, "memories": [m.to_dict() for m in memories]})

    def schema_version(self) -> int:
        return int(self.store.read({"schema_version": self.SCHEMA_VERSION}).get("schema_version", self.SCHEMA_VERSION))
