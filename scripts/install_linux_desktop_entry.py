"""Install OLIVE's per-user Linux desktop entries for a source checkout.

Writes the visible olive.desktop launcher and the hidden local.dmdo.desktop.desktop
portal identity (NoDisplay=true), both starting run_olive.sh. Existing entries that
OLIVE did not write are kept untouched. Packaged builds (AppImage) carry their own
olive.desktop and add the hidden entry when desktop control first needs it.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install(root=ROOT, data_home=None):
    from olive.services.linux_desktop_entries import install as write_entries
    return write_entries(Path(root).resolve() / 'run_olive.sh', data_home)


if __name__ == '__main__':
    print(json.dumps(install(), indent=2))
