"""Read-only runtime checks for KDE's per-application owner provisioned grant.

Writing permissions belongs exclusively to the explicitly invoked setup script.
Host Registry identities are attribution, not a same-user sandbox boundary.
"""
import json
from pathlib import Path
import re

STORE = 'org.freedesktop.impl.portal.PermissionStore'
STORE_PATH = '/org/freedesktop/impl/portal/PermissionStore'
TABLE, ENTRY = 'kde-authorized', 'remote-desktop'


def application_id():
    value = json.loads((Path(__file__).resolve().parents[2] / 'identity.json').read_text())['app_id']
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][\w-]*(?:\.[A-Za-z][\w-]*){2,}', value):
        raise ValueError('OLIVE requires its stable nonempty application ID')
    return value


def lookup(bus, app_id):
    from gi.repository import Gio, GLib
    if app_id != application_id():
        raise ValueError('Permission lookup is restricted to OLIVE')
    try:
        entries = bus.call_sync(STORE, STORE_PATH, STORE, 'Lookup',
            GLib.Variant('(ss)', (TABLE, ENTRY)), None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        return entries.get(app_id)
    except GLib.Error as error:
        if Gio.DBusError.get_remote_error(error) == 'org.freedesktop.portal.Error.NotFound':
            return None
        raise


def require_authorized(bus, app_id):
    if lookup(bus, app_id) != ['yes']:
        raise PermissionError('OLIVE KDE remote-desktop permission is absent or revoked')
