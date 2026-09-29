"""Typed, app-PID-scoped KWin window inspection/activation using its public API.

No arbitrary script endpoint. The only generated values are a validated PID,
boolean and this helper's D-Bus peer. Replies are accepted only from KWin.
"""
import json
import os
import re
from pathlib import Path
import tempfile
import time
import uuid
from gi.repository import Gio, GLib

SCRIPT = '''
const windows = workspace.windowList().filter(w => (PID > 0 ? w.pid === PID : [DESKTOP_ID, DESKTOP_ID + '.desktop'].includes(String(w.desktopFileName))) && w.output && (w.normalWindow || w.dialog));
const targets = TARGET_ID ? windows.filter(w => String(w.internalId) === TARGET_ID) : windows;
if (ACTIVATE && targets.length === 1) {
    targets[0].minimized = false;
    workspace.activeWindow = targets[0];
}
if (CLOSE && TARGET_ID && targets.length === 1 && targets[0].normalWindow && targets[0].closeable) {
    targets[0].closeWindow();
}
const onDesktop = w => w.onAllDesktops || (w.desktops || []).some(d => d === workspace.currentDesktop);
const result = windows.map(w => ({id:String(w.internalId), pid:w.pid,
    active:w.active, output:w.output.name, title:w.caption,
    normal:w.normalWindow, dialog:w.dialog, stacking:w.stackingOrder,
    minimized:!!w.minimized, fullscreen:!!w.fullScreen, on_current_desktop:onDesktop(w),
    desktops:(w.desktops || []).map(d => String(d.id)),
    transient_for:w.transientFor ? String(w.transientFor.internalId) : '',
    desktop_file:String(w.desktopFileName), resource_class:String(w.resourceClass), resource_name:String(w.resourceName),
    bounds:[w.clientGeometry.x,w.clientGeometry.y,w.clientGeometry.width,w.clientGeometry.height],
    frame:[w.frameGeometry.x,w.frameGeometry.y,w.frameGeometry.width,w.frameGeometry.height]}));
callDBus(PEER, '/local/olive/WindowReply', 'local.olive.WindowReply', 'Report', JSON.stringify(result));
'''
XML = '''<node><interface name="local.olive.WindowReply"><method name="Report">
<arg type="s" direction="in"/></method></interface></node>'''


def windows(bus, pid, stopped, activate=False, desktop_id="", target_id="", close=False):
    if target_id and (not (activate or close) or activate and close or
                      not re.fullmatch(r'\{?[0-9a-fA-F-]{36}\}?', target_id)):
        raise ValueError('Invalid window activation identity')
    if close and not target_id:
        raise ValueError('Closing requires one exact window identity')
    if desktop_id and (pid != 0 or activate or close or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", desktop_id)):
        raise ValueError("Invalid desktop application identity query")
    if type(pid) is not int or (pid < 1 and not desktop_id) or type(activate) is not bool or type(close) is not bool:
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
                         .replace('CLOSE', str(close).lower())
                         .replace('PEER', json.dumps(bus.get_unique_name())).replace('DESKTOP_ID', json.dumps(desktop_id))
                         .replace('TARGET_ID', json.dumps(target_id)))
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



def activate_window(bus, pid, stopped, purpose='exact', window_id=''):
    """Activate one window. With `window_id` the exact, already resolved window is
    used; sibling windows of the same process (for example several Firefox
    windows) are not ambiguous then. Only a dialog attached to it blocks."""
    from .window_choice import choose_window
    deadline, attempted = time.monotonic() + 5, False
    chosen_id = window_id or None
    while time.monotonic() < deadline:
        found = windows(bus, pid, stopped)
        if chosen_id:
            selected = [w for w in found if w['id'] == chosen_id]
            if len(selected) != 1:
                raise ValueError('WINDOW_DISAPPEARED: the chosen window closed during activation' if window_id
                                 else 'Window identity changed during activation')
            attached = [w for w in found if w.get('dialog') and (not window_id or w.get('transient_for') == chosen_id)]
            if attached:
                raise ValueError('DIALOG_REQUIRES_USER: the window has an open dialog' if window_id
                                 else 'Window identity changed during activation')
            chosen = selected[0]
        else:
            chosen = choose_window(found, purpose)
        if chosen:
            if chosen['active']:
                return chosen
            if not attempted:
                chosen_id = chosen['id']
                windows(bus, pid, stopped, activate=True, target_id=chosen['id'])
                attempted = True
        wake = GLib.timeout_add(100, lambda: False)
        GLib.MainContext.default().iteration(True)
        if GLib.MainContext.default().find_source_by_id(wake):
            GLib.source_remove(wake)
        if stopped.is_set():
            raise InterruptedError('Window activation stopped')
    raise TimeoutError('Requested window did not become active in KWin')


def close_window(bus, pid, window_id, stopped):
    """Ask KWin to close one exact normal window (like its title-bar button).

    The application may show its own confirmation (unsaved work); that dialog
    is left for the user. Returns whether the window is gone within 3 seconds.
    """
    before = [w for w in windows(bus, pid, stopped) if w['id'] == window_id]
    if len(before) != 1 or not before[0].get('normal'):
        raise ValueError('WINDOW_DISAPPEARED: the window to close is not open')
    windows(bus, pid, stopped, target_id=window_id, close=True)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if stopped.is_set():
            raise InterruptedError('Window operation stopped')
        remaining = windows(bus, pid, stopped)
        if not any(w['id'] == window_id for w in remaining):
            return {'closed': True, 'dialog': False}
        if any(w.get('dialog') and w.get('transient_for') == window_id for w in remaining):
            return {'closed': False, 'dialog': True}
        wake = GLib.timeout_add(100, lambda: False)
        GLib.MainContext.default().iteration(True)
        if GLib.MainContext.default().find_source_by_id(wake):
            GLib.source_remove(wake)
    return {'closed': False, 'dialog': False}
