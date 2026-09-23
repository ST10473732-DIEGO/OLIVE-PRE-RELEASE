"""Application-side portal sessions. Imported only by the native GI helper.

Persistent grants are provisioned separately, never by this runtime.
Every request subscribes before calling, validates its path and closes on timeout.
"""
import time
import uuid

import gi

gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from olive.desktop.linux.permissions import application_id, require_authorized, STORE, STORE_PATH, TABLE, ENTRY

BUS = 'org.freedesktop.portal.Desktop'
PATH = '/org/freedesktop/portal/desktop'
PREFIX = 'org.freedesktop.portal.'


class Portal:
    def __init__(self, stopped, event):
        self.bus = Gio.DBusConnection.new_for_address_sync(
            Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None),
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
        self.app_id = application_id()
        # Register before any portal API so KDE shows OLIVE, not the parent terminal.
        self.bus.call_sync(BUS, PATH, 'org.freedesktop.host.portal.Registry', 'Register',
            GLib.Variant('(sa{sv})', (self.app_id, {})), None,
            Gio.DBusCallFlags.NONE, 3000, None)
        self.registered = True
        self.stopped, self.event = stopped, event
        self.sessions = set()
        self.requests = set()
        self.subscriptions = []
        self.shortcut = None
        self.remote = None
        self.streams = []
        self.all_streams = []
        self.stop_verified = False
        self.subscriptions.append(self.bus.signal_subscribe(
            'org.freedesktop.DBus', 'org.freedesktop.DBus', 'NameOwnerChanged',
            '/org/freedesktop/DBus', BUS, Gio.DBusSignalFlags.NONE, self._owner_changed))
        self.subscriptions.append(self.bus.signal_subscribe(
            STORE, STORE, 'Changed', STORE_PATH, None, Gio.DBusSignalFlags.NONE, self._permission_changed))
        self.subscriptions.append(self.bus.signal_subscribe(
            BUS, PREFIX + 'Session', 'Closed', None, None, Gio.DBusSignalFlags.NONE,
            self._closed))
        self.subscriptions.append(self.bus.signal_subscribe(
            BUS, PREFIX + 'GlobalShortcuts', 'Activated', PATH, None,
            Gio.DBusSignalFlags.NONE, self._activated))

    def _owner_changed(self, connection, sender, path, interface, signal, parameters):
        _, old, new = parameters.unpack()
        if old:
            self.registered = False
            self.stopped.set()
            self.remote = self.shortcut = None
            self.sessions.clear()
            self.streams = []
            self.event('portal-restarted')
        if new:
            # A new portal owner has a new Registry. Old tasks remain cancelled.
            try:
                self.bus.call_sync(BUS, PATH, 'org.freedesktop.host.portal.Registry', 'Register',
                    GLib.Variant('(sa{sv})', (self.app_id, {})), None,
                    Gio.DBusCallFlags.NONE, 3000, None)
                self.registered = True
            except GLib.Error:
                self.event('identity-unavailable')

    def _permission_changed(self, connection, sender, path, interface, signal, parameters):
        table, entry, deleted, _, permissions = parameters.unpack()
        if table == TABLE and entry == ENTRY and (deleted or permissions.get(self.app_id) != ['yes']):
            self.stopped.set()
            self.event('permission-revoked')

    def require_authorized(self):
        if not self.registered:
            raise PermissionError('The portal caller identity is unavailable')
        require_authorized(self.bus, self.app_id)

    def diagnostic(self):
        from olive.desktop.linux.permissions import lookup
        return {'app_id': self.app_id, 'peer': self.bus.get_unique_name(),
                'registered_on_portal_connection': self.registered, 'permission': lookup(self.bus, self.app_id),
                'remote_session': bool(self.remote), 'streams': self.streams}

    def _closed(self, connection, sender, path, interface, signal, parameters):
        if path in self.sessions:
            self.sessions.discard(path)
            self.stopped.set()
            if path == self.shortcut:
                self.shortcut = None
                self.stop_verified = False
                self.event('shortcut-revoked')
            else:
                self.event('revoked')

    def _activated(self, connection, sender, path, interface, signal, parameters):
        session, shortcut, *_ = parameters.unpack()
        if session == self.shortcut and shortcut == 'stop':
            # Verification is a real compositor event, never a model assertion.
            self.stop_verified = True
            self.stopped.set()
            self.event('global-stop')

    def properties(self, interface):
        return self.bus.call_sync(BUS, PATH, 'org.freedesktop.DBus.Properties',
            'GetAll', GLib.Variant('(s)', (PREFIX + interface,)),
            GLib.VariantType.new('(a{sv})'), Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]

    def call(self, interface, method, signature, args, path=PATH):
        return self.bus.call_sync(BUS, path, PREFIX + interface, method,
            GLib.Variant(signature, args), None, Gio.DBusCallFlags.NONE, 3000, None)

    def close_path(self, interface, path):
        # Asynchronous: Stop must never wait for a blocked portal roundtrip.
        self.bus.call(BUS, path, PREFIX + interface, 'Close', None, None,
                      Gio.DBusCallFlags.NONE, 1000, None, None, None)

    def request(self, interface, method, signature, args, timeout=90):
        token = 'olive_' + uuid.uuid4().hex
        options = dict(args[-1])
        options['handle_token'] = GLib.Variant('s', token)
        args = (*args[:-1], options)
        sender = self.bus.get_unique_name()[1:].replace('.', '_')
        path = PATH + '/request/' + sender + '/' + token
        result = []
        subscription = self.bus.signal_subscribe(BUS, PREFIX + 'Request', 'Response',
            path, None, Gio.DBusSignalFlags.NONE,
            lambda *values: result.append(values[-1].unpack()))
        self.requests.add(path)
        try:
            returned = self.call(interface, method, signature, args).unpack()[0]
            if returned != path:
                self.close_path('Request', returned)
                raise RuntimeError('Portal returned an unexpected request identity')
            deadline = time.monotonic() + timeout
            context = GLib.MainContext.default()
            while not result:
                if self.stopped.is_set():
                    raise InterruptedError('Desktop control stopped')
                if time.monotonic() >= deadline:
                    raise TimeoutError('Portal consent timed out: ' + interface + '.' + method)
                # GLib deadline source wakes blocking iteration without polling sleeps.
                wake = GLib.timeout_add(100, lambda: False)
                context.iteration(True)
                if GLib.MainContext.default().find_source_by_id(wake):
                    GLib.source_remove(wake)
            code, data = result[0]
            if code != 0:
                raise PermissionError('Portal consent denied or cancelled')
            return data
        finally:
            self.bus.signal_unsubscribe(subscription)
            self.requests.discard(path)
            self.close_path('Request', path)

    def create(self, interface):
        data = self.request(interface, 'CreateSession', '(a{sv})', ({
            'session_handle_token': GLib.Variant('s', 'olive_' + uuid.uuid4().hex)},))
        path = data['session_handle']
        self.sessions.add(path)
        return path

    def bind_stop(self):
        if self.shortcut:
            raise ValueError('Shortcut session already exists')
        self.shortcut = self.create('GlobalShortcuts')
        try:
            result = self.request('GlobalShortcuts', 'BindShortcuts', '(oa(sa{sv})sa{sv})',
                (self.shortcut, [('stop', {'description': GLib.Variant('s', 'Stop OLIVE desktop control'),
                  'preferred_trigger': GLib.Variant('s', 'CTRL+ALT+Escape')})], '', {}))
            shortcuts = result.get('shortcuts', [])
            bindings = [value for key, value in shortcuts if key == 'stop']
            if len(bindings) != 1:
                raise PermissionError('Global emergency shortcut was not registered')
            trigger = bindings[0].get('trigger_description', '')
            if not isinstance(trigger, str) or not trigger.strip():
                raise PermissionError('KDE did not assign a Stop key; assign a free shortcut when present')
            return {'shortcuts': shortcuts, 'trigger': trigger, 'verified': False}
        except BaseException:
            path, self.shortcut = self.shortcut, None
            self.stop_verified = False
            if path:
                self.sessions.discard(path)
                self.close_path('Session', path)
            raise

    def start(self):
        if self.remote:
            raise ValueError('A control session already exists')
        self.require_authorized()
        if self.stopped.is_set():
            raise InterruptedError('The cancelled session cannot be reused')
        self.remote = self.create('RemoteDesktop')
        try:
            self.request('RemoteDesktop', 'SelectDevices', '(oa{sv})',
                (self.remote, {'types': GLib.Variant('u', 3), 'persist_mode': GLib.Variant('u', 0)}))
            self.request('ScreenCast', 'SelectSources', '(oa{sv})',
                (self.remote, {'types': GLib.Variant('u', 1), 'multiple': GLib.Variant('b', True),
                               'cursor_mode': GLib.Variant('u', 1)}))
            result = self.request('RemoteDesktop', 'Start', '(osa{sv})', (self.remote, '', {}))
            self.streams = result.get('streams', [])
            self.all_streams = self.streams
            # KDE returns an unmapped workspace mosaic for multiple monitors
            # when multiple=False. Ask for individually mapped outputs instead.
            if len(self.streams) > 1:
                output = self.bus.call_sync('org.kde.KWin', '/KWin', 'org.kde.KWin',
                    'activeOutputName', None, GLib.VariantType.new('(s)'),
                    Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
                self.streams = [s for s in self.streams if s[1].get('mapping_id') == output]
            if result.get('devices', 0) & 3 != 3 or len(self.streams) != 1:
                raise PermissionError('One approved display and keyboard/pointer are required')
            return {**result, 'streams': self.streams}
        except BaseException:
            self.close_control()
            raise

    def fd(self, interface, method):
        if not self.remote or self.stopped.is_set():
            raise PermissionError('No active portal control session')
        response, descriptors = self.bus.call_with_unix_fd_list_sync(BUS, PATH,
            PREFIX + interface, method, GLib.Variant('(oa{sv})', (self.remote, {})),
            GLib.VariantType.new('(h)'), Gio.DBusCallFlags.NONE, 3000, None, None)
        return descriptors.get(response.unpack()[0])

    def close_control(self):
        if self.remote:
            self.close_path('Session', self.remote)
            self.sessions.discard(self.remote)
            self.remote = None
        self.streams = []

    def close(self):
        self.close_control()
        for path in tuple(self.requests):
            self.close_path('Request', path)
        for path in tuple(self.sessions):
            self.close_path('Session', path)
        self.sessions.clear()
        for subscription in self.subscriptions:
            self.bus.signal_unsubscribe(subscription)
        self.subscriptions.clear()
        self.bus.close_sync(None)
