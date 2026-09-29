"""Deterministic simulated desktop for navigation tests (no real input, no screenshots).

It stands in for OLIVE's native helper: KWin-like windows on a multi-monitor
layout, a Firefox-like browser (tabs, history, address bar, find bar, search
engine, sign-in redirect, CAPTCHA page), a Dolphin-like file manager and
generic accessible controls (tabs, duplicate labels, a dialog, a delayed
element, changing revisions). It enforces the helper's rules: input needs the
bound window to exist, be active and keep its geometry; accessibility actions
need the current observation revision. Every call is logged so tests can prove
that no input happened after Stop, a question or a failure.
"""
from dataclasses import dataclass, field
import asyncio
import itertools
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import quote_plus, urlsplit

INPUT = {'browser_step', 'browser_navigation', 'invoke', 'click', 'replace_text', 'type', 'key', 'scroll', 'focus',
         'visual_click', 'visual_text', 'visual_key', 'close_window', 'show_folder'}
_ids = itertools.count(1)


def window_id():
    return '{%08d-0000-4000-8000-000000000000}' % next(_ids)


@dataclass
class Tab:
    url: str
    title: str
    history: list = field(default_factory=list)
    forward: list = field(default_factory=list)
    secret_fields: int = 0
    controls: list = field(default_factory=list)


@dataclass
class Window:
    app_id: str
    pid: int
    title: str = ''
    output: str = 'A'
    bounds: tuple = (100, 100, 1200, 800)
    active: bool = False
    minimized: bool = False
    dialog: bool = False
    transient_for: str = ''
    tabs: list = field(default_factory=list)
    current: int = 0
    id: str = field(default_factory=window_id)
    focus: str = ''          # '', 'address', 'find'
    address: str = ''
    find: str = ''
    find_open: bool = False

    @property
    def caption(self):
        if self.tabs:
            return self.tabs[self.current].title + ' — Mozilla Firefox'
        return self.title


SITES = {
    'https://example.com/': 'Example Domain',
    'https://github.com/': 'GitHub',
    'https://www.youtube.com/': 'YouTube',
    'https://account.example.org/': 'Account',
}


class FakeDesktop:
    def __init__(self, monitors=(('A', 0, 0, 1920, 1080), ('B', 1920, 0, 2560, 1440), ('C', -1920, 0, 1920, 1080))):
        self.monitors = monitors
        self.windows = []
        self.calls = []
        self.bound = ''
        self.revision = 0
        self.session = None
        self.hooks = []          # callables(method, args, phase) -> None
        self.redirects = {}      # url -> (url, title, secret_fields)
        self.captcha_search = False
        self.stop_after = None   # (method, count): raise CancelledError-like stop externally
        self.frames = 0

    # -- setup ---------------------------------------------------------------
    def browser(self, *titles_urls, pid=4100, output='A', bounds=(100, 100, 1200, 800), active=False):
        tabs = [Tab(url, title) for title, url in titles_urls] or [Tab('about:newtab', 'New Tab')]
        window = Window('firefox', pid, output=output, bounds=bounds, active=active, tabs=tabs, current=len(tabs) - 1)
        self.windows.append(window)
        return window

    def window(self, app_id, pid, title, **kwargs):
        window = Window(app_id, pid, title, **kwargs)
        self.windows.append(window)
        return window

    def by_id(self, identity):
        return next((w for w in self.windows if w.id == identity), None)

    def row(self, w):
        return {'id': w.id, 'pid': w.pid, 'active': w.active, 'output': w.output, 'title': w.caption,
                'normal': not w.dialog, 'dialog': w.dialog, 'stacking': self.windows.index(w),
                'transient_for': w.transient_for, 'desktop_file': w.app_id, 'resource_class': w.app_id,
                'resource_name': w.app_id, 'bounds': list(w.bounds), 'frame': list(w.bounds),
                'minimized': w.minimized, 'fullscreen': False, 'on_current_desktop': True, 'desktops': ['1']}

    def inputs(self):
        return [name for name, _ in self.calls if name in INPUT]

    # -- helper protocol -------------------------------------------------------
    def bound_window(self, keys=('id', 'bounds', 'output')):
        window = self.by_id(self.bound)
        if window is None:
            raise PermissionError('WINDOW_DISAPPEARED: the bound window closed; nothing was sent')
        if not window.active:
            raise PermissionError('Compositor focus or window geometry changed; observe again')
        snapshot = getattr(self, 'snapshot', None)
        if snapshot and any(snapshot[k] != getattr(window, k) for k in ('bounds', 'output') if k in keys):
            raise PermissionError('Compositor focus or window geometry changed; observe again')
        return window

    def active_of(self, pid):
        found = [w for w in self.windows if w.pid == pid and w.active]
        if len(found) != 1:
            raise PermissionError('Requested window lost focus')
        if self.bound and self.by_id(self.bound) and self.by_id(self.bound).pid == pid and found[0].id != self.bound:
            raise PermissionError('WINDOW_CHANGED: another window of the application is focused; observe again')
        return found[0]

    def chrome(self, window):
        self.revision += 1
        controls = [{'id': 'urlbar', 'name': 'Search or enter address', 'role': 'entry', 'editable': True,
                     'focused': window.focus == 'address', 'value': window.address if window.focus == 'address' else
                     window.tabs[window.current].url, 'bounds': [window.bounds[0] + 200, window.bounds[1] + 40, 600, 30],
                     'enabled': True, 'actions': []}]
        for index, tab in enumerate(window.tabs):
            controls.append({'id': f'tab{index}', 'name': tab.title, 'role': 'page tab', 'selected': index == window.current,
                             'enabled': True, 'actions': ['switch'], 'editable': False, 'focused': False,
                             'bounds': [window.bounds[0] + 10 + 150 * index, window.bounds[1] + 5, 140, 30]})
        if window.find_open:
            controls.append({'id': 'find', 'name': 'Find in page', 'role': 'entry', 'editable': True,
                             'focused': window.focus == 'find', 'value': window.find, 'enabled': True,
                             'bounds': [window.bounds[0] + 10, window.bounds[1] + window.bounds[3] - 40, 300, 30]})
            if window.find:
                controls.append({'id': 'findstatus', 'name': '1 of 2 matches', 'role': 'label', 'enabled': True})
        return {'pid': window.pid, 'revision': str(self.revision), 'controls': controls,
                'windows': [{'id': '1', 'active': True}], 'documents': []}

    def navigate(self, window, url, title=None, record=True):
        tab = window.tabs[window.current]
        if record and tab.url:
            tab.history.append((tab.url, tab.title))
            tab.forward.clear()
        if url in self.redirects:
            url, title, secret = self.redirects[url]
            tab.secret_fields = secret
        else:
            tab.secret_fields = 0
        tab.url, tab.title = url, title or SITES.get(url.rstrip('/') + '/', url)
        window.focus = ''

    async def call(self, method, args=None, timeout=None):
        args = dict(args or {})
        self.calls.append((method, args))
        for hook in list(self.hooks):
            hook(self, method, args, 'before')
        result = self.dispatch(method, args)
        for hook in list(self.hooks):
            hook(self, method, args, 'after')
        await asyncio.sleep(0)
        return result

    def dispatch(self, method, args):
        if method in {'end', 'reset'}:
            self.bound = ''
            return {'cleanup_completed': True}
        if method == 'application_windows':
            wanted = args['desktop_id']
            return [self.row(w) for w in self.windows if w.app_id == wanted]
        if method == 'activate':
            window = self.by_id(args.get('window_id', ''))
            if window is None or window.pid != args['pid']:
                raise ValueError('WINDOW_DISAPPEARED: the chosen window closed during activation')
            if any(w.dialog and w.transient_for == window.id for w in self.windows):
                raise ValueError('DIALOG_REQUIRES_USER: the window has an open dialog')
            for other in self.windows:
                other.active = False
            window.active, window.minimized = True, False
            self.bound = window.id
            self.snapshot = {'bounds': window.bounds, 'output': window.output}
            return {'active': True, 'accessible': True, 'window_id': window.id, 'bounds': list(window.bounds),
                    'output': window.output}
        if method == 'document_locations':
            window = self.active_of(args['pid'])
            tab = window.tabs[window.current] if window.tabs else None
            return {'documents': [{'uri': tab.url, 'ready': True, 'bounds': [window.bounds[0], window.bounds[1] + 80,
                                   window.bounds[2], window.bounds[3] - 80]}] if tab else []}
        if method == 'browser_chrome':
            return self.chrome(self.active_of(args['pid']))
        if method == 'observe':
            window = self.active_of(args['pid'])
            result = self.chrome(window) if window.tabs else {'revision': str(self.revision), 'controls': [],
                                                                'windows': [{'id': '1', 'active': True}]}
            tab = window.tabs[window.current] if window.tabs else None
            result['controls'] += [dict(c) for c in (tab.controls if tab else getattr(window, 'controls', []))]
            result['documents'] = [{'uri': tab.url, 'name': tab.title}] if tab else []
            result['secret_fields'] = tab.secret_fields if tab else 0
            return result
        if method == 'visual_observe':
            window = self.active_of(args['pid'])
            self.frames += 1
            tab = window.tabs[window.current] if window.tabs else None
            return {'png': f'{window.id}:{tab.url if tab else window.title}:{getattr(window, "scrolled", 0)}',
                    'width': 1000, 'height': 700, 'revision': str(self.frames), 'window': self.row(window)}
        if method in {'browser_visit', 'browser_begin'}:
            window = self.bound_window()
            steps = (['new_tab'] if args.get('new_tab', True) else []) + ['address', 'type_query', 'submit']
            self.session = {'value': args.get('url') or args.get('query'), 'visit': method == 'browser_visit',
                            'steps': steps, 'stage': 0}
            return {'ready': True, 'steps': steps}
        if method == 'browser_step':
            window = self.bound_window()
            session = self.session
            if not session or session['stage'] >= len(session['steps']) or args['step'] != session['steps'][session['stage']]:
                raise PermissionError('Browser step is stale or outside this task')
            session['stage'] += 1
            step = args['step']
            if step == 'new_tab':
                window.tabs.append(Tab('about:newtab', 'New Tab'))
                window.current = len(window.tabs) - 1
            elif step == 'address':
                window.focus, window.address = 'address', window.tabs[window.current].url
            elif step == 'type_query':
                if window.focus != 'address':
                    raise PermissionError('Address bar not focused')
                window.address = session['value'] if session['visit'] else '? ' + session['value']
            elif step == 'submit':
                if session['visit']:
                    self.navigate(window, session['value'])
                else:
                    query = session['value']
                    if self.captcha_search:
                        self.navigate(window, 'https://www.google.com/sorry/index?continue=x', 'Unusual traffic')
                    else:
                        self.navigate(window, 'https://www.google.com/search?q=' + quote_plus(query),
                                      query + ' - Google Search')
            return {'dispatched': True}
        if method == 'browser_navigation':
            window = self.bound_window()
            operation, direction = args['operation'], args['direction']
            tab = window.tabs[window.current] if window.tabs else None
            if operation == 'browse' and direction == 'back' and tab and tab.history:
                tab.forward.append((tab.url, tab.title))
                tab.url, tab.title = tab.history.pop()
            elif operation == 'browse' and direction == 'forward' and tab and tab.forward:
                tab.history.append((tab.url, tab.title))
                tab.url, tab.title = tab.forward.pop()
            elif operation == 'browse' and direction == 'new_tab':
                window.tabs.append(Tab('about:newtab', 'New Tab'))
                window.current = len(window.tabs) - 1
            elif operation == 'browse' and direction == 'close_tab':
                window.tabs.pop(window.current)
                window.current = max(0, window.current - 1)
            elif operation == 'browse' and direction == 'find':
                window.find_open, window.focus = True, 'find'
            elif operation == 'tab':
                window.current = (window.current + (1 if direction == 'next' else -1)) % len(window.tabs)
            elif operation == 'history':
                window.title = window.title + ' (back)' if direction == 'back' else window.title
            elif operation == 'scroll':
                window.scrolled = getattr(window, 'scrolled', 0) + (1 if direction == 'down' else -1)
            return {'dispatched': True}
        if method in {'invoke', 'click'}:
            window = self.bound_window()
            if args['revision'] != str(self.revision):
                raise ValueError('Stale observation or unknown target')
            target = args['target']
            if target.startswith('tab'):
                window.current = int(target[3:])
            return {'dispatched': True, 'verified': False}
        if method == 'replace_text':
            window = self.bound_window()
            if args['revision'] != str(self.revision) or args['target'] != 'find' or window.focus != 'find':
                raise PermissionError('INPUT_REFUSED: only a browser search, address or find field can be replaced')
            window.find = args['value']
            return {'dispatched': True}
        if method == 'close_window':
            window = self.bound_window(keys=('id',))
            self.windows.remove(window)
            self.bound = ''
            return {'closed': True, 'dialog': False}
        if method == 'show_folder':
            path = Path(urlsplit(args['uri']).path)
            for other in self.windows:
                other.active = False
            self.window('org.kde.dolphin', 4300, path.name + ' — Dolphin', active=True)
            return {'dispatched': True}
        if method in {'type', 'key', 'scroll', 'focus'}:
            self.bound_window()
            return {'dispatched': True, 'verified': False}
        raise AssertionError('Unexpected native call ' + method)


class FakeApps:
    """Installed apps as the reviewed desktop entries would report them."""
    KINDS = {'Firefox': 'browser', 'Discord': 'messaging', 'Dolphin': 'file_manager', 'Konsole': 'terminal',
             'Kate': 'editor'}
    IDS = {'Firefox': 'firefox.desktop', 'Discord': 'discord.desktop', 'Dolphin': 'org.kde.dolphin.desktop',
           'Konsole': 'org.kde.konsole.desktop', 'Kate': 'org.kde.kate.desktop'}
    PIDS = {'Firefox': 4100, 'Discord': 4200, 'Dolphin': 4300, 'Konsole': 4400, 'Kate': 4500}

    def __init__(self, desktop, installed=('Firefox', 'Discord', 'Dolphin', 'Konsole', 'Kate')):
        self.desktop = desktop
        self.apps = {name: SimpleNamespace(id=self.IDS[name], name=name, executable=Path(sys.executable),
                                           entry=None) for name in installed}
        self.values = {app.id: app for app in self.apps.values()}
        self.launched = []
        self.launch_window = {}   # name -> callable creating the window on launch

    def discover(self):
        return list(self.apps.values())

    def resolve(self, requested):
        key = requested.casefold()
        for name, app in self.apps.items():
            if name.casefold() == key:
                return app
        raise LookupError('No reviewed installed application matches this name')

    def kind(self, app):
        return self.KINDS.get(app.name, 'app')

    def processes(self, app):
        pid = self.PIDS[app.name]
        return [(pid, 1.0)] if any(w.pid == pid for w in self.desktop.windows) or app.name in self.launched else []

    def launch(self, app, force=False):
        self.launched.append(app.name)
        maker = self.launch_window.get(app.name)
        if maker:
            maker(self.desktop)
        return self.processes(app)

    def bind_window_processes(self, app, rows):
        return sorted({(row['pid'], 1.0) for row in rows})

    def verify_process(self, app, pid, created):
        return True

    async def wait_for_processes(self, app, stopped, **_):
        return self.processes(app) or [(self.PIDS[app.name], 1.0)]
