from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import EMBEDDING_MODEL, MODEL_ALIASES_FILE, MODEL_DEFAULTS_FILE, SETTINGS_FILE
from ..themes import DEFAULT_THEME
from .json_store import JsonStore


class SettingsRepository:
    def __init__(
        self,
        settings_path: Path = SETTINGS_FILE,
        defaults_path: Path = MODEL_DEFAULTS_FILE,
        aliases_path: Path = MODEL_ALIASES_FILE,
    ):
        self.settings = JsonStore(settings_path)
        self.model_defaults = JsonStore(defaults_path)
        self.model_aliases = JsonStore(aliases_path)

    def load(self) -> dict[str, Any]:
        value = self.settings.read({})
        if value.get("theme") == "DMDO Blue": value["theme"] = DEFAULT_THEME
        value.setdefault("theme", DEFAULT_THEME)
        # Only fills a missing key: a stored choice (and its existing vectors) is never replaced.
        value.setdefault("embedding_model", EMBEDDING_MODEL)
        value.setdefault("auto_rag", True)
        value.setdefault("rag_semantic_weight", 0.65)
        value.setdefault("rag_lexical_weight", 0.35)
        value.setdefault("rag_minimum_score", 0.08)
        value.setdefault("max_indexing_workers", 1)
        value.setdefault("ocr_executable", "")
        value.setdefault("automatic_memory_suggestions", True)
        value.setdefault("memory_model_extraction", False)
        value.setdefault("auto_memory_approval", False)
        value.setdefault("last_feature", "home")
        value.setdefault("window_width", 1320)
        value.setdefault("window_height", 860)
        value.setdefault("window_maximized", False)
        return value

    def save(self, value: dict[str, Any]) -> None:
        self.settings.write(value)

    def load_model_defaults(self) -> dict[str, dict[str, Any]]:
        return self.model_defaults.read({})

    def save_model_defaults(self, value: dict[str, dict[str, Any]]) -> None:
        self.model_defaults.write(value)

    def load_model_aliases(self) -> dict[str, str]:
        return self.model_aliases.read({})

    def save_model_aliases(self, value: dict[str, str]) -> None:
        self.model_aliases.write(value)
