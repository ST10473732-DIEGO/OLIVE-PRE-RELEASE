"""Profile-owned inert Inbox, exclusive export and bounded durable receipts.

Extends the DownloadQuarantine boundary for streaming: opaque paths, no parsing,
no launch/import, and an explicit exclusive local export.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil

from .contracts import ConnectError, canonical, identifier
from .file_protocol import CHUNK_SIZE, TERMINAL

INBOX_QUOTA = 256 * 1024 * 1024
OUTBOX_QUOTA = 128 * 1024 * 1024
LEDGER_LIMIT = 10_000
MAX_ACTIVE = 4


class FileIOFailure(OSError):
    """Bounded local diagnostic; never includes an OS message or a private path."""
    def __init__(self, category, error):
        super().__init__(category)
        self.category = category
        self.errno = getattr(error, 'errno', None)


def finalize_partial(partial, final, metadata):
    """Flush with write access, close, verify, then publish without replacement.

    Caller holds the transfer lock through the receipt commit. A hard link is an
    exclusive same-directory publication on both Windows and POSIX; unsupported
    filesystems fail closed. No owned handle survives into link/unlink.
    """
    category = 'open_failed'
    try:
        with partial.open('r+b') as stream:
            category = 'flush_failed'
            stream.flush()
            os.fsync(stream.fileno())
        category = 'hash_failed'
        digest, size = hashlib.sha256(), 0
        with partial.open('rb') as stream:
            while data := stream.read(CHUNK_SIZE):
                size += len(data)
                if size > metadata['size']:
                    raise ConnectError('content_integrity_failed')
                digest.update(data)
        if size != metadata['size'] or digest.hexdigest() != metadata['sha256']:
            raise ConnectError('content_integrity_failed')
        category = 'finalize_failed'
        os.link(partial, final)
    except OSError as error:
        raise FileIOFailure(category, error) from None


class FileStore:
    def __init__(self, service, profile):
        self.service = service
        self.directory = Path(profile) / 'quarantine' / 'connect-inbox'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with service.repository.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS file_transfers_v1 (transfer_id TEXT PRIMARY KEY, record TEXT NOT NULL)')
            for row in self.list(db):
                if row['state'] not in TERMINAL:
                    row.update(state='interrupted', error='application_restarted')
                    self.put(db, row)
                if row['state'] != 'completed' or row['direction'] != 'incoming':
                    self.path(row['transfer_id'], 'bin').unlink(missing_ok=True)
            # No partial survives restart, including a crash before ledger insertion.
            for suffix in ('part', 'out'):
                for path in self.directory.glob('*.' + suffix):
                    try:
                        identifier(path.stem)
                    except ConnectError:
                        continue
                    path.unlink(missing_ok=True)

    def path(self, transfer_id, suffix):
        identifier(transfer_id)
        if suffix not in {'part', 'out', 'bin'}:
            raise ConnectError('invalid_artifact')
        return self.directory / (transfer_id + '.' + suffix)

    def get(self, db, transfer_id):
        identifier(transfer_id)
        row = db.execute('SELECT record FROM file_transfers_v1 WHERE transfer_id=?', (transfer_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, db):
        return [json.loads(r[0]) for r in db.execute('SELECT record FROM file_transfers_v1 ORDER BY rowid DESC')]

    def put(self, db, row):
        row['updated_at'] = int(self.service.clock())
        db.execute('INSERT INTO file_transfers_v1 VALUES(?,?) ON CONFLICT(transfer_id) DO UPDATE SET record=excluded.record',
                   (row['transfer_id'], canonical(row).decode()))

    def reserve(self, db, peer, size, direction):
        rows = self.list(db)
        if len(rows) >= LEDGER_LIMIT:
            raise ConnectError('transfer_ledger_full')
        active = [r for r in rows if r['state'] not in TERMINAL]
        if len(active) >= MAX_ACTIVE or sum(r['peer_id'] == peer for r in active) >= 2:
            raise ConnectError('transfer_capacity_reached')
        used = sum(r['metadata']['size'] for r in rows if r['direction'] == direction
                   and (r['state'] not in TERMINAL or (direction == 'incoming' and r['state'] == 'completed')))
        quota = INBOX_QUOTA if direction == 'incoming' else OUTBOX_QUOTA
        if used + size > quota or shutil.disk_usage(self.directory).free < size + 16 * 1024 * 1024:
            raise ConnectError('inbox_quota_exhausted')

    def audit(self, db, row, event):
        self.service.repository.audit(db, row['peer_id'], row['transfer_id'],
            'files.receive' if row['direction'] == 'incoming' else 'files.send', int(self.service.clock()), event)

    def finish(self, db, row, state, error=None):
        if row['state'] in TERMINAL:
            return
        row.update(state=state, error=error)
        self.put(db, row)
        self.audit(db, row, {'completed': 'transfer_completed', 'declined': 'file_declined',
            'cancelled': 'transfer_cancelled'}.get(state, 'transfer_failed'))

    def export(self, row, destination):
        if row['direction'] != 'incoming' or row['state'] != 'completed':
            raise ConnectError('file_not_completed')
        # Stream and reverify the owned artifact before touching the local destination.
        with self.path(row['transfer_id'], 'bin').open('rb') as source:
            digest = hashlib.sha256()
            size = 0
            while data := source.read(CHUNK_SIZE):
                size += len(data)
                digest.update(data)
            if size != row['metadata']['size'] or digest.hexdigest() != row['metadata']['sha256']:
                raise ConnectError('artifact_changed')
            source.seek(0)
            # Same no-overwrite policy as DownloadQuarantine.export; no shell open.
            with Path(destination).open('xb') as target:
                try:
                    digest = hashlib.sha256()
                    size = 0
                    while data := source.read(CHUNK_SIZE):
                        target.write(data)
                        size += len(data)
                        digest.update(data)
                    if size != row['metadata']['size'] or digest.hexdigest() != row['metadata']['sha256']:
                        raise ConnectError('artifact_changed')
                    target.flush()
                    os.fsync(target.fileno())
                except BaseException:
                    target.close()
                    Path(destination).unlink(missing_ok=True)
                    raise
        return {'saved': True}
