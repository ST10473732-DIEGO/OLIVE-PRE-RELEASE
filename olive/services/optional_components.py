"""Optional Python components installed by first-run setup (OLIVE 1.0: Playwright only).

Core never depends on them. A component lives in <user data>/components/<id> with an
OLIVE install marker, and is made importable only when setup.json records it and the
marker matches. It is appended to sys.path, so the packaged backend's own modules
always take precedence.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import stat
import sys

from .. import app_paths
from ..storage.setup_state_repository import SetupStateRepository

log = logging.getLogger(__name__)
MARKER = '.olive-install.json'


def _trusted(path: Path, entry_id: str) -> bool:
    try:
        marker = json.loads((path / MARKER).read_text(encoding='utf-8'))
        mode = path.stat().st_mode
    except (OSError, ValueError):
        return False
    # A folder anyone else may write to is never put on the import path.
    if os.name != 'nt' and mode & (stat.S_IWGRP | stat.S_IWOTH):
        return False
    return isinstance(marker, dict) and marker.get('id') == entry_id and not path.is_symlink()


def activate_path(path) -> None:
    value = str(Path(path))
    if value not in sys.path:
        sys.path.append(value)
    import importlib
    importlib.invalidate_caches()


def deactivate_path(path) -> None:
    value = str(Path(path))
    while value in sys.path:
        sys.path.remove(value)


def activate(profile, environ=None) -> list[str]:
    """Make recorded components importable; returns the entry ids activated."""
    state, readable = SetupStateRepository(Path(profile)).load()
    if not readable:
        return []
    root = Path(app_paths.user_data_root(environ)) / 'components'
    active = []
    for entry_id, record in state['installed'].items():
        if record.get('kind') != 'python-wheels':
            continue
        path = Path(record.get('path', ''))
        try:
            path.resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            log.warning('Optional component %s is outside the components folder; not activated', entry_id)
            continue
        if _trusted(path, entry_id):
            activate_path(path)
            active.append(entry_id)
    return active
