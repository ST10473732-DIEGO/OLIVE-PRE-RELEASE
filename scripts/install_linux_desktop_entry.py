"""Install a collision-safe per-user OLIVE entry for normal launch/portal identity."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from olive.services.linux_startup import quote_exec


def install(root=ROOT, data_home=None):
    identity = json.loads((root / 'olive/identity.json').read_text())
    home = Path(data_home or os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    if not home.is_absolute():
        raise ValueError('XDG data directory must be absolute')
    target = home / 'applications' / (identity['app_id'] + '.desktop')
    content = '\n'.join(['[Desktop Entry]', 'Type=Application', 'Name=OLIVE',
        'Comment=Local-first desktop assistant', 'Terminal=false', 'X-OLIVE-Managed=true',
        'Exec=' + quote_exec(str(root / 'run_olive.sh')), 'Categories=Utility;Development;', ''])
    if target.is_symlink() or target.exists():
        if not target.is_symlink() and target.read_text() == content:
            return target
        raise ValueError('Existing desktop entry differs; review it without overwriting')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as output:
        output.write(content)
    target.chmod(0o644)
    return target


if __name__ == '__main__':
    print(install())
