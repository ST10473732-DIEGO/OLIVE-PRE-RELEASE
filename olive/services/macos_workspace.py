"""The verified external macOS workspace root, as the packaged native app reports it.

desktop/electron/main/index.ts finds the workspace from where the app lives, verifies its
anchor and volume identity, and exports OLIVE_MACOS_EXTERNAL_ROOT. Nothing about a
particular drive is built in. Without it (source runs, tests, other platforms) there is no
workspace, so the native macOS media engines stay unavailable instead of guessing a path.
"""
import os
from pathlib import Path

UNSET = Path('/var/empty/olive-macos-external-workspace-unset')


def external_root() -> Path:
    value = os.environ.get('OLIVE_MACOS_EXTERNAL_ROOT', '')
    return Path(value) if value and Path(value).is_absolute() else UNSET
