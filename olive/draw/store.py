"""Durable OLIVE Draw storage: one SQLite database, versioned migrations, WAL.

Store schema 2 holds a replicated record set per drawing, a materialized view
of it (drawings, visibility), this device's Undo/Redo stacks, imported image
assets (content-addressed), a durable change feed with per-peer cursors, and
permanent-deletion tombstones. Every change commits in ONE transaction.

Store schema 1 (an operation log plus a history head, single editor) is
migrated once, on open: a SQLite backup copy of the v1 file is written next to
it first and the v1 tables are kept (renamed ``legacy_v1_*``); nothing is
deleted. Nothing here deletes an unreadable or newer database; the service
reports "Drawing storage unavailable" instead.
"""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
import threading
import uuid


class DrawStorageError(RuntimeError):
    """Fixed, content-free storage failure categories."""


SCHEMA_V2 = '''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE drawings(
    drawing_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    title_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    background TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL DEFAULT 1,
    revision INTEGER NOT NULL DEFAULT 0,
    last_seq INTEGER NOT NULL DEFAULT 0,
    clock INTEGER NOT NULL DEFAULT 0,
    op_count INTEGER NOT NULL DEFAULT 0,
    record_count INTEGER NOT NULL DEFAULT 0,
    doc_bytes INTEGER NOT NULL DEFAULT 0,
    trashed INTEGER NOT NULL DEFAULT 0,
    trashed_at TEXT NOT NULL DEFAULT '',
    trashed_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok');
CREATE INDEX drawings_by_change ON drawings(trashed, last_seq);
CREATE TABLE draw_records(
    seq INTEGER PRIMARY KEY,
    record_id TEXT NOT NULL UNIQUE,
    drawing_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    device TEXT NOT NULL,
    lamport INTEGER NOT NULL,
    sort_key TEXT NOT NULL,
    target TEXT,
    body TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL);
CREATE INDEX draw_records_drawing ON draw_records(drawing_id, kind, sort_key);
CREATE INDEX draw_records_target ON draw_records(target);
CREATE TABLE draw_visibility(target TEXT PRIMARY KEY, hidden INTEGER NOT NULL, key TEXT NOT NULL);
CREATE TABLE draw_history(
    drawing_id TEXT NOT NULL, stack TEXT NOT NULL, pos INTEGER NOT NULL, record_id TEXT NOT NULL,
    PRIMARY KEY(drawing_id, stack, pos));
CREATE TABLE draw_purges(drawing_id TEXT PRIMARY KEY, purged_at TEXT NOT NULL, device TEXT NOT NULL,
    seq INTEGER NOT NULL UNIQUE);
CREATE TABLE draw_assets(
    asset_id TEXT PRIMARY KEY, mime TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
    size INTEGER NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL, origin TEXT NOT NULL);
CREATE TABLE draw_wanted(asset_id TEXT PRIMARY KEY, drawing_id TEXT NOT NULL, since TEXT NOT NULL);
CREATE TABLE draw_peers(
    device_id TEXT PRIMARY KEY, acked_seq INTEGER NOT NULL DEFAULT 0,
    peer_epoch TEXT, last_sync TEXT, last_error TEXT, protocol TEXT);
CREATE TABLE draw_thumbnails(
    drawing_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, mime TEXT NOT NULL,
    image BLOB NOT NULL, created_at TEXT NOT NULL)
'''


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def sort_key(lamport, device, record_id):
    """Text form of the record order: zero-padded so text order == tuple order."""
    return f'{lamport:016d}:{device}:{record_id}'


def migration_record_id(drawing_id, *parts):
    """Stable ids for migrated v1 content (the same v1 data always maps the same way)."""
    text = ':'.join(('olive-draw-v1-migration', drawing_id) + tuple(str(p) for p in parts))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]


def _private_file(path):
    """Create the database user-only (0600 on POSIX) before SQLite opens it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == 'posix' and not path.exists():
        descriptor = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        os.close(descriptor)


class DrawStore:
    VERSION = 2

    def __init__(self, path, *, device_id):
        self.path = path
        self.device_id = device_id
        self.lock = threading.RLock()
        self.migrated_from = None
        try:
            if path.exists():
                # Decide with a read-only probe: an unrecognised or newer database
                # must not be modified at all (not even switched to WAL).
                with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as probe:
                    version = probe.execute('PRAGMA user_version').fetchone()[0]
                    tables = probe.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                if version > self.VERSION:
                    raise DrawStorageError('draw_storage_newer')
                if version == 0 and tables:
                    raise DrawStorageError('draw_storage_unrecognized')
                if version == 1:
                    self._backup_before_migration()
            else:
                _private_file(path)
            with self.transaction() as db:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version > self.VERSION:
                    raise DrawStorageError('draw_storage_newer')
                if version == 0:
                    if db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]:
                        raise DrawStorageError('draw_storage_unrecognized')
                    self._create_v2(db)
                elif version == 1:
                    self._migrate_v1(db)
                    self.migrated_from = 1
        except DrawStorageError:
            raise
        except sqlite3.DatabaseError:
            raise DrawStorageError('draw_storage_unavailable') from None

    # --- schema -------------------------------------------------------------------
    @staticmethod
    def _create_v2(db):
        for statement in SCHEMA_V2.strip().split(';'):
            if statement.strip():
                db.execute(statement)
        for key, value in (('store_id', str(uuid.uuid4())), ('epoch', str(uuid.uuid4())), ('feed_seq', '0')):
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', (key, value))
        db.execute('PRAGMA user_version=2')

    def _backup_before_migration(self):
        """A consistent copy of the v1 database before its one-time migration."""
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        target = self.path.with_name(f'{self.path.name}.store-v1-{stamp}.bak')
        _private_file(target)
        with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(target)) as copy:
                source.backup(copy)
        self.migration_backup = target

    def _migrate_v1(self, db):
        """Store schema 1 -> 2. Each v1 drawing becomes a record set made by this
        device: its operations in their old order, the redo branch as hidden
        operations, and the same Undo/Redo stacks. v1 tables are kept."""
        from .records import migrate_v1_drawing   # records builds on this module
        for table in ('drawings', 'drawing_ops', 'drawing_thumbnails'):
            db.execute(f'ALTER TABLE {table} RENAME TO legacy_v1_{table}')
        db.execute('DROP INDEX IF EXISTS drawings_updated')
        self._create_v2(db)
        for row in db.execute('SELECT * FROM legacy_v1_drawings ORDER BY updated_at, drawing_id').fetchall():
            ops = [json.loads(r[0]) for r in db.execute(
                'SELECT op FROM legacy_v1_drawing_ops WHERE drawing_id=? ORDER BY idx', (row['drawing_id'],))]
            migrate_v1_drawing(db, self.device_id, row, ops)
        db.execute('INSERT INTO draw_thumbnails(drawing_id,revision,mime,image,created_at) '
                   'SELECT t.drawing_id, d.revision, t.mime, t.image, t.created_at FROM legacy_v1_drawing_thumbnails t '
                   'JOIN drawings d ON d.drawing_id=t.drawing_id')

    @contextmanager
    def transaction(self, *, read_only=False):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA synchronous=FULL')
                db.execute('PRAGMA journal_size_limit=8388608')   # Keep the WAL from staying huge after big saves.
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
                raise DrawStorageError('draw_integrity_failed')
            if db.execute('PRAGMA user_version').fetchone()[0] not in (1, 2):
                raise DrawStorageError('draw_storage_unrecognized')

    # --- feed ---------------------------------------------------------------------
    @staticmethod
    def next_seq(db):
        value = int(db.execute("SELECT value FROM meta WHERE key='feed_seq'").fetchone()[0]) + 1
        db.execute("UPDATE meta SET value=? WHERE key='feed_seq'", (str(value),))
        return value

    @staticmethod
    def meta_value(db, key):
        row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def drawing(db, drawing_id):
        return db.execute('SELECT * FROM drawings WHERE drawing_id=?', (drawing_id,)).fetchone()

    @staticmethod
    def purged(db, drawing_id):
        return db.execute('SELECT 1 FROM draw_purges WHERE drawing_id=?', (drawing_id,)).fetchone() is not None
