"""Application window identity and deterministic multi-window resolution.

A window is identified by stable compositor/process facts: desktop application
ID, process ID and lifetime, window ID, resource class, output and title. A
title is observational data (it can be set by a web page); it can help choose
between windows of an already identified application, never identify one.

Resolution order (first rule that yields exactly one window wins):
explicit user choice, same-task binding, requested title/site, the only
window, the one focused window. Anything else is ambiguous and must be asked;
nothing here ever picks a window by guess, stacking order or a partial title
match between several windows.
"""
from dataclasses import dataclass, field
import re


class WindowResolutionError(ValueError):
    """A public, specific reason why no window can be used."""


@dataclass(frozen=True)
class WindowIdentity:
    window_id: str
    pid: int
    app_id: str = ''
    resource_class: str = ''
    title: str = ''
    output: str = ''
    bounds: tuple = ()
    active: bool = False
    minimized: bool = False
    fullscreen: bool = False
    normal: bool = True
    dialog: bool = False
    transient_for: str = ''
    desktops: tuple = ()
    on_current_desktop: bool = True

    @classmethod
    def from_kwin(cls, row):
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or type(row.get('pid')) is not int:
            raise ValueError('Invalid compositor window row')
        return cls(row['id'], row['pid'], str(row.get('desktop_file', '')).removesuffix('.desktop'),
                   str(row.get('resource_class', '')), safe_title(row.get('title', '')), str(row.get('output', '')),
                   tuple(row.get('bounds') or ()), bool(row.get('active')), bool(row.get('minimized')),
                   bool(row.get('fullscreen')), bool(row.get('normal', True)), bool(row.get('dialog')),
                   str(row.get('transient_for', '')), tuple(row.get('desktops') or ()),
                   bool(row.get('on_current_desktop', True)))

    def summary(self):
        return {'window_id': self.window_id, 'pid': self.pid, 'app_id': self.app_id, 'title': self.title,
                'output': self.output, 'active': self.active, 'minimized': self.minimized}


def safe_title(value):
    """Titles are untrusted display text: printable, single line, bounded."""
    text = re.sub(r'[\x00-\x1f\x7f‪-‮⁦-⁩]', ' ', str(value or ''))
    return re.sub(r'\s+', ' ', text).strip()[:160]


def belongs_to(app_id, pids, window):
    """A window belongs to an application only by desktop ID and a verified process.

    The desktop ID is KWin's `desktopFileName`; the PID must be one of the
    application's verified processes. Title or class alone is never enough.
    """
    wanted = (app_id or '').removesuffix('.desktop').casefold()
    return bool(wanted) and window.app_id.casefold() == wanted and window.pid in set(pids)


BROWSER_SUFFIX = re.compile(r'\s+[—–-]\s+(?:Mozilla Firefox(?: Private Browsing)?|Firefox|Chromium|Google Chrome|'
                            r'Brave|Vivaldi|Dolphin|Konsole|Kate|System Settings|Discord)$', re.I)


def display_title(window):
    if window.title.casefold() in {'mozilla firefox', 'firefox', 'mozilla firefox private browsing'}:
        return 'New Tab'  # Firefox shows only its name for an empty tab.
    return BROWSER_SUFFIX.sub('', window.title) or window.title or 'Untitled window'


def title_matches(window, wanted):
    """Whole-word, case-insensitive match of a requested title/site in a window title."""
    words = re.findall(r'[\w.]+', (wanted or '').casefold())
    if not words:
        return False
    title = display_title(window).casefold()
    return all(re.search(r'(?<![\w.])' + re.escape(word) + r'(?![\w])', title) for word in words)


@dataclass(frozen=True)
class WindowHint:
    choice_id: str = ''     # the user picked this window from a clarification
    bound_id: str = ''      # same task / conversation binding
    bound_pid: int = 0
    title: str = ''         # requested tab title or site name, e.g. "GitHub"
    exclude_id: str = ''    # "the other window"


@dataclass(frozen=True)
class Resolution:
    window: WindowIdentity | None
    candidates: tuple = ()
    reason: str = ''

    @property
    def ambiguous(self):
        return self.window is None and len(self.candidates) > 1


def resolve_window(windows, hint=WindowHint()):
    """Choose one top-level window deterministically, or report why not."""
    normal = [w for w in windows if w.normal and not w.dialog]
    if hint.choice_id:
        chosen = [w for w in normal if w.window_id == hint.choice_id]
        if len(chosen) != 1:
            raise WindowResolutionError('WINDOW_DISAPPEARED: the window you chose is no longer open; nothing was done')
        return Resolution(chosen[0], tuple(normal), 'choice')
    if hint.bound_id:
        bound = [w for w in normal if w.window_id == hint.bound_id]
        if len(bound) == 1 and (not hint.bound_pid or bound[0].pid == hint.bound_pid):
            return Resolution(bound[0], tuple(normal), 'bound')
        # The bound window vanished or now belongs to another process: never
        # slide to a sibling window silently. A unique requested title can still
        # identify the replacement; otherwise the user is asked below.
        remaining = [w for w in normal if w.window_id != hint.bound_id]
        if hint.title:
            matches = [w for w in remaining if title_matches(w, hint.title)]
            if len(matches) == 1:
                return Resolution(matches[0], tuple(remaining), 'title')
        return Resolution(None, tuple(remaining), 'bound_gone')
    pool = [w for w in normal if w.window_id != hint.exclude_id]
    if not pool:
        return Resolution(None, (), 'none')
    if hint.title:
        matches = [w for w in pool if title_matches(w, hint.title)]
        if len(matches) == 1:
            return Resolution(matches[0], tuple(pool), 'title')
        if len(matches) > 1:
            return Resolution(None, tuple(matches), 'ambiguous_title')
    if len(pool) == 1:
        return Resolution(pool[0], tuple(pool), 'only')
    focused = [w for w in pool if w.active]
    if len(focused) == 1:
        return Resolution(focused[0], tuple(pool), 'focused')
    return Resolution(None, tuple(pool), 'ambiguous')


def clarification(application, resolution):
    """The exact question asked when several windows remain."""
    lines = [f'{index}. {display_title(w)}' + (' (minimized)' if w.minimized else '')
             for index, w in enumerate(resolution.candidates[:9], 1)]
    lead = ('The window I was using is no longer open. ' if resolution.reason == 'bound_gone' else '')
    return (f'NEEDS_USER_CLARIFICATION: {lead}I found {len(resolution.candidates)} {application} windows:\n' +
            '\n'.join(lines) + '\n\nWhich one should I use? Nothing was done yet.')


GENERIC_REPLIES = {'tab', 'window', 'one', 'other', 'it', 'that', 'this', 'page', 'new', 'the', 'firefox', 'mozilla'}
ORDINALS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7,
            'eighth': 8, 'ninth': 9, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5}


def parse_choice(text, candidates):
    """Map a reply to a clarification ('2', 'the second one', 'the GitHub one') to one candidate."""
    reply = re.sub(r'[.!?]+$', '', (text or '').strip()).casefold()
    if not reply or len(reply) > 120:
        return None
    reply = re.sub(r'^(?:use|choose|pick|select|open|take)\s+', '', reply)
    reply = re.sub(r'^(?:the|number|no\.?|window|#)\s*', '', reply)
    reply = re.sub(r'\s+(?:one|window|tab)$', '', reply).strip()
    number = None
    if re.fullmatch(r'\d{1,2}', reply):
        number = int(reply)
    elif reply in ORDINALS:
        number = ORDINALS[reply]
    elif reply == 'last':
        number = len(candidates)
    if number is not None:
        return candidates[number - 1] if 1 <= number <= min(len(candidates), 9) else None
    if len(reply) < 3 or reply in GENERIC_REPLIES:
        return None
    matches = [c for c in candidates if title_matches(c, reply)]
    return matches[0] if len(matches) == 1 else None


@dataclass
class WindowBinding:
    """The task's bound window; every meaningful action re-verifies it."""
    app_id: str
    pid: int
    window_id: str
    title: str = ''
    output: str = ''
    bounds: tuple = ()
    revision: str = ''
    history: list = field(default_factory=list)

    @classmethod
    def of(cls, window, revision=''):
        return cls(window.app_id, window.pid, window.window_id, window.title, window.output, tuple(window.bounds),
                   revision)

    def verify(self, windows):
        """The bound window as it is now; raises when it vanished or changed owner."""
        found = [w for w in windows if w.window_id == self.window_id]
        if not found:
            raise WindowResolutionError('WINDOW_DISAPPEARED: the window OLIVE was using was closed; nothing further was done')
        window = found[0]
        if window.pid != self.pid or window.app_id.casefold() != self.app_id.casefold():
            raise WindowResolutionError('WINDOW_CHANGED: the window now belongs to another application; nothing further was done')
        return window

    def moved(self, window):
        return tuple(window.bounds) != tuple(self.bounds) or window.output != self.output

    def update(self, window, revision=''):
        self.title, self.output, self.bounds = window.title, window.output, tuple(window.bounds)
        if revision:
            self.revision = revision
