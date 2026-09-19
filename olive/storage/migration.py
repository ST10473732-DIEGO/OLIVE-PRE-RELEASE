from __future__ import annotations

import json
import re
import shutil
import logging
from pathlib import Path

from ..config import (
    CHATS_FILE,
    LEGACY_DATA_DIR,
    MODEL_ALIASES_FILE,
    MODEL_DEFAULTS_FILE,
    SETTINGS_FILE,
    DEFAULT_SYSTEM_PROMPT,
)

_BRAND_PATTERN = re.compile(r"\bR\.?E\.?X\.?\b", re.IGNORECASE)
logger = logging.getLogger(__name__)


def _normalise_branding(value):
    if isinstance(value, str):
        return _BRAND_PATTERN.sub("OLIVE", value)
    if isinstance(value, list):
        return [_normalise_branding(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalise_branding(v) for k, v in value.items()}
    return value


def migrate_legacy_data() -> list[str]:
    """Copy legacy state into OLIVE's data directory once, without deleting the old data."""
    actions: list[str] = []
    if not LEGACY_DATA_DIR.exists():
        return actions

    legacy_chats = LEGACY_DATA_DIR / "chats.json"
    if legacy_chats.exists() and not CHATS_FILE.exists():
        try:
            payload = json.loads(legacy_chats.read_text(encoding="utf-8"))
            payload = _normalise_branding(payload)
            for chat in payload.get("chats", []):
                # If the old prompt was blank/broken, use the new OLIVE default.
                if not str(chat.get("system_prompt", "")).strip():
                    chat["system_prompt"] = DEFAULT_SYSTEM_PROMPT
            CHATS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            actions.append("Imported conversations")
        except Exception:
            logger.exception("Legacy conversation import failed")

    legacy_defaults = LEGACY_DATA_DIR / "model_defaults.json"
    if legacy_defaults.exists() and not MODEL_DEFAULTS_FILE.exists():
        shutil.copy2(legacy_defaults, MODEL_DEFAULTS_FILE)
        actions.append("Imported model defaults")

    legacy_aliases = LEGACY_DATA_DIR / "model_aliases.json"
    if legacy_aliases.exists() and not MODEL_ALIASES_FILE.exists():
        try:
            aliases = json.loads(legacy_aliases.read_text(encoding="utf-8"))
            aliases = _normalise_branding(aliases)
            MODEL_ALIASES_FILE.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
            actions.append("Imported model aliases")
        except Exception:
            logger.exception("Legacy model alias import failed")

    legacy_theme = LEGACY_DATA_DIR / "current_theme.json"
    if legacy_theme.exists() and not SETTINGS_FILE.exists():
        try:
            old = json.loads(legacy_theme.read_text(encoding="utf-8"))
            SETTINGS_FILE.write_text(
                json.dumps({"theme": old.get("theme", "OLIVE Blue")}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            actions.append("Imported theme")
        except Exception:
            logger.exception("Legacy theme import failed")

    return actions
