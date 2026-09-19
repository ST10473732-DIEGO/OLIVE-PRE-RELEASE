"""Explicit user-session XDG autostart; never a daemon or a model-facing tool."""
import argparse
import os
from pathlib import Path
import sys

MARKER = 'X-OLIVE-Managed=true'


def quote_exec(value):
    if any(ord(c) < 32 for c in value):
        raise ValueError('Startup paths cannot contain control characters')
    # Desktop-entry string escaping is applied after Exec argument escaping.
    escaped = ''.join('\\' + c if c in '\\"`$' else c for c in value)
    return '"' + escaped.replace('\\', '\\\\').replace('%', '%%') + '"'


def configure(enabled, root, profile, config_home=None):
    if sys.platform != 'linux':
        raise ValueError('This startup adapter is Linux-only')
    root, profile = Path(root).resolve(), Path(profile).resolve()
    launcher = root / 'run_olive.sh'
    if not launcher.is_file():
        raise ValueError('The OLIVE launcher is missing')
    configured = config_home or os.environ.get('XDG_CONFIG_HOME', '')
    home = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / '.config'
    target = home / 'autostart' / 'olive.desktop'
    if target.is_symlink() or (target.exists() and MARKER not in target.read_text()):
        raise ValueError('An unmanaged OLIVE startup entry exists; review it before changing startup')
    if not enabled:
        target.unlink(missing_ok=True)
        return target
    content = '\n'.join(['[Desktop Entry]', 'Type=Application', 'Name=OLIVE',
        'Comment=Launch OLIVE in your desktop session', 'Terminal=false', MARKER,
        'Exec=/usr/bin/env ' + quote_exec('OLIVE_DATA_DIR=' + str(profile)) + ' ' + quote_exec(str(launcher)), ''])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.desktop.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        stream.write(content)
    temporary.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'disable'])
    args = parser.parse_args()
    from ..identity import resolve_profile
    target = configure(args.action == 'enable', Path(__file__).resolve().parents[2], resolve_profile())
    print(f'OLIVE launch at login {args.action}d: {target}')


if __name__ == '__main__':
    main()
