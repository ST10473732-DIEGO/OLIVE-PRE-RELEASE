"""Typed, app-PID-scoped KWin window inspection/activation using its public API.

No arbitrary script endpoint. The only generated values are a validated PID,
boolean and this helper's D-Bus peer. Replies are accepted only from KWin.
"""
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
from gi.repository import Gio, GLib

SCRIPT = '''
const windows = workspace.windowList().filter(w => w.pid === PID && w.output && (w.normalWindow || w.dialog));
if (ACTIVATE && windows.length === 1) {
    windows[0].minimized = false;
    workspace.activeWindow = windows[0];
}
const result = windows.map(w => ({id:String(w.internalId), pid:w.pid,
    active:w.active, output:w.output.name, title:w.caption,
    bounds:[w.clientGeometry.x,w.clientGeometry.y,w.clientGeometry.width,w.clientGeometry.height],
    frame:[w.frameGeometry.x,w.frameGeometry.y,w.frameGeometry.width,w.frameGeometry.height]}));
callDBus(PEER, '/local/olive/WindowReply', 'local.olive.WindowReply', 'Report', JSON.stringify(result));
'''
XML = '''<node><interface name="local.olive.WindowReply"><method name="Report">
<arg type="s" direction="in"/></method></interface></node>'''


def windows(bus, pid, stopped, activate=False):
    if type(pid) is not int or pid < 1 or type(activate) is not bool:
        raise ValueError('Invalid window request')
    result = []
    owner = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
        'org.freedesktop.DBus', 'GetNameOwner', GLib.Variant('(s)', ('org.kde.KWin',)),
        None, Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
    def report(connection, sender, path, interface, method, params, invocation):
        if sender != owner or method != 'Report':
            invocation.return_dbus_error('org.freedesktop.DBus.Error.AccessDenied', 'KWin reply required')
            return
        raw = params.unpack()[0]
        if len(raw) > 16000:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.InvalidArgs', 'Excessive reply')
            return
        result.append(json.loads(raw))
        invocation.return_value(None)
    registration = bus.register_object('/local/olive/WindowReply',
        Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], report, None, None)
    name = 'olive-' + uuid.uuid4().hex
    script_id = None
    path = None
    try:
        fd, path = tempfile.mkstemp(prefix=name, suffix='.js', dir=os.environ['XDG_RUNTIME_DIR'])
        with os.fdopen(fd, 'w') as output:
            output.write(SCRIPT.replace('PID', str(pid)).replace('ACTIVATE', str(activate).lower())
                         .replace('PEER', json.dumps(bus.get_unique_name())))
        script_id = bus.call_sync('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting',
            'loadScript', GLib.Variant('(ss)', (path, name)), None,
            Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
        if script_id < 0:
            raise RuntimeError('KWin rejected the typed window helper')
        errors = []
        def ran(connection, response, _):
            try:
                connection.call_finish(response)
            except GLib.Error as error:
                errors.append(error)
        bus.call('org.kde.KWin', '/Scripting/Script' + str(script_id),
            'org.kde.kwin.Script', 'run', None, None, Gio.DBusCallFlags.NONE, 2000, None, ran, None)
        deadline = time.monotonic() + 3
        while not result:
            if errors:
                raise TimeoutError('KWin script run failed: ' + str(errors[0]))
            if stopped.is_set():
                raise InterruptedError('Window operation stopped')
            if time.monotonic() > deadline:
                raise TimeoutError('KWin window operation timed out')
            wake = GLib.timeout_add(50, lambda: False)
            GLib.MainContext.default().iteration(True)
            if GLib.MainContext.default().find_source_by_id(wake):
                GLib.source_remove(wake)
        return result[0]
    finally:
        try:
            if script_id is not None and script_id >= 0:
                bus.call_sync('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting', 'unloadScript',
                         GLib.Variant('(s)', (name,)), None, Gio.DBusCallFlags.NONE, 1000, None)
                # Plasma 6.7 allocates IDs from scripts.size() and deletes later.
                # Wait for our exact script's deletion before loading another, or
                # its deferred destruction can remove a newly reused DBus path.
                deadline = time.monotonic() + 1
                while bus.call_sync('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting',
                        'isScriptLoaded', GLib.Variant('(s)', (name,)), None,
                        Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]:
                    if time.monotonic() > deadline:
                        raise TimeoutError('KWin did not release the owned window script')
                    wake = GLib.timeout_add(20, lambda: False)
                    GLib.MainContext.default().iteration(True)
                    if GLib.MainContext.default().find_source_by_id(wake):
                        GLib.source_remove(wake)
        finally:
            bus.unregister_object(registration)
            if path:
                Path(path).unlink(missing_ok=True)



def activate_window(bus, pid, stopped):
    deadline, attempted = time.monotonic() + 5, False
    while time.monotonic() < deadline:
        found = windows(bus, pid, stopped)
        if len(found) > 1:
            raise ValueError('Multiple windows match the requested application')
        if found:
            if found[0]['active']:
                return found[0]
            if not attempted:
                windows(bus, pid, stopped, activate=True)
                attempted = True
        wake = GLib.timeout_add(100, lambda: False)
        GLib.MainContext.default().iteration(True)
        if GLib.MainContext.default().find_source_by_id(wake):
            GLib.source_remove(wake)
        if stopped.is_set():
            raise InterruptedError('Window activation stopped')
    raise TimeoutError('Requested window did not become active in KWin')
