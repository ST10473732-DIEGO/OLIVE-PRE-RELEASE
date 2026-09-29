"""NotesService: the one authoritative Notes owner in a process.

Every edit (renderer, Chat, history restore, import, remote peer) becomes a CRDT
update that is committed locally BEFORE anything is announced or sent. The sync
layer reads the durable change feed; it never holds edits only in memory.
Logs record note IDs, sizes and categories only, never note text.
"""
import base64
from collections import OrderedDict
from datetime import datetime, timezone
import json
import logging
import re
import secrets
import time
import uuid

from . import statevector, text as notes_text
from .document import DocumentError, NoteDocument, merge
from .limits import LIMITS
from .store import NotesStorageError, NotesStore, digest
from .worker import NotesWorker

logger = logging.getLogger(__name__)

HOT_DOCUMENTS = 24
INLINE_BRIDGE_BYTES = 600_000       # Base64 of this stays well below the 1 MiB bridge line.
EVENT_UPDATE_BYTES = 256_000
COMPACT_UPDATES = 200
COMPACT_BYTES = 262_144
HISTORY_IDLE_SECONDS = 45
HISTORY_MIN_INTERVAL = 300
HISTORY_PER_NOTE = 100
SEARCH_DELAY = 0.8
EVENT_DELAY = 0.15
EDITED_AT_THROTTLE = 10


class NotesError(ValueError):
    """User-facing, content-free Notes errors."""


MESSAGES = {
    'notes_unavailable': 'Notes storage unavailable. Your notes database was left untouched.',
    'notes_storage_newer': 'Notes storage was created by a newer OLIVE. It was left untouched.',
    'notes_storage_unrecognized': 'Notes storage migration failed. The original database was left untouched.',
    'notes_storage_unavailable': 'Notes storage unavailable. Your notes database was left untouched.',
    'note_not_found': 'That note no longer exists.',
    'note_purged': 'That note was permanently deleted.',
    'note_data_corrupted': 'Note data corrupted. The stored data was kept for recovery.',
    'note_too_large': 'Note too large. Notes can hold up to about 1.5 MB of text.',
    'notes_capacity': 'Notes limit reached. Delete notes you no longer need.',
    'invalid_update': 'Could not save locally: the edit was malformed.',
    'not_in_trash': 'Move the note to Recently Deleted before deleting it permanently.',
    'history_not_found': 'That history version is no longer available.',
}


def error(code):
    return NotesError(MESSAGES.get(code, 'Could not save locally.'))


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def b64(data):
    return base64.b64encode(data).decode('ascii')


def unb64(value, limit):
    if type(value) is not str or len(value) > (limit * 4) // 3 + 8:
        raise error('invalid_update')
    try:
        data = base64.b64decode(value, validate=True)
    except Exception:
        raise error('invalid_update') from None
    if len(data) > limit:
        raise error('invalid_update')
    return data


def note_id(value):
    if type(value) is not str:
        raise error('note_not_found')
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise error('note_not_found') from None
    return value


class NotesService:
    def __init__(self, path, *, device_id, publish=lambda topic, data: None, device_names=lambda: {},
                 clock=time.time, timers=True):
        self.path = path
        self.device_id = device_id
        self.publish = publish
        self.device_names = device_names
        self.clock = clock
        self.timers = timers
        self.worker = NotesWorker()
        self.store = None
        self.unavailable = None
        self.docs = OrderedDict()
        self.corrupt = set()
        self.dirty_search = set()
        self.sessions = {}
        self.last_checkpoint = {}    # note_id -> monotonic time of the last idle checkpoint
        self.changed_events = {}
        self.tokens = OrderedDict()
        self.uploads = OrderedDict()
        self.update_counts = {}
        self.listeners = []          # Sync layer: called on the worker with (note_id, peer).
        try:
            self.store = self.worker.call(NotesStore, path)
        except NotesStorageError as failure:
            self.unavailable = str(failure)
            logger.warning('Notes storage unavailable: %s', failure)
        except Exception:
            self.unavailable = 'notes_storage_unavailable'
            logger.warning('Notes storage unavailable')
        if self.store is not None and timers:
            self.worker.schedule('maintenance', 5, self._maintenance_tick)

    # --- plumbing -------------------------------------------------------------
    def run(self, function, *args, **kwargs):
        """Synchronous entry point used by threads (Connect, tests)."""
        return self.worker.call(self._guarded, function, *args, **kwargs)

    async def call(self, function, *args, **kwargs):
        import asyncio
        future = self.worker.submit(self._guarded, function, *args, **kwargs)
        return await asyncio.wrap_future(future)

    def _guarded(self, function, *args, **kwargs):
        if self.store is None:
            raise error(self.unavailable or 'notes_unavailable')
        return function(*args, **kwargs)

    def close(self):
        """Flush local work (search index, history, events); never waits for peers."""
        if self.store is not None:
            try:
                self.worker.call(self._flush_all, timeout=10)
            except Exception:
                logger.warning('Notes flush on shutdown failed')
        self.worker.stop()

    def _flush_all(self):
        self._flush_search()
        self._checkpoint_idle(force=True)
        self._flush_events()

    def now(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    # --- documents --------------------------------------------------------------
    def _document(self, nid):
        if nid in self.docs:
            self.docs.move_to_end(nid)
            return self.docs[nid]
        if nid in self.corrupt:
            raise error('note_data_corrupted')
        with self.store.transaction(read_only=True) as db:
            row = self.store.note(db, nid)
            if row is None:
                raise error('note_purged' if self.store.purged(db, nid) else 'note_not_found')
            snapshot, updates = self.store.document_data(db, nid)
        document = self._load(nid, snapshot, updates)
        self.docs[nid] = document
        self.update_counts[nid] = len(updates)
        while len(self.docs) > HOT_DOCUMENTS:
            self.docs.popitem(last=False)
        return document

    def _load(self, nid, snapshot, updates):
        payloads = [u['payload'] for u in updates]
        bad_snapshot = snapshot is not None and digest(snapshot['state']) != snapshot['sha256']
        bad_updates = any(digest(u['payload']) != u['sha256'] for u in updates)
        if not bad_snapshot and not bad_updates:
            try:
                return NoteDocument.load(snapshot['state'] if snapshot else b'', payloads)
            except DocumentError:
                pass
        # Recovery attempt: skip only the corrupted pieces, and only if what remains
        # still contains the note's creation. Never silently present an empty note.
        good = [u['payload'] for u in updates if digest(u['payload']) == u['sha256']]
        base = snapshot['state'] if snapshot and not bad_snapshot else b''
        try:
            candidate = NoteDocument.load(base, good)
            if candidate.metadata()['created_at']:
                logger.warning('Note %s recovered from valid snapshot/updates', nid)
                return candidate
        except DocumentError:
            pass
        self.corrupt.add(nid)
        with self.store.transaction() as db:
            db.execute("UPDATE notes SET status='corrupt' WHERE note_id=?", (nid,))
        logger.warning('Note %s marked corrupted; data retained', nid)
        raise error('note_data_corrupted')

    def _summary(self, row):
        return {'note_id': row['note_id'], 'title': row['title'], 'display_title': row['display_title'],
                'preview': row['preview'], 'pinned': bool(row['pinned']), 'trashed': bool(row['trashed']),
                'trashed_at': row['trashed_at'], 'created_at': row['created_at'], 'edited_at': row['edited_at'],
                'text_length': row['text_length'], 'status': row['status']}

    def _write_row(self, db, nid, document, *, seq, peer=None, created=False):
        meta = document.metadata()
        body = document.text()
        now = self.now()
        values = dict(
            created_at=meta['created_at'] or now, created_by=meta['created_by'], title=meta['title'],
            display_title=notes_text.display_title(meta['title'], body),
            preview=notes_text.preview(meta['title'], body), pinned=int(meta['pinned']),
            trashed=int(meta['trashed']), trashed_at=meta['trashed_at'], edited_at=meta['edited_at'] or now,
            local_updated_at=now, text_length=len(body), state_bytes=0, change_seq=seq, last_change_peer=peer)
        if created:
            db.execute('INSERT INTO notes(note_id,created_at,created_by,title,display_title,preview,pinned,trashed,'
                       'trashed_at,edited_at,local_updated_at,text_length,state_bytes,change_seq,last_change_peer) '
                       'VALUES(:note_id,:created_at,:created_by,:title,:display_title,:preview,:pinned,:trashed,'
                       ':trashed_at,:edited_at,:local_updated_at,:text_length,:state_bytes,:change_seq,:last_change_peer)',
                       dict(values, note_id=nid))
        else:
            db.execute('UPDATE notes SET created_at=:created_at,created_by=:created_by,title=:title,'
                       'display_title=:display_title,preview=:preview,pinned=:pinned,trashed=:trashed,'
                       'trashed_at=:trashed_at,edited_at=:edited_at,local_updated_at=:local_updated_at,'
                       'text_length=:text_length,change_seq=:change_seq,last_change_peer=:last_change_peer '
                       'WHERE note_id=:note_id', dict(values, note_id=nid))
        return self._summary(self.store.note(db, nid))

    def _commit(self, nid, document, updates, *, origin, device, peer=None, created=False, view=None,
                content_changed=True, reason='changed'):
        """One transaction: CRDT updates + row + change feed. Then announce."""
        updates = [u for u in updates if u]
        if not updates:
            return None
        with self.store.transaction() as db:
            if created:
                if db.execute('SELECT COUNT(*) FROM notes').fetchone()[0] >= LIMITS['max_notes']:
                    raise error('notes_capacity')
            seq = self.store.next_seq(db)
            now = self.now()
            summary = self._write_row(db, nid, document, seq=seq, peer=peer, created=created)
            for update in updates:
                update_id = ('r:' + digest(nid.encode() + update)) if origin == 'remote' else None
                self.store.append_update(db, nid, update, origin=origin, device_id=device, now=now, update_id=update_id)
        self.update_counts[nid] = self.update_counts.get(nid, 0) + len(updates)
        if content_changed:
            self.dirty_search.add(nid)
            self._schedule('search', SEARCH_DELAY, self._flush_search)
            session = self.sessions.setdefault(nid, {'devices': set(), 'last': 0.0})
            session['devices'].add(device)
            session['last'] = time.monotonic()
        for update in updates:
            if len(update) <= EVENT_UPDATE_BYTES:
                self.publish('notes.update', {'note_id': nid, 'update': b64(update), 'origin': origin, 'view': view or ''})
            else:
                self.publish('notes.resync', {'note_id': nid})
        self._changed(nid, reason)
        for listener in list(self.listeners):
            try:
                listener(nid, peer)
            except Exception:
                logger.warning('Notes change listener failed')
        if self.update_counts[nid] >= COMPACT_UPDATES:
            self._schedule('compact:' + nid, 2, lambda: self._compact(nid))
        return summary

    def _schedule(self, key, delay, function):
        if self.timers:
            self.worker.schedule(key, delay, function)
        else:
            self.worker.schedule(key, 3600, function)  # Tests flush explicitly.

    def _changed(self, nid, reason):
        self.changed_events[nid] = reason
        self._schedule('events', EVENT_DELAY, self._flush_events)

    def _flush_events(self):
        if not self.changed_events:
            return
        items, self.changed_events = self.changed_events, {}
        self.publish('notes.changed', {'note_ids': sorted(items)[:500], 'reasons': sorted(set(items.values()))})

    def flush(self):
        """Tests and shutdown: run every pending timer now."""
        self.worker.run_due(all_timers=True)

    # --- queries ----------------------------------------------------------------
    def list_notes(self, view='notes'):
        if view not in ('notes', 'trash'):
            raise NotesError('Unknown Notes view')
        order = 'trashed_at DESC, edited_at DESC' if view == 'trash' else 'pinned DESC, edited_at DESC, note_id'
        with self.store.transaction(read_only=True) as db:
            rows = db.execute(f'SELECT * FROM notes WHERE trashed=? ORDER BY {order} LIMIT ?',
                              (int(view == 'trash'), LIMITS['max_notes'])).fetchall()
            counts = dict(db.execute('SELECT trashed, COUNT(*) FROM notes GROUP BY trashed').fetchall())
        return {'notes': [self._summary(row) for row in rows], 'counts': {'notes': counts.get(0, 0), 'trash': counts.get(1, 0)}}

    def get(self, nid):
        nid = note_id(nid)
        with self.store.transaction(read_only=True) as db:
            row = self.store.note(db, nid)
            if row is None:
                raise error('note_purged' if self.store.purged(db, nid) else 'note_not_found')
        return self._summary(row)

    def read_text(self, nid):
        nid = note_id(nid)
        document = self._document(nid)
        summary = self.get(nid)
        body = document.text()
        return dict(summary, text=body, revision=digest(document.encode_state())[:16], sha256=digest(body))

    def open(self, nid):
        nid = note_id(nid)
        document = self._document(nid)
        return dict(self._deliver(document.encode_state()), note=self.get(nid))

    def state_since(self, nid, state_vector):
        nid = note_id(nid)
        document = self._document(nid)
        try:
            update = document.diff(unb64(state_vector, LIMITS['max_state_vector_bytes']))
        except (DocumentError, statevector.StateVectorError):
            raise error('invalid_update') from None
        return self._deliver(update)

    def _deliver(self, data):
        if len(data) <= INLINE_BRIDGE_BYTES:
            return {'state': b64(data), 'chunks': 0, 'token': ''}
        token = secrets.token_hex(16)
        self.tokens[token] = (time.monotonic() + 120, data)
        while len(self.tokens) > 4:
            self.tokens.popitem(last=False)
        return {'state': '', 'chunks': -(-len(data) // INLINE_BRIDGE_BYTES), 'token': token}

    def state_chunk(self, token, index):
        expires, data = self.tokens.get(token, (0, b''))
        if expires < time.monotonic() or type(index) is not int or not 0 <= index * INLINE_BRIDGE_BYTES < len(data):
            raise NotesError('The note transfer expired. Reopen the note.')
        return {'data': b64(data[index * INLINE_BRIDGE_BYTES:(index + 1) * INLINE_BRIDGE_BYTES])}

    # --- local edits ---------------------------------------------------------------
    def create(self, title='', body='', *, origin='local', reason='created'):
        if type(title) is not str or type(body) is not str:
            raise NotesError('Invalid note')
        nid = str(uuid.uuid4())
        try:
            document, update = NoteDocument.create(device_id=self.device_id, now=self.now(), title=title, body=body)
        except DocumentError as failure:
            raise error(str(failure)) from None
        self.docs[nid] = document
        try:
            summary = self._commit(nid, document, [update], origin=origin, device=self.device_id, created=True, reason=reason)
        except BaseException:
            self.docs.pop(nid, None)
            raise
        if body:
            self._checkpoint(nid, reason)
        return summary

    def apply_update(self, nid, update, *, view=None, upload=None, origin='local'):
        """A renderer (or local phone UI) Yjs update. Idempotent."""
        nid = note_id(nid)
        raw = self._assemble(nid, update, upload)
        if raw is None:
            return {'saved': False, 'partial': True}
        document = self._document(nid)
        before_text = document.text()
        try:
            changed, effective, pending = document.apply_update(raw)
            document.check_size()
        except DocumentError as failure:
            self.docs.pop(nid, None)  # Discard the in-memory state; storage is authoritative.
            raise error(str(failure)) from None
        if not changed and not pending:
            return {'saved': True, 'changed': False}
        content = document.text() != before_text
        summary = self._commit(nid, document, [raw if pending else effective], origin=origin, device=self.device_id,
                               view=view, content_changed=content, reason='edited' if content else 'metadata')
        touch = self._touch(document) if content else None
        if touch:
            # The editor's own replica must receive this backend-made change too.
            summary = self._commit(nid, document, [touch], origin=origin, device=self.device_id, view=None,
                                   content_changed=False, reason='metadata')
        return {'saved': True, 'changed': True, 'note': summary}

    def _touch(self, document):
        edited = document.metadata()['edited_at']
        try:
            age = self.clock() - datetime.fromisoformat(edited.replace('Z', '+00:00')).timestamp()
        except ValueError:
            age = EDITED_AT_THROTTLE
        if age < EDITED_AT_THROTTLE:
            return None
        with document.capture() as captured:
            with document.doc.transaction():
                document.meta['edited_at'] = self.now()
        return captured['update']

    def _assemble(self, nid, update, upload):
        if upload is None:
            return unb64(update, LIMITS['max_inline_update_bytes'] * 4)
        if (type(upload) is not dict or set(upload) != {'id', 'index', 'count'} or type(upload['id']) is not str
                or not 1 <= len(upload['id']) <= 64 or type(upload['index']) is not int or type(upload['count']) is not int
                or not 1 <= upload['count'] <= 24 or not 0 <= upload['index'] < upload['count']):
            raise error('invalid_update')
        key = (nid, upload['id'])
        parts = self.uploads.setdefault(key, {'count': upload['count'], 'parts': {}, 'expires': time.monotonic() + 120})
        if parts['count'] != upload['count'] or parts['expires'] < time.monotonic():
            self.uploads.pop(key, None)
            raise error('invalid_update')
        parts['parts'][upload['index']] = unb64(update, INLINE_BRIDGE_BYTES)
        while len(self.uploads) > 4:
            self.uploads.popitem(last=False)
        if len(parts['parts']) < parts['count']:
            return None
        self.uploads.pop(key, None)
        data = b''.join(parts['parts'][i] for i in range(parts['count']))
        if len(data) > LIMITS['max_document_bytes']:
            raise error('note_too_large')
        return data

    def _edit(self, nid, action, *, origin, reason, checkpoint_before=False):
        nid = note_id(nid)
        document = self._document(nid)
        if checkpoint_before:
            self._checkpoint(nid, 'before-' + reason)
        before = document.text()
        try:
            update = action(document)
            document.check_size()
        except DocumentError as failure:
            self.docs.pop(nid, None)
            raise error(str(failure)) from None
        if update is None:
            return self.get(nid)
        content = document.text() != before
        return self._commit(nid, document, [update], origin=origin, device=self.device_id,
                            content_changed=content, reason=reason)

    def replace_text(self, nid, body, *, origin='local', reason='edited'):
        if type(body) is not str:
            raise NotesError('Invalid note text')
        return self._edit(nid, lambda d: d.replace_text(body, now=self.now()), origin=origin, reason=reason)

    def append_text(self, nid, addition, *, origin='local'):
        if type(addition) is not str or not addition.strip():
            raise NotesError('Nothing to add')
        return self._edit(nid, lambda d: d.append_text(addition, now=self.now()), origin=origin, reason='edited')

    def rename(self, nid, title, *, origin='local'):
        if type(title) is not str or len(title) > LIMITS['max_title_chars']:
            raise NotesError('Titles can be up to 200 characters')
        summary = self._edit(nid, lambda d: d.set_meta(title=title, now=self.now()), origin=origin, reason='renamed')
        self._checkpoint(note_id(nid), 'rename')
        return summary

    def set_pinned(self, nid, pinned, *, origin='local'):
        if type(pinned) is not bool:
            raise NotesError('Invalid pin state')
        return self._edit(nid, lambda d: d.set_meta(pinned=pinned), origin=origin, reason='pinned')

    def trash(self, nid, *, origin='local'):
        nid = note_id(nid)
        self._checkpoint(nid, 'trash')
        return self._edit(nid, lambda d: d.set_meta(trashed=True, trashed_at=self.now()), origin=origin, reason='trashed')

    def restore(self, nid, *, origin='local'):
        return self._edit(nid, lambda d: d.set_meta(trashed=False, trashed_at=''), origin=origin, reason='restored')

    def duplicate(self, nid):
        source = self.read_text(nid)
        title = (source['title'] + ' (copy)')[:LIMITS['max_title_chars']] if source['title'] else ''
        return self.create(title, source['text'], reason='duplicated')

    def purge(self, nid, *, origin='local', peer=None):
        """Permanent deletion. Only from Recently Deleted, except when a peer's
        durable purge marker arrives (that is already an explicit decision)."""
        nid = note_id(nid)
        with self.store.transaction() as db:
            if self.store.purged(db, nid):
                return {'purged': True}
            row = self.store.note(db, nid)
            if origin != 'remote' and (row is None or not row['trashed']):
                raise error('not_in_trash' if row is not None else 'note_not_found')
            seq = self.store.next_seq(db)
            db.execute('DELETE FROM notes WHERE note_id=?', (nid,))
            db.execute('DELETE FROM note_history WHERE note_id=?', (nid,))
            self.store.delete_search(db, nid)
            db.execute('INSERT INTO note_purges VALUES(?,?,?,?)', (nid, self.now(), peer or self.device_id, seq))
        self.docs.pop(nid, None)
        self.dirty_search.discard(nid)
        self.sessions.pop(nid, None)
        self.corrupt.discard(nid)
        self.publish('notes.purged', {'note_id': nid})
        self._changed(nid, 'purged')
        for listener in list(self.listeners):
            try:
                listener(nid, peer)
            except Exception:
                logger.warning('Notes change listener failed')
        return {'purged': True}

    def import_text(self, title, body):
        body = notes_text.normalize(body)
        if notes_text.byte_size(body) > LIMITS['max_note_text_bytes']:
            raise error('note_too_large')
        return self.create(title[:LIMITS['max_title_chars']], body, reason='imported')

    def export_text(self, nid, fmt='txt'):
        note = self.read_text(nid)
        if fmt == 'md' and note['title']:
            return '# ' + note['title'] + '\n\n' + note['text']
        return note['text']

    # --- search -----------------------------------------------------------------------
    def _flush_search(self):
        dirty, self.dirty_search = self.dirty_search, set()
        for nid in sorted(dirty):
            try:
                document = self._document(nid)
            except NotesError:
                continue
            meta = document.metadata()
            body = document.text()
            with self.store.transaction() as db:
                if self.store.note(db, nid) is not None:
                    self.store.write_search(db, nid, notes_text.display_title(meta['title'], body), body)

    def search(self, query, *, include_trash=False, limit=50):
        if type(query) is not str or not query.strip() or len(query) > 500:
            return {'results': []}
        self._flush_search()
        query = notes_text.normalize(query).strip()
        tokens = re.findall(r'\w+', query, re.UNICODE)
        found = OrderedDict()
        with self.store.transaction(read_only=True) as db:
            if self.store.fts and tokens and all(t.isascii() for t in tokens):
                expression = ' AND '.join('"' + t.replace('"', '') + '"*' for t in tokens[:12])
                try:
                    for row in db.execute('SELECT note_id FROM note_search WHERE note_search MATCH ? ORDER BY rank LIMIT ?',
                                          (expression, limit)):
                        found[row[0]] = True
                except Exception:
                    pass
            if len(found) < limit:
                table = 'note_search' if self.store.fts else 'note_search_plain'
                needle = query.casefold()
                for row in db.execute(f'SELECT note_id FROM {table} WHERE instr(lower(title), lower(?)) OR instr(lower(body), lower(?)) LIMIT ?',
                                      (needle, needle, limit * 2)):
                    found.setdefault(row[0], True)
            results = []
            table = 'note_search' if self.store.fts else 'note_search_plain'
            for nid in list(found)[:limit]:
                row = self.store.note(db, nid)
                if row is None or (row['trashed'] and not include_trash):
                    continue
                indexed = db.execute(f'SELECT body FROM {table} WHERE note_id=?', (nid,)).fetchone()
                results.append(dict(self._summary(row), snippet=self._snippet(indexed[0] if indexed else '', query, tokens)))
        return {'results': results}

    @staticmethod
    def _snippet(body, query, tokens):
        position = body.casefold().find(query.casefold())
        if position < 0 and tokens:
            position = body.casefold().find(tokens[0].casefold())
        if position < 0:
            return ''
        start = max(0, position - 50)
        return re.sub(r'\s+', ' ', body[start:position + len(query) + 70]).strip()

    # --- history ----------------------------------------------------------------------
    def _checkpoint(self, nid, reason):
        try:
            document = self._document(nid)
        except NotesError:
            return None
        body = document.text()
        title = document.metadata()['title']
        fingerprint = digest(title + '\x00' + body)
        with self.store.transaction() as db:
            last = db.execute('SELECT sha256 FROM note_history WHERE note_id=? ORDER BY created_at DESC LIMIT 1',
                              (nid,)).fetchone()
            if last and last['sha256'] == fingerprint and not reason.startswith('before-'):
                return None
            session = self.sessions.get(nid)
            devices = sorted(session['devices']) if session else [self.device_id]
            db.execute('INSERT INTO note_history VALUES(?,?,?,?,?,?,?,?)',
                       (str(uuid.uuid4()), nid, self.now(), reason, json.dumps(devices), title, body, fingerprint))
            db.execute('DELETE FROM note_history WHERE note_id=? AND history_id NOT IN (SELECT history_id FROM '
                       'note_history WHERE note_id=? ORDER BY created_at DESC LIMIT ?)', (nid, nid, HISTORY_PER_NOTE))
        if session:
            session['devices'] = set()
            session['checkpointed'] = time.monotonic()
        return True

    def _checkpoint_idle(self, force=False):
        """After 45 s without edits: one checkpoint, at most every 5 minutes per note."""
        now = time.monotonic()
        for nid, session in list(self.sessions.items()):
            if not force and now - session['last'] < HISTORY_IDLE_SECONDS:
                continue
            previous = self.last_checkpoint.get(nid)
            if force or previous is None or now - previous >= HISTORY_MIN_INTERVAL:
                if self._checkpoint(nid, 'edit'):
                    self.last_checkpoint[nid] = now
                self.sessions.pop(nid, None)
            # Otherwise keep the session (and its devices) for the next checkpoint.

    def history(self, nid):
        nid = note_id(nid)
        names = self.device_names() or {}
        current = self._document(nid)
        current_fingerprint = digest(current.metadata()['title'] + '\x00' + current.text())
        with self.store.transaction(read_only=True) as db:
            rows = db.execute('SELECT history_id,created_at,reason,devices,title,length(body) AS size,sha256 FROM note_history '
                              'WHERE note_id=? ORDER BY created_at DESC', (nid,)).fetchall()
        items = []
        for row in rows:
            devices = [d for d in json.loads(row['devices']) if isinstance(d, str)]
            items.append({'history_id': row['history_id'], 'created_at': row['created_at'], 'reason': row['reason'],
                          'devices': [{'device_id': d, 'name': 'This computer' if d == self.device_id else names.get(d, 'Paired device')}
                                      for d in devices[:8]],
                          'title': row['title'], 'size': row['size'], 'current': row['sha256'] == current_fingerprint})
        return {'history': items}

    def history_text(self, history_id):
        with self.store.transaction(read_only=True) as db:
            row = db.execute('SELECT note_id,title,body,created_at FROM note_history WHERE history_id=?', (history_id,)).fetchone()
        if row is None:
            raise error('history_not_found')
        return {'note_id': row['note_id'], 'title': row['title'], 'text': row['body'], 'created_at': row['created_at']}

    def restore_history(self, nid, history_id):
        """History restore is a NEW collaborative edit, never a rewind."""
        nid = note_id(nid)
        entry = self.history_text(history_id)
        if entry['note_id'] != nid:
            raise error('history_not_found')
        self._checkpoint(nid, 'before-restore')
        def action(document):
            with document.capture() as captured:
                with document.doc.transaction():
                    new_text = notes_text.normalize(entry['text'])
                    change = notes_text.diff(document.text(), new_text)
                    if change:
                        document.splice(*change)
                    if dict(document.meta).get('title') != entry['title']:
                        document.meta['title'] = entry['title']
                    document.meta['edited_at'] = self.now()
            return captured['update']
        summary = self._edit(nid, action, origin='history-restore', reason='history-restored')
        self._checkpoint(nid, 'restored')
        return summary

    # --- maintenance --------------------------------------------------------------------
    def _maintenance_tick(self):
        try:
            self._checkpoint_idle()
            self._flush_search()
            for token, (expires, _) in list(self.tokens.items()):
                if expires < time.monotonic():
                    self.tokens.pop(token, None)
            for nid, count in list(self.update_counts.items()):
                if count >= COMPACT_UPDATES:
                    self._compact(nid)
        finally:
            if self.timers:
                self.worker.schedule('maintenance', 5, self._maintenance_tick)

    def _compact(self, nid):
        """Fold logged updates into a verified snapshot. Lossless merge, so a
        stale peer can still catch up by state-vector diff afterwards."""
        with self.store.transaction() as db:
            row = self.store.note(db, nid)
            if row is None or row['status'] != 'ok':
                return False
            snapshot, updates = self.store.document_data(db, nid)
            if len(updates) < 2 and snapshot is not None:
                self.update_counts[nid] = len(updates)
                return False
            last = db.execute('SELECT MAX(seq) FROM note_updates WHERE note_id=?', (nid,)).fetchone()[0]
            parts = ([snapshot['state']] if snapshot else []) + [u['payload'] for u in updates]
            if any(digest(u['payload']) != u['sha256'] for u in updates) or (snapshot and digest(snapshot['state']) != snapshot['sha256']):
                return False
            merged = merge(parts)
            check = NoteDocument.load(merged, [])
            reference = NoteDocument.load(b'', parts)
            if check.text() != reference.text() or check.state_vector() != reference.state_vector() or check.metadata() != reference.metadata():
                logger.warning('Note %s compaction verification failed; log kept', nid)
                return False
            folded = (snapshot['folded_updates'] if snapshot else 0) + len(updates)
            db.execute('INSERT INTO note_snapshots VALUES(?,?,?,?,?) ON CONFLICT(note_id) DO UPDATE SET '
                       'state=excluded.state, sha256=excluded.sha256, created_at=excluded.created_at, '
                       'folded_updates=excluded.folded_updates', (nid, merged, digest(merged), self.now(), folded))
            db.execute('DELETE FROM note_updates WHERE note_id=? AND seq<=?', (nid, last))
            db.execute('UPDATE notes SET state_bytes=? WHERE note_id=?', (len(merged), nid))
        self.update_counts[nid] = 0
        return True

    def storage_stats(self):
        with self.store.transaction(read_only=True) as db:
            return {'notes': db.execute('SELECT COUNT(*) FROM notes').fetchone()[0],
                    'updates': db.execute('SELECT COUNT(*) FROM note_updates').fetchone()[0],
                    'update_bytes': db.execute('SELECT COALESCE(SUM(length(payload)),0) FROM note_updates').fetchone()[0],
                    'snapshot_bytes': db.execute('SELECT COALESCE(SUM(length(state)),0) FROM note_snapshots').fetchone()[0],
                    'purges': db.execute('SELECT COUNT(*) FROM note_purges').fetchone()[0]}

    # --- sync-facing (called on the worker by the sync engine) ---------------------------
    def epoch(self):
        with self.store.transaction(read_only=True) as db:
            return self.store.meta_value(db, 'epoch')

    def peer(self, device):
        with self.store.transaction(read_only=True) as db:
            row = db.execute('SELECT * FROM note_peers WHERE device_id=?', (device,)).fetchone()
        return dict(row) if row else {'device_id': device, 'acked_seq': 0, 'peer_epoch': None, 'last_sync': None,
                                       'last_error': None, 'protocol': None}

    def save_peer(self, device, **values):
        allowed = {'acked_seq', 'peer_epoch', 'last_sync', 'last_error', 'protocol'}
        if set(values) - allowed:
            raise ValueError('invalid peer state')
        with self.store.transaction() as db:
            db.execute('INSERT OR IGNORE INTO note_peers(device_id) VALUES(?)', (device,))
            for key, value in values.items():
                db.execute(f'UPDATE note_peers SET {key}=? WHERE device_id=?', (value, device))

    def pending(self, device, after, limit):
        """Change feed after `after` for one peer: (seq, note_id, purged, skip)."""
        with self.store.transaction(read_only=True) as db:
            notes = db.execute("SELECT change_seq,note_id,last_change_peer,status FROM notes WHERE change_seq>? "
                               "ORDER BY change_seq LIMIT ?", (after, limit)).fetchall()
            purges = db.execute('SELECT change_seq,note_id FROM note_purges WHERE change_seq>? ORDER BY change_seq LIMIT ?',
                                (after, limit)).fetchall()
        feed = [(r['change_seq'], r['note_id'], False, r['last_change_peer'] == device or r['status'] != 'ok') for r in notes]
        feed += [(r['change_seq'], r['note_id'], True, False) for r in purges]
        feed.sort()
        return feed[:limit]

    def pending_count(self, device):
        acked = self.peer(device)['acked_seq']
        with self.store.transaction(read_only=True) as db:
            notes = db.execute('SELECT COUNT(*) FROM notes WHERE change_seq>? AND status=? AND '
                               '(last_change_peer IS NULL OR last_change_peer<>?)', (acked, 'ok', device)).fetchone()[0]
            purges = db.execute('SELECT COUNT(*) FROM note_purges WHERE change_seq>?', (acked,)).fetchone()[0]
        return notes + purges

    def is_purged(self, nid):
        with self.store.transaction(read_only=True) as db:
            return self.store.purged(db, nid)

    def state_vector_of(self, nid):
        """(state_vector, exists). A note we have never seen has an empty vector."""
        try:
            return self._document(nid).state_vector(), True
        except NotesError:
            return b'\x00', False

    def document(self, nid):
        return self._document(nid)

    def apply_remote(self, nid, update, peer):
        """Apply a peer's update. Returns (status, state_vector)."""
        with self.store.transaction(read_only=True) as db:
            if self.store.purged(db, nid):
                return 'purged', b'\x00'
            row = self.store.note(db, nid)
            acked = db.execute('SELECT acked_seq FROM note_peers WHERE device_id=?', (peer,)).fetchone()
        if nid in self.corrupt or (row is not None and row['status'] != 'ok'):
            return 'rejected', b'\x00'
        created = row is None
        document = NoteDocument() if created else self._document(nid)
        before = document.text()
        try:
            changed, effective, pending = document.apply_update(update)
            document.check_size()
        except DocumentError as failure:
            self.docs.pop(nid, None)
            return ('rejected:' + str(failure)), b'\x00'
        if changed or pending:
            # The peer already has everything we have for this note only if our
            # previous state had been delivered to it (or the note is new to us).
            delivered = created or row['last_change_peer'] == peer or row['change_seq'] <= (acked['acked_seq'] if acked else 0)
            self.docs[nid] = document
            try:
                self._commit(nid, document, [update if pending else effective], origin='remote', device=peer,
                             peer=peer if delivered else None, created=created,
                             content_changed=document.text() != before, reason='remote')
            except NotesError:
                self.docs.pop(nid, None)
                return 'rejected:notes_capacity', b'\x00'
            except BaseException:
                self.docs.pop(nid, None)  # Storage is authoritative; reload next time.
                raise
            while len(self.docs) > HOT_DOCUMENTS:
                self.docs.popitem(last=False)
        return 'applied', document.state_vector()

    def status(self):
        with self.store.transaction(read_only=True) as db:
            total = db.execute('SELECT COUNT(*) FROM notes').fetchone()[0]
            corrupt = db.execute("SELECT COUNT(*) FROM notes WHERE status<>'ok'").fetchone()[0]
        return {'available': True, 'notes': total, 'corrupted': corrupt}
