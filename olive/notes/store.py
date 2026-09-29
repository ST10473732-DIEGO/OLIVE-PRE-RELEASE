"""Durable Notes storage: one SQLite database, versioned migrations, WAL.

Every note mutation commits its CRDT update, its metadata row and the change
feed position in ONE transaction, so a crash cannot leave metadata that claims
an edit whose document data is missing. Nothing here deletes an unreadable or
newer database; the service reports "Notes storage unavailable" instead.
"""
from contextlib import contextmanager, closing
import hashlib
import os
import sqlite3
import threading
import uuid


class NotesStorageError(RuntimeError):
    """Fixed, content-free storage failure categories."""


SCHEMA = '''
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE notes(
    note_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    display_title TEXT NOT NULL,
    preview TEXT NOT NULL DEFAULT '',
    pinned INTEGER NOT NULL DEFAULT 0,
    trashed INTEGER NOT NULL DEFAULT 0,
    trashed_at TEXT NOT NULL DEFAULT '',
    edited_at TEXT NOT NULL,
    local_updated_at TEXT NOT NULL,
    text_length INTEGER NOT NULL DEFAULT 0,
    state_bytes INTEGER NOT NULL DEFAULT 0,
    change_seq INTEGER NOT NULL,
    last_change_peer TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    schema_version INTEGER NOT NULL DEFAULT 1);
CREATE INDEX notes_change ON notes(change_seq);
CREATE TABLE note_snapshots(
    note_id TEXT PRIMARY KEY REFERENCES notes(note_id) ON DELETE CASCADE,
    state BLOB NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
    folded_updates INTEGER NOT NULL);
CREATE TABLE note_updates(
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id TEXT NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE,
    update_id TEXT NOT NULL UNIQUE,
    origin TEXT NOT NULL,
    device_id TEXT NOT NULL,
    payload BLOB NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL);
CREATE INDEX note_updates_note ON note_updates(note_id, seq);
CREATE TABLE note_purges(
    note_id TEXT PRIMARY KEY, purged_at TEXT NOT NULL, purged_by TEXT NOT NULL,
    change_seq INTEGER NOT NULL);
CREATE INDEX note_purges_change ON note_purges(change_seq);
CREATE TABLE note_peers(
    device_id TEXT PRIMARY KEY, acked_seq INTEGER NOT NULL DEFAULT 0,
    peer_epoch TEXT, last_sync TEXT, last_error TEXT, protocol TEXT);
CREATE TABLE note_history(
    history_id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    devices TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    sha256 TEXT NOT NULL);
CREATE INDEX note_history_note ON note_history(note_id, created_at);
'''


def digest(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def _private_file(path):
    """Create the database user-only (0600 on POSIX) before SQLite opens it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == 'posix' and not path.exists():
        descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        os.close(descriptor)


class NotesStore:
    VERSION = 1

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.fts = False
        existed = path.exists()
        try:
            if existed:
                # Decide with a read-only probe: an unrecognised or newer database
                # must not be modified at all (not even switched to WAL).
                with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as probe:
                    version = probe.execute('PRAGMA user_version').fetchone()[0]
                    tables = probe.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                if version > self.VERSION:
                    raise NotesStorageError('notes_storage_newer')
                if version == 0 and tables:
                    raise NotesStorageError('notes_storage_unrecognized')
            else:
                _private_file(path)
            with self.transaction() as db:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version > self.VERSION:
                    raise NotesStorageError('notes_storage_newer')
                if version == 0:
                    tables = db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                    if tables:
                        # Not ours (or half-written by something else): never repair in place.
                        raise NotesStorageError('notes_storage_unrecognized')
                    self._migrate_v1(db)
                self.fts = self._ensure_search(db)
        except NotesStorageError:
            raise
        except sqlite3.DatabaseError:
            raise NotesStorageError('notes_storage_unavailable') from None

    def _migrate_v1(self, db):
        for statement in SCHEMA.strip().split(';'):
            if statement.strip():
                db.execute(statement)
        db.execute("INSERT INTO meta VALUES('store_seq','0')")
        db.execute("INSERT INTO meta VALUES('epoch',?)", (str(uuid.uuid4()),))
        db.execute('PRAGMA user_version=1')

    @staticmethod
    def _ensure_search(db):
        """FTS5 when this SQLite has it; otherwise bounded LIKE search (same results)."""
        try:
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS note_search USING fts5("
                       "note_id UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2')")
            return True
        except sqlite3.OperationalError:
            db.execute('CREATE TABLE IF NOT EXISTS note_search_plain(note_id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL)')
            return False

    @contextmanager
    def transaction(self, *, read_only=False):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA synchronous=FULL')
                db.execute('BEGIN' if read_only else 'BEGIN IMMEDIATE')
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def validate_database(path):
        """Backup validation: integrity and a recognised schema version."""
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise NotesStorageError('notes_integrity_failed')
            if db.execute('PRAGMA user_version').fetchone()[0] not in (1,):
                raise NotesStorageError('notes_storage_unrecognized')

    # --- feed ---------------------------------------------------------------
    @staticmethod
    def next_seq(db):
        value = int(db.execute("SELECT value FROM meta WHERE key='store_seq'").fetchone()[0]) + 1
        db.execute("UPDATE meta SET value=? WHERE key='store_seq'", (str(value),))
        return value

    @staticmethod
    def meta_value(db, key):
        row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def set_meta_value(db, key, value):
        db.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))

    # --- notes --------------------------------------------------------------
    @staticmethod
    def note(db, note_id):
        return db.execute('SELECT * FROM notes WHERE note_id=?', (note_id,)).fetchone()

    @staticmethod
    def purged(db, note_id):
        return db.execute('SELECT 1 FROM note_purges WHERE note_id=?', (note_id,)).fetchone() is not None

    @staticmethod
    def document_data(db, note_id):
        snapshot = db.execute('SELECT state,sha256 FROM note_snapshots WHERE note_id=?', (note_id,)).fetchone()
        updates = db.execute('SELECT payload,sha256 FROM note_updates WHERE note_id=? ORDER BY seq', (note_id,)).fetchall()
        return snapshot, updates

    @staticmethod
    def append_update(db, note_id, payload, *, origin, device_id, now, update_id=None):
        db.execute('INSERT OR IGNORE INTO note_updates(note_id,update_id,origin,device_id,payload,sha256,created_at) '
                   'VALUES(?,?,?,?,?,?,?)',
                   (note_id, update_id or str(uuid.uuid4()), origin, device_id, payload, digest(payload), now))

    def write_search(self, db, note_id, title, body):
        if self.fts:
            db.execute('DELETE FROM note_search WHERE note_id=?', (note_id,))
            db.execute('INSERT INTO note_search(note_id,title,body) VALUES(?,?,?)', (note_id, title, body))
        else:
            db.execute('INSERT INTO note_search_plain VALUES(?,?,?) ON CONFLICT(note_id) DO UPDATE SET '
                       'title=excluded.title, body=excluded.body', (note_id, title, body))

    def delete_search(self, db, note_id):
        db.execute('DELETE FROM note_search WHERE note_id=?' if self.fts else
                   'DELETE FROM note_search_plain WHERE note_id=?', (note_id,))
