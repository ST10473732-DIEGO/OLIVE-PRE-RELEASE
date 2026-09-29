"""The OLIVE-owned CRDT adapter. pycrdt (Yjs update format v1) stays behind it.

A note is one Yjs document with a Text `body` and a Map `meta`. Every change is
captured as the exact Yjs update it produced; callers persist that update before
announcing it. Remote updates are idempotent: re-applying one changes nothing and
produces no update, which is what stops sync echo loops.
"""
from contextlib import contextmanager

import pycrdt

from .limits import BODY, META, DOCUMENT_SCHEMA, LIMITS
from . import statevector, text as notes_text


class DocumentError(ValueError):
    """A fixed category; never contains note content."""


class NoteDocument:
    def __init__(self):
        self.doc = pycrdt.Doc()
        self.body = self.doc.get(BODY, type=pycrdt.Text)
        self.meta = self.doc.get(META, type=pycrdt.Map)
        self._captured = None
        self._subscription = self.doc.observe(self._observed)

    def _observed(self, event):
        if self._captured is not None:
            self._captured.append(event.update)

    @contextmanager
    def capture(self):
        """Collect the updates a block produced, merged into one (or None)."""
        if self._captured is not None:
            raise DocumentError('nested_capture')
        self._captured = []
        result = {'update': None}
        try:
            yield result
        finally:
            captured, self._captured = self._captured, None
        if captured:
            result['update'] = captured[0] if len(captured) == 1 else pycrdt.merge_updates(*captured)

    # --- construction -----------------------------------------------------
    @classmethod
    def create(cls, *, device_id, now, title='', body=''):
        note = cls()
        with note.capture() as change:
            with note.doc.transaction():
                note.meta['schema'] = DOCUMENT_SCHEMA
                note.meta['created_at'] = now
                note.meta['created_by'] = device_id
                note.meta['edited_at'] = now
                note.meta['title'] = notes_text.normalize(title)[:LIMITS['max_title_chars']].strip()
                note.meta['pinned'] = False
                note.meta['trashed'] = False
                note.meta['trashed_at'] = ''
                if body:
                    note.body.insert(0, notes_text.normalize(body))
        note.check_size()
        return note, change['update']

    @classmethod
    def load(cls, snapshot, updates):
        """Rebuild from a snapshot plus logged updates. Raises on undecodable data."""
        note = cls()
        try:
            if snapshot:
                note.doc.apply_update(snapshot)
            for update in updates:
                note.doc.apply_update(update)
        except Exception:
            raise DocumentError('note_data_corrupted') from None
        return note

    # --- reads ------------------------------------------------------------
    def text(self):
        return str(self.body)

    def metadata(self):
        """Typed, bounded view. A peer can write any map value; ignore bad types."""
        raw = dict(self.meta)
        def string(key, limit=64):
            value = raw.get(key)
            return value[:limit] if isinstance(value, str) else ''
        title = raw.get('title')
        return {
            'title': title.strip()[:LIMITS['max_title_chars']] if isinstance(title, str) else '',
            'pinned': raw.get('pinned') is True,
            'trashed': raw.get('trashed') is True,
            'trashed_at': string('trashed_at'),
            'created_at': string('created_at'),
            'created_by': string('created_by'),
            'edited_at': string('edited_at') or string('created_at'),
        }

    def state_vector(self):
        return self.doc.get_state()

    def encode_state(self):
        return self.doc.get_update()

    def diff(self, remote_state_vector):
        """Everything the remote lacks, always including the full delete set."""
        statevector.decode(remote_state_vector)  # Validate before handing to Rust.
        return self.doc.get_update(remote_state_vector)

    def check_size(self):
        if notes_text.byte_size(self.text()) > LIMITS['max_note_text_bytes']:
            raise DocumentError('note_too_large')

    # --- local edits ------------------------------------------------------
    def splice(self, index, remove, insert):
        """Edit by code-point positions (Python str indices).

        pycrdt's Text indexes by UTF-8 byte offsets, so positions are converted
        here, and only here. Using code points directly would misplace edits
        in non-ASCII text and can split a character (see tests).
        """
        current = self.text()
        if not 0 <= index <= index + remove <= len(current):
            raise DocumentError('invalid_edit')
        start = len(current[:index].encode('utf-8'))
        if remove:
            end = start + len(current[index:index + remove].encode('utf-8'))
            del self.body[start:end]
        if insert:
            self.body.insert(start, insert)

    def _touch(self, now):
        if now and self.meta.get('edited_at') != now:
            self.meta['edited_at'] = now

    def replace_text(self, new_text, *, now=None):
        """Replace the whole body through one minimal CRDT edit."""
        new_text = notes_text.normalize(new_text)
        change = notes_text.diff(self.text(), new_text)
        if change is None:
            return None
        index, remove, insert = change
        with self.capture() as captured:
            with self.doc.transaction():
                self.splice(index, remove, insert)
                self._touch(now)
        return captured['update']

    def append_text(self, addition, *, now=None):
        addition = notes_text.normalize(addition)
        if not addition:
            return None
        current = self.text()
        if current and not current.endswith('\n'):
            addition = '\n' + addition
        with self.capture() as captured:
            with self.doc.transaction():
                self.splice(len(current), 0, addition)
                self._touch(now)
        return captured['update']

    def set_meta(self, *, now=None, **values):
        allowed = {'title', 'pinned', 'trashed', 'trashed_at'}
        if set(values) - allowed:
            raise DocumentError('invalid_metadata')
        if 'title' in values:
            values['title'] = notes_text.normalize(values['title']).strip()[:LIMITS['max_title_chars']]
        current = dict(self.meta)
        changes = {key: value for key, value in values.items() if current.get(key) != value}
        if not changes:
            return None
        with self.capture() as captured:
            with self.doc.transaction():
                for key, value in changes.items():
                    self.meta[key] = value
                if 'title' in changes:
                    self._touch(now)
        return captured['update']

    # --- remote -------------------------------------------------------------
    def apply_update(self, update):
        """Returns (changed, effective_update, pending).

        `pending` means the update names structs whose dependencies are not
        here yet; the raw update must still be kept durably.
        """
        if type(update) is not bytes or not update:
            raise DocumentError('invalid_update')
        try:
            incoming = statevector.decode(pycrdt.get_state(update))
        except Exception:
            raise DocumentError('invalid_update') from None
        with self.capture() as captured:
            try:
                self.doc.apply_update(update)
            except Exception:
                raise DocumentError('invalid_update') from None
        local = statevector.decode(self.state_vector())
        pending = not statevector.covers(local, incoming)
        return captured['update'] is not None, captured['update'], pending


def merge(updates):
    """Lossless merge of raw updates (keeps not-yet-integrable structs)."""
    updates = [u for u in updates if u]
    if not updates:
        return b''
    return updates[0] if len(updates) == 1 else pycrdt.merge_updates(*updates)
