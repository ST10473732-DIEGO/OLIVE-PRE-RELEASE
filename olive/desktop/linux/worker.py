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
from olive.desktop.linux.accessibility import Accessibility, ObservationAborted
from olive.desktop.linux.geometry import approved_region
from olive.desktop.linux.monitors import FrameSpace, Layout, Monitor, WindowCrop, input_point, inside
from olive.desktop.task_authority import scroll_amount
from olive.desktop.key_policy import key_codes, canonical



# Requests that only observe; every other request may change the screen.
READ_ONLY = frozenset({'diagnostic', 'probe', 'visual_observe', 'capture', 'observe', 'browser_chrome',
                       'document_locations', 'application_windows', 'monitors'})
BROWSER_KEYS = {'back': 'Alt+Left', 'forward': 'Alt+Right', 'reload': 'Ctrl+R', 'new_tab': 'Ctrl+T',
                'close_tab': 'Ctrl+W', 'reopen_tab': 'Ctrl+Shift+T', 'find': 'Ctrl+F', 'next': 'Ctrl+PageDown', 'previous': 'Ctrl+PageUp',
                'page_up': 'PageUp', 'page_down': 'PageDown', 'escape': 'Escape'}
# Only chrome fields whose content is navigation text may be replaced (never a draft).
REPLACEABLE = ('search', 'address', 'find', 'location', 'url', 'filter')

class Worker:
    def __init__(self):
        import fcntl
        runtime = Path(os.environ['XDG_RUNTIME_DIR'])
        if runtime.stat().st_uid != os.getuid() or runtime.stat().st_mode & 0o077:
            raise PermissionError('A private user runtime directory is required')
        self.input_lock = os.open(runtime / 'olive-desktop-input.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        fcntl.flock(self.input_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.stopped = threading.Event()
        self.write_lock = threading.Lock()
        self.portal = Portal(self.stopped, self.event)
        self.accessibility = Accessibility()
        self.capture = self.eis = None
        self.window = None
        self.browser_search = None
        self.visual_frame = None
        self.editor_stage = None
        self.editor_ownership = None
        self.file_input = None
        self.last_heartbeat = time.monotonic()
        self.last_input = None  # When the last state-changing request finished.
        self.stop_deadline = None
        self.session_deadline = None
        self.loop = GLib.MainLoop()
        signal.signal(signal.SIGUSR1, self.signal_stop)
        self.pending = threading.BoundedSemaphore(1)
        GLib.timeout_add(100, self.watchdog)

    def signal_stop(self, *_):
        self.stopped.set()
        self.stop_deadline = time.monotonic() + .5
        GLib.idle_add(self.cleanup, priority=GLib.PRIORITY_HIGH)

    def emit(self, value):
        with self.write_lock:
            sys.stdout.write(json.dumps(value, ensure_ascii=True, allow_nan=False) + '\n')
            sys.stdout.flush()

    def event(self, reason):
        self.stopped.set()
        self.stop_deadline = time.monotonic() + .5
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
                self.window = None
                self.editor_ownership = None
                self.browser_search = None
                self.visual_frame = None
                self.editor_stage = None
                self.file_input = None
                self.stop_deadline = None
                self.session_deadline = None
        return False

    def require_session(self):
        if self.stopped.is_set() or not self.portal.remote:
            raise PermissionError('No active authorized control session')
        if self.session_deadline is None or time.monotonic() >= self.session_deadline:
            self.event('task-lease-expired')
            raise PermissionError('The finite input lease expired')
        self.require_unlocked()
        self.portal.require_authorized()

    def require_unlocked(self):
        from gi.repository import Gio
        locked = self.portal.bus.call_sync('org.freedesktop.ScreenSaver', '/ScreenSaver',
            'org.freedesktop.ScreenSaver', 'GetActive', None, GLib.VariantType.new('(b)'),
            Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
        if locked:
            self.event('session-locked')
            raise PermissionError('The desktop session is locked')

    def layout(self):
        """The consented monitors as one layout (portal stream geometry is logical)."""
        monitors = []
        for _, meta in self.portal.all_streams or []:
            position, size, name = meta.get('position'), meta.get('size'), meta.get('mapping_id')
            if position is not None and size is not None and name:
                monitors.append(Monitor(str(name), *position, *size))
        return Layout(tuple(monitors)) if monitors else None

    def bound(self, keys=('id', 'pid', 'bounds', 'output')):
        """The task's bound window, unchanged and active, or an error (never a sibling window)."""
        from olive.desktop.linux.kwin import windows
        if not self.window:
            raise PermissionError('No window is bound to this task; observe again')
        found = [w for w in windows(self.portal.bus, self.window['pid'], self.stopped) if w['id'] == self.window['id']]
        if len(found) != 1:
            raise PermissionError('WINDOW_DISAPPEARED: the bound window closed; nothing was sent')
        if not found[0]['active'] or any(found[0][k] != self.window[k] for k in keys):
            raise PermissionError('Compositor focus or window geometry changed; observe again')
        return found[0]

    def active_window(self, pid):
        """The one active window of `pid`; when a window is bound it must be that one."""
        from olive.desktop.linux.kwin import windows
        found = [w for w in windows(self.portal.bus, pid, self.stopped) if w['active']]
        if len(found) != 1 or not found[0]['active']:
            raise PermissionError('Requested window lost focus')
        if self.window and self.window.get('pid') == pid and found[0]['id'] != self.window['id']:
            raise PermissionError('WINDOW_CHANGED: another window of the application is focused; observe again')
        return found[0]

    def dispatch(self, method, args):
        if method == 'diagnostic' and not args:
            return self.portal.diagnostic()
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
            self.require_unlocked()
            self.session_deadline = time.monotonic() + 240
            result = self.portal.start()
            try:
                try:
                    approved_region(self.portal.streams[0][1])
                except PermissionError:
                    meta = self.portal.streams[0][1]
                    safe = {key: meta.get(key) for key in ('position', 'size', 'source_type', 'mapping_id')}
                    raise PermissionError('Portal stream geometry unavailable: ' + json.dumps(safe)) from None
                self.eis = EIS(self.portal.fd('RemoteDesktop', 'ConnectToEIS'), self.stopped, self.event, self.portal.streams[0][1])
                self.capture = Capture(self.portal.fd('ScreenCast', 'OpenPipeWireRemote'), self.portal.streams[0][0], self.portal.streams[0][1]['size'])
                frame = self.capture.frame()
                return {'streams': result['streams'], 'devices': result['devices'], 'backend': 'libei',
                        'identity': self.portal.diagnostic(),
                        'frame': {key: frame[key] for key in ('width', 'height', 'original_width', 'original_height', 'pts')}}
            except BaseException:
                self.cleanup()
                raise
        if method == 'end' and not args:
            self.cleanup()
            return {'cleanup_completed': True}
        self.require_session()
        if method == 'file_begin' and set(args) == {'source', 'destination', 'operation'}:
            from olive.desktop.linux.file_input import FileInput
            if self.file_input or not self.window:
                raise PermissionError('A unique active file task is required')
            self.file_input = FileInput(**args)
            return {'ready': True}
        if method == 'file_step' and set(args) == {'step', 'value'} and self.file_input:
            return self.file_input.step(self, **args)
        if method == 'application_windows' and set(args) == {'desktop_id'}:
            from olive.desktop.linux.kwin import windows
            return windows(self.portal.bus, 0, self.stopped, desktop_id=args['desktop_id'])
        if method == 'monitors' and not args:
            layout = self.layout()
            return {'monitors': [dict(name=m.name, geometry=list(m.bounds)) for m in layout.monitors] if layout else [],
                    'mapped': self.eis.mapping_id if self.eis else ''}
        if (method == 'activate' and set(args) in ({'pid', 'purpose'}, {'pid', 'purpose', 'window_id'}) and
                type(args['pid']) is int and args['pid'] > 0 and args['purpose'] in {'exact','open','new_document','visual'}
                and isinstance(args.get('window_id', ''), str)):
            from olive.desktop.linux.kwin import activate_window
            from olive.desktop.linux.capture import Capture
            visual = args['purpose'] == 'visual'
            self.window = None  # A new activation rebinds; nothing earlier stays valid.
            window = activate_window(self.portal.bus, args['pid'], self.stopped,
                                     purpose='exact' if visual else args['purpose'], window_id=args.get('window_id', ''))
            streams = [s for s in self.portal.all_streams if s[1].get('mapping_id') == window['output']]
            if len(streams) != 1:
                raise PermissionError('Requested window output is not mapped to a portal stream')
            if streams != self.portal.streams:
                self.capture.close()
                self.portal.streams = streams
                self.eis.mapping_id = streams[0][1]['mapping_id']
                self.eis.region = approved_region(streams[0][1])
                self.capture = Capture(self.portal.fd('ScreenCast', 'OpenPipeWireRemote'), streams[0][0], streams[0][1]['size'])
            self.window = window
            if visual:
                # Visual-only clients: KWin's active exact window is the evidence; no
                # wait for accessibility activation events they do not emit.
                return {'active': True, 'accessible': False, 'window_id': window['id'], 'bounds': window['bounds'], 'output': window['output'], 'input_region': list(self.eis.region), 'mapping_id': self.eis.mapping_id}
            try:
                self.accessibility.bind_geometry(args['pid'], window['bounds'])
                # With an exact KWin window binding, sibling windows of the same
                # process are expected; the compositor already verified which one is active.
                self.accessibility.activate(args['pid'], approved_region(self.portal.streams[0][1]), self.stopped,
                                            allow_active_window=args['purpose'] != 'exact' or bool(args.get('window_id')))
                return {'active': True, 'accessible': True, 'window_id': window['id'], 'bounds': window['bounds'], 'output': window['output'], 'input_region': list(self.eis.region), 'mapping_id': self.eis.mapping_id}
            except (LookupError, TimeoutError):
                # An inaccessible Chromium frame is not evidence that KWin lost
                # focus. Recheck independently before allowing the visual route.
                from olive.desktop.linux.kwin import windows
                current = [w for w in windows(self.portal.bus, args['pid'], self.stopped) if w['active']]
                if len(current) != 1 or not current[0]['active'] or current[0]['id'] != window['id'] or current[0]['bounds'] != window['bounds']:
                    raise PermissionError('Application focus or geometry changed during accessibility discovery')
                return {'active': True, 'accessible': False, 'window_id': window['id'], 'bounds': window['bounds'], 'output': window['output'], 'input_region': list(self.eis.region), 'mapping_id': self.eis.mapping_id}
        if method == 'visual_observe' and set(args) == {'pid'}:
            from olive.desktop.linux.kwin import windows
            from olive.desktop.linux.geometry import contains
            import base64
            import io
            from PIL import Image
            try:
                found = [self.active_window(args['pid'])]
            except PermissionError as error:
                raise PermissionError('Visual target lost focus or became ambiguous' if 'lost focus' in str(error)
                                      else str(error)) from None
            region = approved_region(self.portal.streams[0][1])
            if not contains(region, found[0]['bounds']):
                raise PermissionError('Visual target left the mapped display (WINDOW_OFF_MONITOR: it is not entirely '
                                      'on the monitor being observed)')
            frame = self.capture.frame(since=self.last_input)
            crop = FrameSpace(tuple(region), int(frame['width']), int(frame['height'])).crop(found[0]['bounds'])
            left, top, right, bottom = crop.box
            with Image.open(io.BytesIO(base64.b64decode(frame['png']))) as image:
                cropped = image.crop((left, top, right, bottom))
                data = io.BytesIO()
                cropped.save(data, format='PNG')
            self.window = found[0]
            import uuid
            result = {**frame, 'png': base64.b64encode(data.getvalue()).decode(),
                    'width': right-left, 'height': bottom-top, 'crop_origin': [left, top], 'window': self.window,
                    'crop': crop.describe(), 'monitor': self.portal.streams[0][1].get('mapping_id', '')}
            result['revision'] = uuid.uuid4().hex
            self.visual_frame = result
            return result
        if method == 'visual_click' and set(args) == {'revision', 'point'}:
            frame, self.visual_frame = self.visual_frame, None
            if not frame or args['revision'] != frame['revision'] or time.monotonic()-frame['captured_at'] > 10:
                raise ValueError('Stale visual observation')
            if any(frame['window'][k] != self.window[k] for k in ('id', 'bounds', 'output', 'title')):
                raise PermissionError('Visual target focus or geometry changed')
            try:
                self.bound(keys=('id', 'bounds', 'output', 'title'))
            except PermissionError:
                raise PermissionError('Visual target focus or geometry changed') from None
            point = args['point']
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError('Invalid visual point')
            # Crop pixels -> global logical through the one coordinate module; the
            # point must stay inside the bound window and the consented monitor.
            point = WindowCrop.restore(frame['crop']).to_logical(*point)
            # The coordinate fallback is bound to this window, frame revision and geometry.
            from olive.desktop.observation_revision import CoordinateTarget, Observation
            CoordinateTarget(frame['window']['id'], frame['revision'], tuple(frame['window']['bounds']), point).check(
                Observation(frame['revision'], self.window['id'], self.window['pid'], '', tuple(self.window['bounds']),
                            self.window['output'], '', ''))
            input_point(self.layout(), self.eis.region, point)
            self.eis.click(*point)
            return {'dispatched': True}
        if method in {'visual_text', 'visual_key'} and set(args) == {'revision', 'value'}:
            # Visual-only clients: literal text into the focused field, or one key
            # from a fixed allowlist. Requires the latest unconsumed frame of the
            # same pinned window; the runtime binds values to the task scope.
            frame, self.visual_frame = self.visual_frame, None
            if not frame or args['revision'] != frame['revision'] or time.monotonic()-frame['captured_at'] > 10:
                raise ValueError('Stale visual observation')
            if any(frame['window'][k] != self.window[k] for k in ('id', 'bounds', 'output', 'title')):
                raise PermissionError('Visual target focus or geometry changed')
            try:
                self.bound(keys=('id', 'bounds', 'output', 'title'))
            except PermissionError:
                raise PermissionError('Visual target focus or geometry changed') from None
            value = args['value']
            if method == 'visual_text':
                if not isinstance(value, str) or not 1 <= len(value) <= 4000 or any(ord(c) < 32 for c in value):
                    raise ValueError('Invalid literal text')
                self.eis.text(value)
            elif value in {'ctrl+k', 'Enter', 'Escape'}:
                self.eis.chord_codes(key_codes(canonical(value), 'messaging'))
            else:
                raise ValueError('Unsupported visual key')
            return {'dispatched': True}
        if method == 'browser_visit' and set(args) in ({'pid', 'url'}, {'pid', 'url', 'new_tab'}):
            from olive.desktop.browser_url import validated_url
            if not self.window or self.window['pid'] != args['pid'] or type(args.get('new_tab', True)) is not bool:
                raise PermissionError('Browser window is not bound')
            steps = (('new_tab',) if args.get('new_tab', True) else ()) + ('address', 'type_query', 'submit')
            self.browser_search = {'query': validated_url(args['url']), 'stage': 0, 'visit': True, 'steps': steps}
            return {'ready': True, 'steps': list(steps)}
        if method == 'browser_begin' and set(args) in ({'pid', 'query'}, {'pid', 'query', 'new_tab'}):
            if not self.window or self.window['pid'] != args['pid'] or not isinstance(args['query'], str) or not 1 <= len(args['query']) <= 2000 or any(ord(c) < 32 for c in args['query']) or type(args.get('new_tab', True)) is not bool:
                raise ValueError('Invalid browser search scope')
            steps = (('new_tab',) if args.get('new_tab', True) else ()) + ('address', 'type_query', 'submit')
            self.browser_search = {'query': args['query'], 'stage': 0, 'steps': steps}
            return {'ready': True, 'steps': list(steps)}
        if method == 'browser_navigation' and set(args) in ({'operation', 'direction'}, {'operation', 'direction', 'bounds'}):
            try:
                self.bound(keys=('id', 'bounds', 'output'))
            except PermissionError as error:
                raise PermissionError('Browser focus or geometry changed' if 'geometry' in str(error) else str(error)) from None
            operation, direction = args['operation'], args['direction']
            if operation == 'tab' and direction in {'next', 'previous'}:
                self.eis.chord_codes(key_codes(BROWSER_KEYS[direction], 'browser'))
            elif operation == 'browse' and direction in BROWSER_KEYS:
                self.eis.chord_codes(key_codes(BROWSER_KEYS[direction], 'browser'))
            elif operation == 'history' and direction in {'back', 'forward'}:
                self.eis.chord_codes(key_codes(BROWSER_KEYS[direction], 'file_manager'))
            elif operation == 'scroll' and direction in {'up', 'down'}:
                # Scroll the verified container (the page document by default),
                # never another pane: the pointer goes to its centre first.
                area = args.get('bounds') or [self.window['bounds'][0], self.window['bounds'][1] + self.window['bounds'][3] * .4,
                                              self.window['bounds'][2], self.window['bounds'][3] * .6]
                if not inside(self.window['bounds'], area):
                    raise PermissionError('INPUT_REFUSED: the scroll container is outside the bound window')
                x, y, width, height = area
                point = input_point(self.layout(), self.eis.region, (x + width / 2, y + height / 2))
                self.eis.move(*point)
                self.eis.scroll(480 if direction == 'down' else -480)
            else:
                raise ValueError('Unknown browser navigation')
            return {'dispatched': True}
        if method == 'replace_text' and set(args) == {'revision', 'target', 'bounds', 'value'}:
            # Navigation text into a focused *chrome* search/address/find field only.
            self.bound(keys=('id', 'pid', 'bounds', 'output'))
            node = self.accessibility.check(args['revision'], args['target'], args['bounds'],
                                            approved_region(self.portal.streams[0][1]), require_focus=True)
            value = args['value']
            if not isinstance(value, str) or not 1 <= len(value) <= 2000 or any(ord(c) < 32 for c in value):
                raise ValueError('Invalid navigation text')
            if not any(word in (node.get_name() or '').casefold() for word in REPLACEABLE) or \
                    self.accessibility.in_document(node):
                raise PermissionError('INPUT_REFUSED: only a browser search, address or find field can be replaced')
            self.accessibility.revision = ''
            from gi.repository import Atspi
            editor, text = node.get_editable_text_iface(), node.get_text_iface()
            accepted = bool(editor and editor.set_text_contents(value) and text and
                            Atspi.Text.get_text(text, 0, min(text.get_character_count(), 2001)) == value)
            if not accepted:
                # Some chrome inputs (Firefox's find bar) report success without changing.
                # The verified field still has focus: select its own text and type once.
                self.eis.chord_codes(key_codes('Ctrl+A', 'field'))
                self.eis.text(value)
            return {'dispatched': True, 'method': 'semantic' if accepted else 'keys'}
        if method == 'show_folder' and set(args) == {'uri'}:
            from urllib.parse import unquote, urlsplit
            from gi.repository import Gio
            uri = args['uri']
            parsed = urlsplit(uri) if isinstance(uri, str) else None
            if (not parsed or parsed.scheme != 'file' or parsed.netloc or len(uri) > 2000 or
                    any(ord(c) < 32 for c in uri) or not os.path.isdir(unquote(parsed.path))):
                raise ValueError('Invalid folder location')
            self.portal.bus.call_sync('org.freedesktop.FileManager1', '/org/freedesktop/FileManager1',
                'org.freedesktop.FileManager1', 'ShowFolders', GLib.Variant('(ass)', ([uri], '')),
                None, Gio.DBusCallFlags.NONE, 5000, None)
            return {'dispatched': True}
        if method == 'close_window' and set(args) == {'window_id'}:
            from olive.desktop.linux.kwin import close_window
            if not self.window or self.window['id'] != args['window_id']:
                raise PermissionError('Only the bound window can be closed')
            result = close_window(self.portal.bus, self.window['pid'], args['window_id'], self.stopped)
            if result['closed']:
                self.window = None
                self.accessibility.clear()
            return result
        if method == 'browser_step' and set(args) == {'step'}:
            from olive.desktop.linux.kwin import windows
            search = self.browser_search
            steps = search.get('steps', ('new_tab', 'address', 'type_query', 'submit')) if search else ()
            if not search or search['stage'] >= len(steps) or args['step'] != steps[search['stage']]:
                raise PermissionError('Browser step is stale or outside this task')
            try:
                self.bound(keys=('id', 'pid', 'bounds', 'output'))
            except PermissionError as error:
                raise PermissionError('Browser focus or geometry changed' if 'geometry' in str(error) else str(error)) from None
            search['stage'] += 1  # Never replay a partially dispatched effect.
            if args['step'] == 'type_query':
                self.eis.text(('' if search.get('visit') else '? ') + search['query'])
            else:
                self.eis.browser_key(args['step'])
            return {'dispatched': True}
        if (method in {'observe', 'browser_chrome', 'document_locations'} and set(args) in ({'pid'}, {'pid', 'item'})
                and type(args['pid']) is int and args['pid'] > 0 and
                (method == 'observe' or 'item' not in args) and
                isinstance(args.get('item', ''), str) and len(args.get('item', '')) <= 255):
            self.window = self.active_window(args['pid'])
            self.accessibility.bind_geometry(args['pid'], self.window['bounds'])
            region = approved_region(self.portal.streams[0][1])
            if method == 'document_locations':
                return self.accessibility.document_locations(args['pid'], region)
            return self.accessibility.observe(args['pid'], region, chrome_only=method == 'browser_chrome',
                                              item=args.get('item', ''))
        if method == 'editor_session' and set(args) == {'pid', 'created'}:
            import psutil
            from olive.desktop.linux.editor_ownership import EditorOwnership
            process = psutil.Process(args['pid'])
            if (not self.window or self.window['pid'] != args['pid'] or
                    process.create_time() != args['created'] or process.uids().real != os.getuid() or
                    time.time() - args['created'] > 30 or self.editor_stage is not None):
                raise PermissionError('Isolated editor process lifetime is not verified')
            self.editor_ownership = EditorOwnership(args['pid'], args['created'], self.window['id'], True)
            return {'bound': True}
        if method == 'editor_key' and set(args) == {'step'}:
            from olive.desktop.linux.kwin import windows
            step = args['step']
            if step != ('new_document' if self.editor_stage is None else 'save_as' if self.editor_stage in {'new_document', 'text_entered'} else ''):
                raise PermissionError('Editor operation is stale or out of scope')
            current = [w for w in windows(self.portal.bus, self.window['pid'], self.stopped) if w['active']]
            if len(current) != 1 or current[0]['id'] != self.window['id']:
                raise PermissionError('Editor focus changed')
            if step == 'save_as' and self.editor_ownership:
                self.editor_ownership.expect_save(windows(self.portal.bus, self.window['pid'], self.stopped))
            self.editor_stage = step
            self.eis.editor_key(step)
            return {'dispatched': True}
        if method == 'editor_paste' and not args:
            from olive.desktop.linux.kwin import windows
            if self.editor_stage != 'new_document':
                raise PermissionError('Paste requires a fresh new document')
            current = [w for w in windows(self.portal.bus, self.window['pid'], self.stopped) if w['active']]
            if len(current) != 1 or current[0]['id'] != self.window['id'] or 'untitled' not in current[0]['title'].casefold():
                raise PermissionError('The new untitled editor is not active')
            self.editor_stage = 'text_entered'
            self.eis.chord_codes([29, 47])  # Ctrl+V; regular clipboard, never PRIMARY.
            return {'dispatched': True}
        if method == 'editor_text' and set(args) == {'value'}:
            from olive.desktop.linux.kwin import windows
            if self.editor_stage != 'new_document':
                raise PermissionError('A fresh new document is required')
            current = [w for w in windows(self.portal.bus, self.window['pid'], self.stopped) if w['active']]
            if len(current) != 1 or current[0]['id'] != self.window['id'] or 'untitled' not in current[0]['title'].casefold():
                raise PermissionError('The new untitled editor is not active')
            self.editor_stage = 'text_entered'
            self.eis.text(args['value'])
            return {'dispatched': True}
        if method == 'filename' and set(args) == {'revision', 'target', 'bounds', 'value'}:
            if self.editor_stage != 'save_as':
                raise PermissionError('No new-document Save As operation is active')
            node = self.accessibility.check(args['revision'], args['target'], args['bounds'],
                approved_region(self.portal.streams[0][1]), require_focus=True)
            from olive.desktop.linux.kwin import windows
            active = [w for w in windows(self.portal.bus, self.window['pid'], self.stopped) if w['active']]
            if len(active) != 1 or any(active[0][k] != self.window[k] for k in ('id', 'bounds', 'output')):
                raise PermissionError('Save dialog focus or geometry changed')
            if self.editor_ownership:
                import psutil
                controls = self.accessibility.observe(self.window['pid'], approved_region(self.portal.streams[0][1]))['controls']
                self.editor_ownership.admit(active[0], psutil.Process(self.window['pid']).create_time(), controls)
            if not any(label.strip().casefold().rstrip(':') in {'file name', 'filename', 'name'}
                       for label in [node.get_name(), *self.accessibility.labels(node)]):
                raise PermissionError('Only the save dialog filename can be replaced')
            value = args['value']
            if not isinstance(value, str) or not Path(value).is_absolute() or Path(value).exists() or '\x00' in value:
                raise PermissionError('An unused absolute destination is required')
            self.accessibility.revision = ''
            editor = node.get_editable_text_iface()
            if editor:
                if not editor.set_text_contents(value):
                    raise ValueError('The file picker rejected the destination')
            else:
                self.eis.chord_codes([29, 30])  # Select only the verified filename field.
                self.eis.text(value)
            return {'dispatched': True}
        if method == 'capture' and not args:
            return self.capture.frame(since=self.last_input)
        required = {'revision', 'target', 'bounds', 'value'}
        if method not in {'focus', 'click', 'type', 'key', 'invoke', 'scroll'} or set(args) != required:
            raise ValueError('Unknown native action or fields')
        self.bound(keys=('id', 'pid', 'bounds', 'output'))
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
            self.accessibility.hit_test(node, x + width / 2, y + height / 2)
            input_point(self.layout(), self.eis.region, (x + width / 2, y + height / 2))
            self.eis.click(x + width / 2, y + height / 2)
        elif method == 'key':
            name = canonical(args['value'])
            if name is None:
                raise ValueError('Unsupported key; commands and arbitrary chords are not accepted')
            self.eis.chord_codes(key_codes(name))
        elif method == 'scroll':
            x, y, width, height = args['bounds']
            self.eis.move(x + width / 2, y + height / 2)
            self.eis.scroll(scroll_amount(args['value']))
        return {'dispatched': True, 'verified': False}

    def execute(self, message):
        try:
            if set(message) != {'id', 'method', 'arguments'} or type(message['id']) is not int or not isinstance(message['arguments'], dict):
                raise ValueError('Invalid native request')
            try:
                result = self.dispatch(message['method'], message['arguments'])
            finally:
                if message['method'] not in READ_ONLY:
                    # A later screen read must postdate this request's effects.
                    self.last_input = time.monotonic()
            self.emit({'id': message['id'], 'result': result})
        except Exception as error:
            # No exception repr: GI errors can contain private application text.
            self.emit({'id': message.get('id'), 'error': type(error).__name__,
                       'message': str(error)[:500] if type(error) in (ValueError, PermissionError, InterruptedError, TimeoutError, ObservationAborted) or isinstance(error, GLib.Error) and message.get('method') in {'probe', 'bind_stop', 'start'} else 'Native operation failed: ' + type(error).__name__})
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
        def lease_watchdog():
            # Independent of GLib, model inference and all repository locks.
            while True:
                time.sleep(.05)
                now = time.monotonic()
                if now - self.last_heartbeat > 2 or self.stop_deadline and now > self.stop_deadline or self.session_deadline and now > self.session_deadline:
                    self.stopped.set()
                    # Closing the process's EIS/portal FDs releases compositor
                    # input even when a native extension is stuck in a call.
                    os._exit(70)
        threading.Thread(target=lease_watchdog, daemon=True, name='olive-input-watchdog').start()
        try:
            self.loop.run()
        finally:
            try:
                self.cleanup()
            finally:
                self.portal.close()


if __name__ == '__main__':
    Worker().run()
