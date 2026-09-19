from __future__ import annotations

from pathlib import Path
from ..storage.json_store import JsonStore


class TrainingExampleStore:
    """Future opt-in LoRA dataset. Examples are written only with explicit approval."""
    def __init__(self, path: Path): self.store = JsonStore(path)
    def add(self, prompt: str, response: str, *, approved: bool):
        if not approved: raise PermissionError("Training examples require explicit approval")
        value = self.store.read({"schema_version":1,"examples":[]})
        value["examples"].append({"prompt":prompt,"response":response}); self.store.write(value)
