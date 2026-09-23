"""Private-pipe native helper, run with distribution Python/GObject.

No network listener, command execution service, persistent grants or auto-resume.
The stdin reader handles Stop immediately, outside inference/storage/GLib work.
"""
import json
import os
from pathlib import Path
import sys
import signal
import threading
import time

# Executed as a file by the venv host; import only this native package.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from olive.desktop.linux.portal import Portal, GLib
from olive.desktop.linux.accessibility import Accessibility
from olive.desktop.linux.geometry import approved_region
from olive.desktop.task_authority import scroll_amount


class Worker:
    def __init__(self):
        self.stopped = threading.Event()
        self.write_lock = threading.Lock()
        self.portal = Portal(self.stopped, self.event)
        self.accessibility = Accessibility()
        self.capture = self.eis = None
        self.last_heartbeat = time.monotonic()
        self.loop = GLib.MainLoop()
        signal.signal(signal.SIGUSR1, self.signal_stop)
        self.pending = threading.BoundedSemaphore(1)
        GLib.timeout_add(100, self.watchdog)

    def signal_stop(self, *_):
        self.stopped.set()
        GLib.idle_add(self.cleanup, priority=GLib.PRIORITY_HIGH)

    def emit(self, value):
        with self.write_lock:
            sys.stdout.write(json.dumps(value, ensure_ascii=True, allow_nan=False) + '\n')
            sys.stdout.flush()

    def event(self, reason):
        self.stopped.set()
        GLib.idle_add(self.cleanup, priority=GLib.PRIORITY_HIGH)
        try:
            self.emit({'event': reason})
        except (BrokenPipeError, OSError):
            GLib.idle_add(self.loop.quit, priority=GLib.PRIORITY_HIGH)

    def watchdog(self):
        if time.monotonic() - self.last_heartbeat > 2:
            self.event('lease-expired')
            self.loop.quit()
            return False
        if self.eis:
            self.eis.pump()
        return True

    def cleanup(self):
        eis, capture = self.eis, self.capture
        self.eis = self.capture = None
        try:
            if eis:
                eis.close()
        finally:
            try:
                if capture:
                    capture.close()
            finally:
                self.portal.close_control()
                self.accessibility.clear()
        return False

    def require_session(self):
        if self.stopped.is_set() or not self.portal.remote or not self.portal.stop_verified:
            raise PermissionError('No consented, Stop-verified control session')

    def dispatch(self, method, args):
        if method == 'probe':
            if args:
                raise ValueError('Unexpected probe arguments')
            return {name: self.portal.properties(name) for name in
                    ('RemoteDesktop', 'ScreenCast', 'GlobalShortcuts')}
        if method == 'bind_stop':
            if args:
                raise ValueError('Unexpected shortcut arguments')
            return self.portal.bind_stop()
        if method == 'reset':
            if args or self.portal.remote:
                raise ValueError('Cannot reset an active session')
            self.stopped.clear()
            return {'stop_verified': self.portal.stop_verified}
        if method == 'start':
            if args:
                raise ValueError('Unexpected session arguments')
            from olive.desktop.linux.capture import Capture
            from olive.desktop.linux.eis import EIS
            result = self.portal.start()
            try:
                approved_region(self.portal.streams[0][1])
                self.eis = EIS(self.portal.fd('RemoteDesktop', 'ConnectToEIS'), self.stopped, self.event, self.portal.streams[0][1])
                self.capture = Capture(self.portal.fd('ScreenCast', 'OpenPipeWireRemote'), self.portal.streams[0][0])
                return {'streams': result['streams'], 'devices': result['devices'], 'backend': 'libei'}
            except BaseException:
                self.cleanup()
                raise
        if method == 'end' and not args:
            self.cleanup()
            return {'cleanup_completed': True}
        self.require_session()
        if method == 'observe' and set(args) == {'pid'} and type(args['pid']) is int and args['pid'] > 0:
            return self.accessibility.observe(args['pid'], approved_region(self.portal.streams[0][1]))
        if method == 'capture' and not args:
            return self.capture.frame()
        required = {'revision', 'target', 'bounds', 'value'}
        if method not in {'focus', 'click', 'type', 'key', 'invoke', 'scroll'} or set(args) != required:
            raise ValueError('Unknown native action or fields')
        node = self.accessibility.check(args['revision'], args['target'], args['bounds'],
                                         approved_region(self.portal.streams[0][1]),
                                         require_focus=method in {'type', 'key'})
        # Native observation is invalid after any input, even if the call fails.
        self.accessibility.revision = ''
        if self.stopped.is_set():
            raise InterruptedError('Input stopped')
        if method == 'focus':
            if args['value'] or not node.get_component_iface().grab_focus():
                raise PermissionError('Application did not accept focus')
        elif method == 'type':
            editor = node.get_editable_text_iface()
            text = node.get_text_iface()
            value = args['value']
            if not isinstance(value, str) or len(value) > 4000 or '\x00' in value:
                raise ValueError('Invalid literal text')
            if not editor or not text or text.get_character_count() != 0:
                raise PermissionError('Composer is not empty; preserve the existing draft')
            # Semantic Unicode insertion avoids keymap guesses and clipboard changes.
            if not editor.set_text_contents(value):
                raise RuntimeError('Application rejected text')
        elif method == 'invoke':
            action = node.get_action_iface()
            names = [action.get_action_name(i) for i in range(action.get_n_actions())] if action else []
            matches = [i for i, name in enumerate(names) if name == args['value']]
            if len(matches) != 1 or not action.do_action(matches[0]):
                raise ValueError('Accessible action unavailable')
        elif method == 'click':
            if args['value']:
                raise ValueError('Unexpected click value')
            x, y, width, height = args['bounds']
            # Restrict input to the consented monitor's compositor logical rectangle.
            meta = self.portal.streams[0][1]
            origin, size = meta.get('position'), meta.get('size')
            if not origin or not size or width <= 0 or height <= 0 or not (
                    origin[0] <= x and origin[1] <= y and
                    x + width <= origin[0] + size[0] and y + height <= origin[1] + size[1]):
                raise PermissionError('Target is outside the approved display or coordinates are unavailable')
            self.eis.click(x + width / 2, y + height / 2)
        elif method == 'key':
            self.eis.key(args['value'])
        elif method == 'scroll':
            x, y, width, height = args['bounds']
            self.eis.move(x + width / 2, y + height / 2)
            self.eis.scroll(scroll_amount(args['value']))
        return {'dispatched': True, 'verified': False}

    def execute(self, message):
        try:
            if set(message) != {'id', 'method', 'arguments'} or type(message['id']) is not int or not isinstance(message['arguments'], dict):
                raise ValueError('Invalid native request')
            result = self.dispatch(message['method'], message['arguments'])
            self.emit({'id': message['id'], 'result': result})
        except Exception as error:
            # No exception repr: GI errors can contain private application text.
            self.emit({'id': message.get('id'), 'error': type(error).__name__,
                       'message': str(error)[:500] if type(error) in (ValueError, PermissionError, InterruptedError, TimeoutError) or isinstance(error, GLib.Error) and message.get('method') in {'probe', 'bind_stop', 'start'} else 'Native operation failed: ' + type(error).__name__})
        finally:
            self.pending.release()
        return False

    def read(self):
        try:
            while line := sys.stdin.buffer.readline(65537):
                if len(line) > 65536:
                    raise ValueError('Oversized native request')
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError('Native request must be an object')
                if message == {'method': 'heartbeat'}:
                    self.last_heartbeat = time.monotonic()
                elif message == {'method': 'stop'}:
                    self.event('stop')
                elif self.pending.acquire(blocking=False):
                    GLib.idle_add(self.execute, message)
                else:
                    self.emit({'id': message.get('id'), 'error': 'Busy', 'message': 'Native helper is busy'})
        finally:
            self.stopped.set()
            GLib.idle_add(self.loop.quit, priority=GLib.PRIORITY_HIGH)

    def run(self):
        threading.Thread(target=self.read, daemon=True, name='olive-native-stop').start()
        try:
            self.loop.run()
        finally:
            try:
                self.cleanup()
            finally:
                self.portal.close()


if __name__ == '__main__':
    Worker().run()
