"""Bounded conversational desktop context, per chat and in memory only.

It remembers just enough to let natural follow-ups work ("Go back", "Open
general") without repeating the application every turn:

* the current application and its bound window (identity, not a guess),
* the Discord server/channel that was last *verified*,
* the last verified observation revision and page URL OLIVE opened,
* one pending clarification or user hand-off.

Nothing here grants authority: a follow-up is still parsed from the new literal
user message and issued as a fresh finite task. Context expires, is replaced
when another application is used, and is never persisted, so a restart never
resumes desktop input. Selecting a different application drops the old one.
"""
from dataclasses import dataclass, field
import time

CONTEXT_SECONDS = 20 * 60
PENDING_SECONDS = 10 * 60


@dataclass
class DesktopContext:
    application: str = ''       # the name used in task scopes, e.g. "Firefox"
    app_id: str = ''            # installed desktop entry ID
    kind: str = ''              # browser | messaging | file_manager | terminal | editor | settings | app
    window: object = None       # window_targets.WindowBinding
    server: str = ''            # last verified messaging server
    destination: str = ''       # last verified messaging channel/conversation
    revision: str = ''          # last verified observation revision
    page_url: str = ''          # URL verified in a tab OLIVE opened (navigate in place next time)
    last_scope: object = None   # TaskScope of the last completed or attempted navigation
    last_request: str = ''
    candidates: tuple = ()      # windows offered in the last clarification
    pending: dict | None = None
    updated: float = 0.0
    default_browser: str = ''
    history: list = field(default_factory=list)

    def fresh(self, clock=time.monotonic):
        return bool(self.application) and clock() - self.updated < CONTEXT_SECONDS

    def pending_now(self, kind=None, clock=time.monotonic):
        if not self.pending or clock() - self.pending.get('created', 0) >= PENDING_SECONDS:
            return None
        return self.pending if kind is None or self.pending.get('kind') == kind else None


class DesktopContexts:
    def __init__(self, clock=time.monotonic, limit=50):
        self.clock, self.limit = clock, limit
        self.values = {}

    def get(self, chat_id):
        value = self.values.get(chat_id)
        if value is not None and not value.fresh(self.clock) and not value.pending_now(clock=self.clock):
            self.values.pop(chat_id, None)
            value = None
        return value or DesktopContext()

    def _slot(self, chat_id):
        if chat_id not in self.values and len(self.values) >= self.limit:
            oldest = min(self.values, key=lambda key: self.values[key].updated)
            self.values.pop(oldest)
        return self.values.setdefault(chat_id, DesktopContext())

    def select(self, chat_id, application, app_id='', kind='app'):
        """Use an application; a different application replaces the whole context."""
        value = self._slot(chat_id)
        if value.app_id and app_id and value.app_id != app_id or \
                value.application and value.application.casefold() != application.casefold() and not app_id:
            value = self.values[chat_id] = DesktopContext()
        value.application, value.kind = application, kind or value.kind or 'app'
        value.app_id = app_id or value.app_id
        value.updated = self.clock()
        return value

    def bind(self, chat_id, binding, revision=''):
        value = self._slot(chat_id)
        if value.window is not None and binding is not None and value.window.window_id != binding.window_id:
            value.page_url = ''  # a verified page belongs to its window
        value.window, value.revision, value.updated = binding, revision or value.revision, self.clock()
        return value

    def verified_destination(self, chat_id, server='', destination=''):
        value = self._slot(chat_id)
        value.server = server
        value.destination = destination
        value.updated = self.clock()

    def ask(self, chat_id, kind, **details):
        value = self._slot(chat_id)
        value.pending = {'kind': kind, 'created': self.clock(), **details}
        value.updated = self.clock()
        return value.pending

    def resolve_pending(self, chat_id):
        value = self.values.get(chat_id)
        pending = value.pending if value else None
        if value:
            value.pending = None
        return pending

    def invalidate_window(self, chat_id):
        value = self.values.get(chat_id)
        if value:
            value.window, value.revision, value.page_url = None, '', ''

    def clear(self, chat_id):
        self.values.pop(chat_id, None)
