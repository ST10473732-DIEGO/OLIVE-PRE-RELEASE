"""Window-bound navigation in ordinary desktop applications (Linux, KDE/Wayland).

The generic runtime owns identity, observation, input, permissions, Stop and
receipts. This module executes the navigation effects on one *bound* window:

* focus / close_window: KWin exact-window operations;
* browser (declared browser adapter): visit, search, back/forward/reload,
  new/close tab, select tab, find, scroll, with URL/title verification;
* folder: the standard FileManager1 D-Bus interface, verified by window title;
* scroll in other applications: the one accessible scroll container.

Order of preference: accessibility semantics (document URL, focused field,
page tabs), then stable window identity, then declared layout; coordinates
are never computed here. Every input is preceded by a check that the bound
window is unchanged and followed by a fresh observation. Waits are bounded.
"""
import asyncio
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit

from ..observation_revision import Revisions, StaleObservation, stale_reason
from ..page_state import classify
from ..window_targets import (WindowBinding, WindowIdentity, WindowResolutionError, belongs_to, display_title,
                              title_matches)
from ...agent.receipts import COMPLETED, DESKTOP_INPUT, FAILED, NOT_APPLIED, UNCERTAIN

LOAD_SECONDS = 15        # page navigation
UI_SECONDS = 3           # UI reaction to one key
FOLDER_SECONDS = 8       # file manager window for a folder
POLL = .25
SEARCH_KEYS = ('q', 'p', 'query', 'text', 'search_query', 'wd', 'search')
NEW_TAB_URLS = {'about:newtab', 'about:home', 'about:blank', 'about:privatebrowsing'}


class NeedsUser(ValueError):
    """The UI needs the user (sign-in, CAPTCHA, dialog); the task pauses, never retries."""

    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason


def same_destination(wanted, actual):
    """The loaded URL is the requested page (scheme upgrade and www. allowed)."""
    try:
        want, have = urlsplit(wanted), urlsplit(actual)
    except ValueError:
        return False
    if have.scheme not in {'http', 'https'} or want.scheme == 'https' and have.scheme != 'https':
        return False
    host = lambda value: (value.hostname or '').casefold().removeprefix('www.')
    if host(want) != host(have) or (want.port or None) != (have.port or None):
        return False
    wanted_path = want.path.rstrip('/')
    if wanted_path and not have.path.rstrip('/').startswith(wanted_path):
        return False
    return not want.query or parse_qs(want.query) == parse_qs(have.query)


def search_matches(query, url, title=''):
    """The results page is for exactly this query (URL parameter, or the page title)."""
    wanted = ' '.join(query.casefold().split())
    try:
        params = parse_qs(urlsplit(url).query)
    except ValueError:
        params = {}
    for key in SEARCH_KEYS:
        for value in params.get(key, []):
            if ' '.join(value.casefold().split()) == wanted:
                return True
    return bool(title) and wanted in ' '.join(title.casefold().split())


def short(url):
    if url in NEW_TAB_URLS:
        return 'the new tab page'
    try:
        parts = urlsplit(url)
    except ValueError:
        return 'the page'
    if parts.scheme not in {'http', 'https'}:
        return url[:60]
    path = parts.path.rstrip('/')
    return (parts.hostname or url).removeprefix('www.') + (path if len(path) <= 40 else path[:40] + '…')


class Navigator:
    def __init__(self, runtime, grant, app, kind, window, processes, record=None, resuming=False):
        self.runtime, self.grant, self.app, self.kind = runtime, grant, app, kind
        self.resuming = resuming  # "continue" after the user signed in / solved a check
        self.window, self.processes = window, processes
        self.binding = WindowBinding.of(window)
        self.record = record
        self.lines = []
        self.pid = window.pid
        # Every step is planned against an observation revision; input re-checks it.
        self.revisions = Revisions()
        self.planned = self.revisions.observe(window)
        self.binding.revision = self.planned.revision
        self.replans = 0

    # -- shared helpers -----------------------------------------------------
    def check(self):
        self.runtime.check_task(self.grant)

    def progress(self, text):
        self.runtime.progress(text)

    def done(self, text):
        self.lines.append('✓ ' + text)
        if self.record:
            self.record.done(text)

    def reserve(self, operation, expected):
        if not self.record:
            return None
        return self.record.reserve(operation, DESKTOP_INPUT, application=self.app.name,
                                   window=self.binding.window_id, revision=self.binding.revision, expected=expected)

    def settle(self, receipt, state, observed=''):
        if self.record:
            self.record.settle(receipt, state, observed)

    async def current(self):
        """The bound window as the compositor reports it now (never a sibling)."""
        rows = await self.runtime.native.call('application_windows', {'desktop_id': self.app.id.removesuffix('.desktop')})
        windows = [WindowIdentity.from_kwin(row) for row in rows]
        window = self.binding.verify(windows)
        if not window.active:
            raise WindowResolutionError('WINDOW_CHANGED: another window took focus; nothing further was typed')
        dialogs = [w for w in windows if w.dialog and w.transient_for == window.window_id]
        if dialogs:
            state = classify(dialogs=[{'title': d.title} for d in dialogs])
            raise NeedsUser(state.message(self.app.name), 'dialog')
        return window

    async def before_input(self):
        """Gate before every key/pointer effect.

        The step was planned against `self.planned`. The bound window is observed
        again; if it moved, resized or changed monitor the planned step is stale: it
        is discarded, the window is re-bound and the step is re-planned against the
        new observation (at most twice per task). A changed window or a dialog
        stops the task instead (see current()).
        """
        self.check()
        window = await self.current()
        observation = self.revisions.observe(window)
        reason = stale_reason(self.planned, observation, content=False)
        if reason:
            if self.replans >= 2:
                raise StaleObservation(reason + ' repeatedly')
            self.replans += 1
            if self.record:
                self.record.done('Re-observed: ' + reason, 'info')
            self.binding.update(window)
            await self.runtime.native.call('activate', {'pid': self.pid, 'purpose': 'exact',
                                                        'window_id': self.binding.window_id}, timeout=10)
            self.check()
            window = await self.current()
            observation = self.revisions.observe(window)
        self.planned = observation
        self.binding.revision = observation.revision
        return window

    async def observe(self, method, args=None, **kwargs):
        """A read-only native observation; a focus/window failure is reported specifically."""
        try:
            return await self.runtime.native.call(method, args if args is not None else {'pid': self.pid}, **kwargs)
        except PermissionError:
            await self.current()   # Raises WINDOW_DISAPPEARED / WINDOW_CHANGED / dialog when that is the cause.
            raise

    async def documents(self):
        found = await self.observe('document_locations')
        return [d for d in found.get('documents', []) if d.get('uri')]

    async def location(self):
        """The one ready top-level document URL of the bound window, or ''."""
        documents = [d for d in await self.documents() if d.get('ready')]
        uris = {d['uri'] for d in documents}
        return uris.pop() if len(uris) == 1 else ''

    async def wait_for(self, predicate, seconds, what):
        deadline = time.monotonic() + seconds
        while True:
            self.check()
            value = await predicate()
            if value:
                return value
            if time.monotonic() >= deadline:
                raise TimeoutError('NAVIGATION_TIMED_OUT: ' + what + ' within ' + str(seconds) + ' seconds; '
                                   'the input was sent once and not repeated')
            await asyncio.sleep(POLL)

    async def page_state(self):
        """Sign-in / CAPTCHA / dialog check of the loaded page (counts, never contents)."""
        try:
            observation = await self.observe('observe')
        except RuntimeError:
            return None
        window = await self.current()
        return classify(observation.get('controls', []), observation.get('documents', []), (),
                        observation.get('secret_fields', 0), window.title)

    async def require_clear_page(self):
        state = await self.page_state()
        if state is not None and state.blocked:
            raise NeedsUser(state.message(self.app.name), state.state)

    # -- effects ------------------------------------------------------------
    async def run(self):
        effect = self.grant.scope.effect
        handler = {'open': self.focus, 'focus': self.focus, 'visit': self.visit, 'search': self.search, 'browse': self.browse,
                   'tab': self.tab, 'find': self.find, 'scroll': self.scroll,
                   'close_window': self.close_window}.get(effect)
        if handler is None:
            raise ValueError('This navigation effect is not supported')
        if effect in {'visit', 'search', 'tab', 'find'} or effect == 'browse' and self.kind != 'file_manager':
            if self.kind != 'browser':
                raise ValueError('CONTROL_UNAVAILABLE: ' + self.app.name + ' is not a web browser; nothing was done')
        return await handler()

    async def focus(self):
        window = await self.current()
        if self.record:
            self.record.done('Window verified: ' + display_title(window))
        return f'{self.app.name} is open and focused ("{display_title(window)}").'

    async def visit(self):
        url = self.grant.scope.content
        before = await self.location()
        if self.resuming:
            # Re-observe first: after a sign-in the site usually shows the page already.
            if before and same_destination(url, before):
                await self.require_clear_page()
                window = await self.current()
                self.done('Page verified after your sign-in: ' + display_title(window))
                self.runtime.remember_page(self.binding, before)
                return f'{short(before)} is open in {self.app.name} ("{display_title(window)}"); nothing was re-entered.'
            await self.require_clear_page()
        in_place = self.resuming or (self.grant.scope.mode != 'new_tab' and bool(before) and
                                     before == self.runtime.owned_page(self.binding))
        await self.before_input()
        receipt = self.reserve('visit', 'document at ' + short(url))
        await self.runtime.native.call('browser_visit', {'pid': self.pid, 'url': url, 'new_tab': not in_place})
        await self.type_steps(url, visit=True, new_tab=not in_place)
        try:
            loaded = await self.wait_for(lambda: self._loaded(url), LOAD_SECONDS, 'the page did not finish loading')
        except TimeoutError:
            self.settle(receipt, UNCERTAIN, 'page did not load in time')
            raise
        self.settle(receipt, COMPLETED, short(loaded))
        self.done('Navigated to ' + short(loaded))
        await self.require_clear_page()
        window = await self.current()
        self.done('Page verified: ' + display_title(window))
        self.runtime.remember_page(self.binding, loaded)
        return f'Opened {short(loaded)} in {self.app.name} ("{display_title(window)}").'

    async def _loaded(self, url):
        current = await self.location()
        if current and same_destination(url, current):
            return current
        if current and current not in NEW_TAB_URLS and not current.startswith('about:'):
            # A redirect (often to a sign-in page) is never reported as the requested page.
            seen = getattr(self, '_redirect', None)
            if seen is None or seen[0] != current:
                state = await self.page_state()   # Once per distinct page, not every poll.
                if state is not None and state.blocked:
                    raise NeedsUser(state.message(self.app.name), state.state)
                self._redirect = (current, time.monotonic())
            elif time.monotonic() - seen[1] >= 2.5:
                raise ValueError('DESTINATION_UNVERIFIED: ' + short(url) + ' redirected to ' + short(current) +
                                 ' (for example because you are already signed in); nothing else was done')
            if urlsplit(current).hostname and (urlsplit(current).hostname or '').removeprefix('www.') != \
                    (urlsplit(url).hostname or '').removeprefix('www.'):
                raise ValueError('DESTINATION_UNVERIFIED: the browser went to ' + short(current) + ' instead of ' +
                                 short(url) + '; nothing else was done')
        return ''

    async def type_steps(self, text, visit, new_tab):
        """Staged address-bar entry: each step once, text verified before Enter."""
        steps = (['new_tab'] if new_tab else []) + ['address', 'type_query', 'submit']
        labels = {'new_tab': 'Opening a new tab…', 'address': 'Focusing the address bar…',
                  'type_query': 'Entering the address…' if visit else 'Entering the search…',
                  'submit': 'Loading…' if visit else 'Searching…'}
        for step in steps:
            await self.before_input()
            self.progress(labels[step])
            if step == 'submit':
                await self.verify_typed(text, visit)
            before = {d['uri'] for d in await self.documents()} if step == 'new_tab' else set()
            await self.runtime.native.call('browser_step', {'step': step})
            if step == 'new_tab':
                async def opened():
                    uris = {d['uri'] for d in await self.documents()}
                    # A new-tab page, or a custom new-tab page that replaced the shown document.
                    return bool(uris & NEW_TAB_URLS) or bool(uris) and uris != before
                await self.wait_for(opened, UI_SECONDS, 'the new tab did not open')
                self.done('New tab opened')

    async def verify_typed(self, text, visit):
        """The focused address field holds exactly the requested text; otherwise no Enter."""
        wanted = {text} if visit else {text, '? ' + text}
        deadline = time.monotonic() + 1.5
        while True:
            self.check()
            try:
                chrome = await self.observe('browser_chrome')
            except RuntimeError:
                chrome = {'controls': []}
            focused = [c for c in chrome['controls'] if c.get('focused') and c.get('editable')]
            if len(focused) == 1 and focused[0].get('value') in wanted:
                return
            if time.monotonic() >= deadline:
                raise ValueError('CONTROL_UNAVAILABLE: the address bar did not show exactly the requested text; '
                                 'Enter was not pressed')
            await asyncio.sleep(.15)

    async def search(self):
        query = self.grant.scope.content
        if self.resuming:
            current = await self.location()
            window = await self.current()
            if current and search_matches(query, current, display_title(window)):
                await self.require_clear_page()
                self.done('Search results verified after your check')
                return f'The results for "{query}" are open in {self.app.name}; nothing was re-entered.'
            await self.require_clear_page()
        await self.before_input()
        receipt = self.reserve('search', 'results page for the query')
        new_tab = self.grant.scope.mode != 'current_tab' and not self.resuming
        await self.runtime.native.call('browser_begin', {'pid': self.pid, 'query': query, 'new_tab': new_tab})
        await self.type_steps(query, visit=False, new_tab=new_tab)

        async def results():
            current = await self.location()
            if not current or current in NEW_TAB_URLS:
                return ''
            window = await self.current()
            if search_matches(query, current, display_title(window)):
                return current
            state = await self.page_state()
            if state is not None and state.blocked:
                raise NeedsUser(state.message(self.app.name), state.state)
            return ''
        try:
            loaded = await self.wait_for(results, LOAD_SECONDS, 'the search results did not load')
        except TimeoutError:
            self.settle(receipt, UNCERTAIN, 'results not verified')
            raise
        self.settle(receipt, COMPLETED, 'results for the query at ' + (urlsplit(loaded).hostname or ''))
        await self.require_clear_page()
        self.done('Search completed')
        self.runtime.remember_page(self.binding, loaded)
        return f'Searched for "{query}" in {self.app.name}; the results page is open ({urlsplit(loaded).hostname}).'

    async def browse(self):
        operation = self.grant.scope.content
        if self.kind == 'file_manager':
            if operation not in {'back', 'forward'}:
                raise ValueError('CONTROL_UNAVAILABLE: only back/forward are supported in the file manager')
            window = await self.before_input()
            receipt = self.reserve(operation, 'another folder')
            await self.runtime.native.call('browser_navigation', {'operation': 'history', 'direction': operation})

            async def changed():
                now = await self.current()
                return now if now.title != window.title else None
            try:
                now = await self.wait_for(changed, UI_SECONDS, 'the folder did not change')
            except TimeoutError:
                self.settle(receipt, NOT_APPLIED, 'no earlier folder')
                raise
            self.settle(receipt, COMPLETED, 'folder changed')
            self.done(f'Went {operation} to {display_title(now)}')
            return f'Went {operation}; {self.app.name} shows {display_title(now)}.'
        before = await self.location()
        closing = display_title(await self.current()) if operation == 'close_tab' else ''
        if operation == 'close_tab':
            chrome = await self.observe('browser_chrome')
            tabs = [c for c in chrome['controls'] if c.get('role') == 'page tab']
            if len(tabs) <= 1:
                raise ValueError('INPUT_REFUSED: this is the window\'s last tab, so closing it would close the '
                                 'window. Say "close this window" if you want that. Nothing was closed.')
        await self.before_input()
        tabs_before = None
        if operation == 'reopen_tab':
            chrome = await self.observe('browser_chrome')
            tabs_before = sum(c.get('role') == 'page tab' for c in chrome['controls'])
        receipt = self.reserve(operation, {'back': 'previous page', 'forward': 'next page', 'reload': 'same page reloaded',
                                           'new_tab': 'a new empty tab', 'close_tab': 'another tab',
                                           'reopen_tab': 'the closed tab back'}.get(operation, ''))
        await self.runtime.native.call('browser_navigation', {'operation': 'browse', 'direction': operation})

        async def settled():
            current = await self.location()
            if operation in {'back', 'forward'}:
                return current if current and current != before else ''
            if operation == 'new_tab':
                return current if current in NEW_TAB_URLS else ''
            if operation == 'close_tab':
                return current if current != before else ''
            if operation == 'reopen_tab':
                chrome = await self.observe('browser_chrome')
                count = sum(c.get('role') == 'page tab' for c in chrome['controls'])
                return current if count == tabs_before + 1 and current != before else ''
            return current if current == before and current else ''
        try:
            current = await self.wait_for(settled, LOAD_SECONDS if operation != 'new_tab' else UI_SECONDS,
                                          {'back': 'there was no earlier page', 'forward': 'there was no later page',
                                           'reload': 'the page did not reload', 'new_tab': 'the new tab did not open',
                                           'close_tab': 'the tab did not close',
                                           'reopen_tab': 'no closed tab came back'}.get(operation, 'nothing changed'))
        except TimeoutError:
            self.settle(receipt, NOT_APPLIED if operation in {'back', 'forward'} else UNCERTAIN, 'no change observed')
            raise
        self.settle(receipt, COMPLETED, short(current) if current not in NEW_TAB_URLS else 'new tab')
        if operation in {'back', 'forward', 'reload'}:
            await self.require_clear_page()
        text = {'back': 'Went back to ', 'forward': 'Went forward to ', 'reload': 'Reloaded ',
                'close_tab': 'Tab closed; now showing ', 'reopen_tab': 'Reopened the closed tab: '}.get(operation)
        if operation == 'new_tab':
            self.done('New tab opened')
            self.runtime.remember_page(self.binding, current)
            return f'Opened a new tab in {self.app.name}.'
        if operation == 'close_tab':
            now = await self.current()
            self.done(f'Closed the tab "{closing}"')
            return f'Closed the tab "{closing}"; now showing "{display_title(now)}".'
        self.done(text + short(current))
        return text + short(current) + '.'

    async def tab(self):
        operation = self.grant.scope.content
        if operation in {'next', 'previous'}:
            window = await self.before_input()
            receipt = self.reserve('tab_' + operation, 'another tab')
            await self.runtime.native.call('browser_navigation', {'operation': 'tab', 'direction': operation})

            async def changed():
                now = await self.current()
                return now if now.title != window.title else None
            now = await self.wait_for(changed, UI_SECONDS, 'the tab did not change')
            self.settle(receipt, COMPLETED, 'tab changed')
            self.done('Switched to ' + display_title(now))
            return 'Switched to the tab "' + display_title(now) + '".'
        wanted = self.grant.scope.destination
        window = await self.current()
        if title_matches(window, wanted):
            self.done(f'{display_title(window)} tab selected')
            return f'The "{display_title(window)}" tab is already showing in {self.app.name}.'
        chrome = await self.observe('browser_chrome')
        tabs = [c for c in chrome['controls'] if c.get('role') == 'page tab' and c.get('enabled', True)]
        matches = [c for c in tabs if title_matches(WindowIdentity('', 0, title=c.get('name', '')), wanted)]
        if not matches:
            raise ValueError(f'TARGET_NOT_VISIBLE: no open tab named "{wanted}" in this {self.app.name} window; '
                             'nothing was changed')
        if len(matches) > 1:
            names = '\n'.join(f'{i}. {m.get("name", "")[:80]}' for i, m in enumerate(matches[:9], 1))
            raise ValueError(f'CONTROL_AMBIGUOUS: several tabs match "{wanted}":\n{names}\nWhich one? Nothing was changed.')
        target = matches[0]
        await self.before_input()
        receipt = self.reserve('select_tab', 'the requested tab selected')
        action = next((a for a in target.get('actions', []) if a in {'switch', 'select', 'activate', 'press', 'click'}), '')
        if action:
            await self.runtime.native.call('invoke', {'revision': chrome['revision'], 'target': target['id'],
                                                      'bounds': target['bounds'], 'value': action})
        else:
            await self.runtime.native.call('click', {'revision': chrome['revision'], 'target': target['id'],
                                                     'bounds': target['bounds'], 'value': ''})

        async def selected():
            now = await self.current()
            return now if title_matches(now, wanted) else None
        try:
            now = await self.wait_for(selected, UI_SECONDS, 'the tab did not become active')
        except TimeoutError:
            self.settle(receipt, UNCERTAIN, 'tab selection not verified')
            raise
        self.settle(receipt, COMPLETED, 'window title shows the tab')
        self.done(f'{display_title(now)} tab selected')
        return f'Selected the "{display_title(now)}" tab in {self.app.name}.'

    async def find(self):
        needle = self.grant.scope.content
        await self.before_input()
        receipt = self.reserve('find', 'find bar holding the text')
        await self.runtime.native.call('browser_navigation', {'operation': 'browse', 'direction': 'find'})

        async def field():
            chrome = await self.observe('browser_chrome')
            found = [c for c in chrome['controls'] if c.get('focused') and c.get('editable') and
                     'find' in c.get('name', '').casefold()]
            return (chrome, found[0]) if len(found) == 1 else None
        chrome, target = await self.wait_for(field, UI_SECONDS, 'the find bar did not open')
        await self.before_input()
        await self.runtime.native.call('replace_text', {'revision': chrome['revision'], 'target': target['id'],
                                                        'bounds': target['bounds'], 'value': needle})

        async def typed():
            again = await self.observe('browser_chrome')
            found = [c for c in again['controls'] if c.get('editable') and 'find' in c.get('name', '').casefold()
                     and c.get('value') == needle]
            return again if found else None
        again = await self.wait_for(typed, UI_SECONDS, 'the find text was not accepted')
        status = next((c.get('name', '') for c in again['controls']
                       if re.search(r'\b\d+ of \d+ match|phrase not found|no matches', c.get('name', ''), re.I)), '')
        self.settle(receipt, COMPLETED, 'find text present')
        self.done('Finding “' + needle + '”' + (' — ' + status[:60] if status else ''))
        return f'Searching this page for "{needle}"' + (f' ({status[:60]}).' if status else '.')

    async def scroll(self):
        direction, container = self.grant.scope.content, self.grant.scope.destination
        if self.kind == 'browser' and container in {'', 'page'}:
            documents = [d for d in await self.documents() if d.get('ready')]
            if len(documents) != 1:
                raise ValueError('CONTROL_AMBIGUOUS: the page area is not uniquely exposed; nothing was scrolled')
            bounds = documents[0]['bounds']
            before = await self.observe('visual_observe', timeout=5)
            await self.before_input()
            receipt = self.reserve('scroll', 'page moved ' + direction)
            await self.runtime.native.call('browser_navigation', {'operation': 'scroll', 'direction': direction,
                                                                  'bounds': bounds})
            after = await self.observe('visual_observe', timeout=5)
            if after['png'] == before['png']:
                self.settle(receipt, NOT_APPLIED, 'no visible change')
                raise ValueError('TARGET_NOT_VISIBLE: scrolled once but the page did not move (already at the ' +
                                 ('bottom' if direction == 'down' else 'top') + '?)')
            self.settle(receipt, COMPLETED, 'page moved')
            self.done('Scrolled the page ' + direction)
            return f'Scrolled the page {direction}.'
        observation = await self.observe('observe')
        roles = {'scroll pane', 'list', 'tree', 'table', 'tree table', 'document web', 'document frame', 'list box'}
        containers = [c for c in observation['controls'] if c.get('role') in roles and c.get('bounds')]
        if container:
            containers = [c for c in containers if container.split()[0] in c.get('name', '').casefold()]
        if len(containers) != 1:
            raise ValueError(('CONTROL_AMBIGUOUS: several scrollable areas are visible' if containers else
                              'CONTROL_UNAVAILABLE: no scrollable area is exposed') +
                             '; say which one. Nothing was scrolled.')
        target = containers[0]
        await self.before_input()
        receipt = self.reserve('scroll', 'container moved ' + direction)
        await self.runtime.native.call('scroll', {'revision': observation['revision'], 'target': target['id'],
                                                  'bounds': target['bounds'], 'value': '480' if direction == 'down' else '-480'})
        self.settle(receipt, COMPLETED, 'scroll dispatched to the one container')
        self.done('Scrolled ' + (target.get('name') or 'the list')[:40] + ' ' + direction)
        return f'Scrolled {direction}.'

    async def close_window(self):
        window = await self.before_input()
        receipt = self.reserve('close_window', 'window closed')
        result = await self.runtime.native.call('close_window', {'window_id': window.window_id}, timeout=6)
        if result.get('dialog'):
            self.settle(receipt, UNCERTAIN, 'the application asked for confirmation')
            raise NeedsUser('DIALOG_REQUIRES_USER: ' + self.app.name + ' asked for confirmation before closing. '
                            'Please answer it yourself; I did not click anything.', 'dialog')
        if not result.get('closed'):
            self.settle(receipt, UNCERTAIN, 'window still open')
            raise TimeoutError('NAVIGATION_TIMED_OUT: the window did not close within 3 seconds')
        self.settle(receipt, COMPLETED, 'window closed')
        self.done(f'{self.app.name} window closed')
        return f'Closed the {self.app.name} window "{display_title(window)}".'


def resolve_folder(path, home=None):
    """A requested folder -> an existing directory, never a guessed neighbour."""
    home = Path(home or Path.home())
    if path.startswith('xdg:'):
        name = path[4:]
        folder = xdg_dir(name, home)
    elif path == '~' or path.startswith('~/'):
        folder = home / path[2:] if path != '~' else home
    elif path.startswith('/'):
        folder = Path(path)
    else:
        raise ValueError('Provide a folder name or path')
    try:
        folder = folder.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError('TARGET_NOT_VISIBLE: that folder does not exist; nothing was opened') from None
    if not folder.is_dir():
        raise ValueError('TARGET_NOT_VISIBLE: that path is not a folder; nothing was opened')
    return folder


def xdg_dir(name, home):
    defaults = {'DOWNLOAD': 'Downloads', 'DOCUMENTS': 'Documents', 'PICTURES': 'Pictures', 'MUSIC': 'Music',
                'VIDEOS': 'Videos', 'DESKTOP': 'Desktop'}
    if name not in defaults:
        raise ValueError('Unknown user folder')
    config = home / '.config' / 'user-dirs.dirs'
    try:
        for line in config.read_text(encoding='utf-8').splitlines()[:50]:
            match = re.fullmatch(r'XDG_' + name + r'_DIR="(\$HOME)?(/?[^"$`\\]*)"', line.strip())
            if match:
                value = match.group(2)
                return home / value.lstrip('/') if match.group(1) else Path(value)
    except OSError:
        pass
    return home / defaults[name]


def folder_uri(folder):
    return 'file://' + quote(str(folder))


def folder_title(folder, home=None):
    return 'Home' if Path(folder) == Path(home or Path.home()) else Path(folder).name


def app_windows(rows, app, pids):
    identities = [WindowIdentity.from_kwin(row) for row in rows]
    return [w for w in identities if belongs_to(app.id, pids, w)]
