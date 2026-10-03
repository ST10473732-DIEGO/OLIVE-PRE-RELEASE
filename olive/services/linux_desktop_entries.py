"""Linux desktop entries: the visible OLIVE launcher and the hidden portal identity.

olive.desktop                  visible menu entry; Electron announces this desktop
                               name (app.setDesktopName), so Wayland/X11 windows
                               match it through StartupWMClass=olive.
local.dmdo.desktop.desktop     hidden (NoDisplay=true) compatibility entry. The KDE
                               RemoteDesktop/portal grant is keyed by the stable
                               app ID local.dmdo.desktop, and xdg-desktop-portal's
                               host Registry only accepts an ID with a matching
                               desktop file. It never appears in menus.

Templates live in packaging/linux/*.in; tests keep them identical to these renderers.
Entries are written only when absent or already OLIVE-managed: a user's own entry
is never overwritten.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .linux_startup import MARKER, quote_exec

VISIBLE = 'olive.desktop'
PLACEHOLDER = '@EXEC@'


def _app_id():
    return json.loads(Path(__file__).resolve().parents[1].joinpath('identity.json').read_text(encoding='utf-8'))['app_id']


def compatibility_name():
    return _app_id() + '.desktop'


def visible_entry(exec_value=PLACEHOLDER):
    return '\n'.join(['[Desktop Entry]', 'Type=Application', 'Name=OLIVE', 'GenericName=AI Assistant',
                      'Comment=Local-first desktop AI assistant', 'Exec=' + exec_value, 'Icon=olive',
                      'Terminal=false', 'Categories=Utility;', 'StartupNotify=true', 'StartupWMClass=olive',
                      MARKER, ''])


def compatibility_entry(exec_value=PLACEHOLDER):
    return '\n'.join(['[Desktop Entry]', 'Type=Application', 'Name=OLIVE',
                      'Comment=Desktop-control permission identity for OLIVE (compatibility entry)',
                      'Exec=' + exec_value, 'Icon=olive', 'Terminal=false', 'NoDisplay=true', MARKER, ''])


def applications_directory(data_home=None):
    configured = data_home or os.environ.get('XDG_DATA_HOME', '')
    home = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / '.local' / 'share'
    return home / 'applications'


def _write(target: Path, content: str) -> str:
    if target.is_symlink():
        raise ValueError(f'{target.name} is a link; review it without overwriting')
    if target.exists():
        current = target.read_text(encoding='utf-8', errors='replace')
        if current == content:
            return 'unchanged'
        if MARKER not in current:
            return 'kept-user-entry'  # Someone else's entry: never replaced.
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        stream.write(content)
    temporary.chmod(0o644)
    temporary.replace(target)
    return 'written'


def install(executable, data_home=None, visible=True, compatibility=True):
    """Write the entries for an absolute launcher (an AppImage file or run_olive.sh)."""
    launcher = Path(executable)
    if not launcher.is_absolute() or '/.mount_' in str(launcher):
        raise ValueError('Desktop entries need the absolute path of the AppImage or launcher, not its mount')
    exec_value = quote_exec(str(launcher))
    directory = applications_directory(data_home)
    result = {}
    if visible:
        result[VISIBLE] = _write(directory / VISIBLE, visible_entry(exec_value))
    if compatibility:
        result[compatibility_name()] = _write(directory / compatibility_name(), compatibility_entry(exec_value))
    return result


def ensure_portal_identity(environ=None):
    """Packaged Linux only: make sure the hidden portal identity entry exists before
    desktop control registers with the portal. Source checkouts use the install script."""
    from .. import app_paths
    env = os.environ if environ is None else environ
    executable = app_paths.app_executable(env)
    if not app_paths.packaged() or not executable:
        return None
    try:
        return install(executable, env.get('XDG_DATA_HOME'), visible=False)
    except (OSError, ValueError):
        return None  # Desktop control then reports its own truthful portal state.
