"""Ephemeral typed data; result text can never supply action parameters."""
from dataclasses import dataclass
import hashlib
import time


@dataclass(frozen=True)
class TaskResult:
    kind: str
    text: str
    digest: str
    parents: tuple[str, ...]
    application: str = ''
    window_id: str = ''
    producing_step: str = ''
    created: float = 0.
    trust: str = 'untrusted_observation'
    content_allowed: bool = False   # May fill requested content (only verified derived text).
    target_allowed: bool = False    # May select a location for a later read (never a new effect).


# Result kinds and what they may supply. Paths, applications, recipients and
# message bodies are never taken from results; they stay original-request data.
KINDS = {'location': ('verified_location', False, True), 'link': ('verified_link_location', False, True),
         'observation': ('untrusted_observation', False, False), 'text': ('extractive_summary', True, False)}


class TaskResults:
    def __init__(self, request, epoch, clock=time.monotonic):
        self.request_digest = hashlib.sha256(request.encode()).hexdigest()
        self.epoch, self.clock = epoch, clock
        self.expires = clock() + 600
        self.values = {}
        self.closed = False

    def check(self, epoch):
        if self.closed or epoch != self.epoch or self.clock() >= self.expires:
            raise InterruptedError('Task results expired or were cancelled')

    def observation(self, key, text, epoch, source=''):
        self.check(epoch)
        if key in self.values or not isinstance(text, str) or not 1 <= len(text) <= 16000:
            raise ValueError('Invalid task observation')
        parent = self.values.get(source) if source else None
        if source and (parent is None or parent.kind not in {'location', 'link'}):
            raise PermissionError('Observation location provenance is missing')
        self.values[key] = self._result('observation', text, (source,) if source else (),
            parent.application if parent else '', parent.window_id if parent else '', key)

    def _result(self, kind, text, parents, application, window_id, key):
        trust, content, target = KINDS[kind]
        return TaskResult(kind, text, hashlib.sha256(text.encode()).hexdigest(), parents, application, window_id,
                          key, self.clock(), trust, content, target)

    def location(self, key, uri, application, window_id, epoch):
        self.check(epoch)
        if key in self.values or not window_id:
            raise ValueError('A location requires a unique verified window')
        self.values[key] = self._result('location', uri, (), application, window_id, key)

    def link(self, key, label, application, window_id, epoch):
        """A verified click on a user-named link: a location for a later read only."""
        self.check(epoch)
        if key in self.values or not window_id or not label:
            raise ValueError('A followed link requires a unique verified window')
        self.values[key] = self._result('link', label, (), application, window_id, key)

    def source_location(self, key, application, epoch):
        self.check(epoch)
        value = self.values.get(key)
        if not value or value.kind not in {'location', 'link'} or value.application != application:
            raise PermissionError('RESULT_PROVENANCE_INVALID: the observation source is not a verified task location')
        return value

    def summary(self, key, source, excerpts, epoch):
        self.check(epoch)
        original = self.values.get(source)
        if not original or original.kind != 'observation' or key in self.values:
            raise ValueError('Summary requires a verified task-local observation')
        if (not isinstance(excerpts, list) or not 1 <= len(excerpts) <= 12 or
                any(not isinstance(s, str) or not s.strip() or s not in original.text for s in excerpts)):
            raise ValueError('Summary facts must be exact excerpts from the observed source')
        text = '\n'.join('- ' + s.strip() for s in excerpts) + '\n'
        if len(text) > 4000 or any(ord(c) < 32 and c not in '\n\t' for c in text):
            raise ValueError('Derived note exceeds the text budget')
        self.values[key] = self._result('text', text, (source,), '', '', key)
        return text

    def text(self, key, epoch):
        self.check(epoch)
        value = self.values.get(key)
        if not value or value.kind != 'text' or not value.content_allowed:
            raise ValueError('Only verified derived text may supply note content')
        return value.text

    def close(self):
        self.closed = True
        self.values.clear()
