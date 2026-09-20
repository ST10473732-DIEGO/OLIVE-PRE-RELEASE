"""Versioned profile-local storage. No secret material, sockets or live DB sync."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import uuid

from .contracts import (CAPABILITIES, SAFE_OPERATIONS, CapabilityMetadata, ConnectError,
                        TrustState, display_name, timestamp)
from .models import validate_record


class DeviceRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise ConnectError('unsupported_repository_schema')
            db.execute('CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, local INTEGER NOT NULL, record TEXT NOT NULL)')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_local ON devices(local) WHERE local=1')
            db.execute('CREATE TABLE IF NOT EXISTS requests (source TEXT, request_id TEXT, fingerprint TEXT NOT NULL, response TEXT, PRIMARY KEY(source,request_id))')
            db.execute('CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, source_device_id TEXT, request_id TEXT, capability TEXT, timestamp INTEGER NOT NULL, result_state TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS connect_keys (device_id TEXT PRIMARY KEY, public TEXT NOT NULL, state TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS pairing_ledger (session_id TEXT PRIMARY KEY, state TEXT NOT NULL, peer_id TEXT, completion_hash TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS pairing_completion_v1 (session_id TEXT PRIMARY KEY, record TEXT NOT NULL)')
            db.execute('PRAGMA user_version=2')

    @contextmanager
    def transaction(self, *, timeout=10, read_only=False):
        # Separate connections support multiple repository instances and threads.
        db = sqlite3.connect(self.path, timeout=timeout)
        try:
            if read_only:
                # Snapshot lookups must not contend for the single writer slot.
                # Enforce this mode so it cannot accidentally perform a write.
                db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN' if read_only else 'BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, device_id):
        row = db.execute('SELECT record FROM devices WHERE device_id=?', (device_id,)).fetchone()
        return validate_record(json.loads(row[0])) if row else None

    @staticmethod
    def put(db, record, *, local=False):
        validate_record(record)
        db.execute('INSERT INTO devices VALUES(?,?,?) ON CONFLICT(device_id) DO UPDATE SET record=excluded.record',
                   (record['device_id'], int(local), json.dumps(record)))

    def ensure_local(self, platform, os_name, now):
        if platform not in {'windows', 'linux', 'macos', 'unknown'}:
            raise ConnectError('invalid_platform')
        with self.transaction() as db:
            row = db.execute('SELECT record FROM devices WHERE local=1').fetchone()
            if row:
                return validate_record(json.loads(row[0]))
            record = dict(device_id=str(uuid.uuid4()), display_name='This device',
                          platform=platform, device_class='desktop', created_at=timestamp(now),
                          public_identity_metadata={'os': display_name(os_name)},
                          capabilities=[asdict(CapabilityMetadata(c, c in SAFE_OPERATIONS))
                                        for c in sorted(CAPABILITIES)], revision=1)
            self.put(db, record, local=True)
            return record

    def add_fixture(self, name, now, *, capabilities=()):
        """Synthetic enrollment only; service gates this behind explicit fixture mode."""
        metadata = [asdict(c) for c in capabilities]
        with self.transaction() as db:
            record = dict(device_id=str(uuid.uuid4()), display_name=display_name(name),
                          platform='unknown', device_class='unknown',
                          trust_state=TrustState.PAIRED.value, paired_at=timestamp(now),
                          last_seen=None, connection_state='offline', connection_kind='fixture',
                          capabilities=metadata, permissions=[], revision=1, revoked_at=None)
            self.put(db, record)
            return record

    @staticmethod
    def devices_from_db(db):
        return [validate_record(json.loads(row[0])) for row in db.execute(
            'SELECT record FROM devices WHERE local=0 ORDER BY device_id')]

    def devices(self, *, timeout=10):
        with self.transaction(timeout=timeout, read_only=True) as db:
            return [validate_record(json.loads(row[0])) for row in db.execute('SELECT record FROM devices WHERE local=0 ORDER BY device_id')]

    @staticmethod
    def audit(db, source, request, capability, now, state):
        db.execute('INSERT INTO activity(source_device_id,request_id,capability,timestamp,result_state) VALUES(?,?,?,?,?)',
                   (source, request, capability, now, state))
        # Bounded activity history; replay ledger intentionally is not evicted.
        db.execute('DELETE FROM activity WHERE id <= (SELECT COALESCE(MAX(id),0)-1000 FROM activity)')

    def activity(self):
        with self.transaction() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM activity ORDER BY id')]
