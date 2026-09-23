"""Owner-only installation operation; never imported by runtime/model tools.

Run with distribution Python. An exclusive private receipt preserves only OLIVE's
entry. Rollback restores that entry without deleting the table or other apps.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from olive.desktop.linux.permissions import application_id, lookup, STORE, STORE_PATH, TABLE, ENTRY
from olive.desktop.linux.portal import Portal, Gio, GLib
import threading


def provision(receipt, restore=False):
    app_id = application_id()
    from install_linux_desktop_entry import install
    install()  # Refuses replacement of a different desktop identity.
    portal = Portal(threading.Event(), lambda _: None)
    try:
        before = lookup(portal.bus, app_id)
        if restore:
            saved = json.loads(receipt.read_text())
            if saved['app_id'] != app_id or saved['table'] != TABLE or saved['entry'] != ENTRY:
                raise ValueError('Receipt identity mismatch')
            if before != ['yes']:
                raise ValueError('Permission changed after setup; refusing to overwrite it')
            previous = saved['previous']
            method, signature, args = ('DeletePermission', '(sss)', (TABLE, ENTRY, app_id)) if previous is None else (
                'SetPermission', '(sbssas)', (TABLE, True, ENTRY, app_id, previous))
            portal.bus.call_sync(STORE, STORE_PATH, STORE, method, GLib.Variant(signature, args),
                                 None, Gio.DBusCallFlags.NONE, 3000, None)
            if lookup(portal.bus, app_id) != previous:
                raise RuntimeError('Permission restoration verification failed')
            return {'app_id': app_id, 'restored': True}
        receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        saved = {'app_id': app_id, 'table': TABLE, 'entry': ENTRY, 'previous': before,
                 'registered_peer': portal.bus.get_unique_name(), 'schema': 1}
        fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(saved, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        cli = shutil.which('flatpak')
        if cli:
            subprocess.run([cli, 'permission-set', TABLE, ENTRY, app_id, 'yes'], check=True)
        else:
            portal.bus.call_sync(STORE, STORE_PATH, STORE, 'SetPermission',
                GLib.Variant('(sbssas)', (TABLE, True, ENTRY, app_id, ['yes'])),
                None, Gio.DBusCallFlags.NONE, 3000, None)
        if lookup(portal.bus, app_id) != ['yes']:
            raise RuntimeError('Named permission verification failed')
        return {**saved, 'permission': ['yes'], 'transport': 'flatpak' if cli else 'PermissionStore'}
    finally:
        portal.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(provision(args.receipt, args.restore), indent=2))
