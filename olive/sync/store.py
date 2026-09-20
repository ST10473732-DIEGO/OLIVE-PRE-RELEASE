"""Transactional C5 ledger beside native PersonalStore records.

Only current portable payloads and unresolved competing versions are retained.
Fingerprint receipts and tombstones are never evicted to make room.
"""
import json
import uuid

from ..connect.contracts import ConnectError, canonical
from ..personal.store import timestamp
from .records import SyncRecord, DOMAINS, MAX_BATCH, MAX_BYTES, dominates

MAX_RECEIPTS = 100_000
MAX_CONFLICTS = 128
MAX_CURRENT_RECORDS = 10_000
MAX_CURRENT_BYTES = 64 * 1024 * 1024


class SyncStore:
    def __init__(self, personal, device_id, signer):
        self.personal = personal
        self.native = personal.store
        self.device_id = device_id
        self.signer = signer
        self.chat = None
        with self.native.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sync_current_v1 (id TEXT PRIMARY KEY, kind TEXT NOT NULL, native_revision INTEGER NOT NULL, sequence INTEGER NOT NULL, record TEXT NOT NULL, size INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sync_excluded_v1 (id TEXT PRIMARY KEY, revision INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sync_sessions_v1 (peer TEXT PRIMARY KEY, status TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sync_counter_v1 (id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO sync_counter_v1 VALUES(1,0)')
            db.execute('CREATE TABLE IF NOT EXISTS sync_receipts_v1 (revision TEXT PRIMARY KEY, fingerprint TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sync_conflicts_v1 (id TEXT PRIMARY KEY, peer TEXT NOT NULL, record_id TEXT NOT NULL, local_revision TEXT, local_record TEXT, incoming TEXT NOT NULL, reason TEXT NOT NULL, UNIQUE(record_id, incoming))')
            db.execute('CREATE TABLE IF NOT EXISTS sync_cursors_v1 (peer TEXT NOT NULL, capability TEXT NOT NULL, sent INTEGER NOT NULL, received INTEGER NOT NULL, PRIMARY KEY(peer,capability))')
            db.execute('CREATE TABLE IF NOT EXISTS sync_chat_message_links_v1 (id TEXT PRIMARY KEY, conversation TEXT NOT NULL, predecessor TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS sync_reminder_cutoff_v1 (id TEXT PRIMARY KEY, cutoff TEXT NOT NULL)')

    def attach_chat(self, repository, **kwargs):
        from .chat import ChatAdapter
        self.chat = ChatAdapter(self, repository, **kwargs)
        return self.chat

    def flush(self):
        if self.chat:
            self.chat.flush()

    def current(self, db, identity):
        row = db.execute('SELECT record FROM sync_current_v1 WHERE id=?', (identity,)).fetchone()
        return SyncRecord.parse(json.loads(row[0])) if row else None

    def receipt(self, db, record):
        fingerprint = record.fingerprint()
        row = db.execute('SELECT fingerprint FROM sync_receipts_v1 WHERE revision=?', (record.revision,)).fetchone()
        if row:
            if row[0] != fingerprint:
                raise ConnectError('changed_revision')
            return True
        if db.execute('SELECT COUNT(*) FROM sync_receipts_v1').fetchone()[0] >= MAX_RECEIPTS:
            raise ConnectError('sync_ledger_capacity')
        db.execute('INSERT INTO sync_receipts_v1 VALUES(?,?)', (record.revision, fingerprint))
        return False

    def put(self, db, record, native_revision):
        encoded = canonical(record.value())
        previous = db.execute('SELECT size FROM sync_current_v1 WHERE id=?', (record.record_id,)).fetchone()
        count, size = db.execute('SELECT COUNT(*),COALESCE(SUM(size),0) FROM sync_current_v1').fetchone()
        if (count + int(previous is None) > MAX_CURRENT_RECORDS or
                size - (previous[0] if previous else 0) + len(encoded) > MAX_CURRENT_BYTES):
            raise ConnectError('sync_ledger_capacity')
        self.receipt(db, record)
        db.execute('UPDATE sync_counter_v1 SET value=value+1 WHERE id=1')
        seq = db.execute('SELECT value FROM sync_counter_v1 WHERE id=1').fetchone()[0]
        db.execute('INSERT OR REPLACE INTO sync_current_v1 VALUES(?,?,?,?,?,?)',
                   (record.record_id, record.kind, native_revision, seq, encoded.decode(), len(encoded)))
        for row in db.execute('SELECT id,incoming FROM sync_conflicts_v1 WHERE record_id=?', (record.record_id,)).fetchall():
            incoming = SyncRecord.parse(json.loads(row['incoming']))
            if record.ancestry != incoming.ancestry and dominates(record.ancestry, incoming.ancestry):
                db.execute('DELETE FROM sync_conflicts_v1 WHERE id=?', (row['id'],))

    def local_record(self, kind, identity, payload, deleted, current=None, other=None):
        ancestry = dict(current.ancestry) if current else {}
        if other:
            for device, count in other.ancestry.items():
                ancestry[device] = max(ancestry.get(device, 0), count)
        ancestry[self.device_id] = ancestry.get(self.device_id, 0) + 1
        return SyncRecord.parse(self.signer(dict(kind=kind, record_id=identity, schema_version=1,
            revision=str(uuid.uuid4()), ancestry=ancestry,
            origin_device_id=current.origin_device_id if current else self.device_id,
            editor_device_id=self.device_id, updated_at=timestamp(), deleted=deleted,
            payload={} if deleted else payload)))

    def capture(self, db):
        if self.chat:
            self.chat.capture(db)
        # Read only changed native revisions; bounded work per exchange. The native
        # repository remains authoritative, including edits made while disconnected.
        rows = db.execute("SELECT r.* FROM records r LEFT JOIN sync_current_v1 s ON s.id=r.id LEFT JOIN sync_excluded_v1 e ON e.id=r.id WHERE (e.id IS NULL OR e.revision!=r.revision) AND r.kind IN ('task','calendar','event','reminder') AND (s.id IS NULL OR s.native_revision!=r.revision) ORDER BY r.updated_at,r.id LIMIT 256").fetchall()
        self.capture_rows(db, rows)

    def capture_targets(self, db, records):
        if self.chat:
            self.chat.capture_targets(db, records)
        identities = [r.record_id for r in records if r.kind not in ('conversation', 'message')]
        if identities:
            placeholders = ','.join('?' for _ in identities)
            rows = db.execute(f'SELECT r.* FROM records r LEFT JOIN sync_current_v1 s ON s.id=r.id WHERE r.id IN ({placeholders}) AND (s.id IS NULL OR s.native_revision!=r.revision)', identities).fetchall()
            self.capture_rows(db, rows)

    def capture_rows(self, db, rows):
        for row in rows:
            current = self.current(db, row['id'])
            payload = {} if row['deleted'] else json.loads(row['body'])
            if payload.get('agent_task_id'):
                db.execute('INSERT OR REPLACE INTO sync_excluded_v1 VALUES(?,?)', (row['id'], row['revision']))
                continue
            db.execute('DELETE FROM sync_excluded_v1 WHERE id=?', (row['id'],))
            if current and current.deleted and not row['deleted']:
                raise ConnectError('tombstone_recreation_not_supported')
            if current and current.deleted == bool(row['deleted']) and current.payload == payload:
                db.execute('UPDATE sync_current_v1 SET native_revision=? WHERE id=?', (row['revision'], row['id']))
                continue
            record = self.local_record(row['kind'], row['id'], payload, bool(row['deleted']), current)
            self.put(db, record, row['revision'])

    def batch(self, db, capability, cursor, peer=None):
        kinds = [kind for kind, domain in DOMAINS.items() if 'sync.' + domain == capability]
        placeholders = ','.join('?' for _ in kinds)
        rows = db.execute(f'SELECT sequence,record FROM sync_current_v1 WHERE sequence>? AND kind IN ({placeholders}) ORDER BY sequence LIMIT 512', (cursor, *kinds)).fetchall()
        records, end, size = [], cursor, 0
        examined = 0
        for row in rows:
            if len(records) >= MAX_BATCH:
                break
            value = json.loads(row['record'])
            if db.execute('SELECT 1 FROM sync_excluded_v1 WHERE id=?', (value['record_id'],)).fetchone():
                end = row['sequence']
                examined += 1
                continue
            if capability == 'sync.chat' and (not self.chat or not self.chat.allowed(db, peer, SyncRecord.parse(value))):
                end = row['sequence']
                examined += 1
                continue
            size += len(row['record'].encode())
            if size > MAX_BYTES - 4096:
                break
            records.append(value)
            examined += 1
            end = row['sequence']
        return records, end, (len(rows) > examined or len(rows) == 512 or
                              bool(capability == 'sync.chat' and self.chat and self.chat.capture_pending))

    def conflict(self, db, peer, current, incoming, reason):
        raw = canonical(incoming.value()).decode()
        if db.execute('SELECT 1 FROM sync_conflicts_v1 WHERE record_id=? AND incoming=?', (incoming.record_id, raw)).fetchone():
            return
        if db.execute('SELECT COUNT(*) FROM sync_conflicts_v1').fetchone()[0] >= MAX_CONFLICTS:
            raise ConnectError('sync_conflict_capacity')
        db.execute('INSERT INTO sync_conflicts_v1 VALUES(?,?,?,?,?,?,?)',
                   (str(uuid.uuid4()), peer, incoming.record_id, current.revision if current else None, canonical(current.value()).decode() if current else None, raw, reason))

    def apply_native(self, db, record, peer=None):
        if record.kind in ('conversation', 'message'):
            if not self.chat:
                raise ConnectError('chat_sync_unavailable')
            return self.chat.stage(db, peer or self.device_id, record)
        row = db.execute('SELECT * FROM records WHERE id=?', (record.record_id,)).fetchone()
        if row and row['kind'] == 'task' and json.loads(row['body']).get('agent_task_id'):
            raise LookupError('unsyncable_relationship')
        if row and row['kind'] != record.kind:
            raise ConnectError('record_kind_collision')
        if record.deleted:
            # Relationships require a local review/cascade; never leave dangling
            # links by accepting a remote delete ahead of its dependent changes.
            if db.execute('SELECT 1 FROM links WHERE target=?', (record.record_id,)).fetchone():
                raise LookupError('dependent_records')
            if row:
                db.execute('UPDATE records SET deleted=1,revision=revision+1,updated_at=? WHERE id=?', (timestamp(), record.record_id))
                db.execute('DELETE FROM links WHERE source=?', (record.record_id,))
                db.execute("UPDATE deliveries SET state='cancelled',updated_at=? WHERE reminder_id=? AND state IN ('pending','snoozed')", (timestamp(), record.record_id))
                return row['revision'] + 1
            return 0
        if row and row['deleted']:
            raise ConnectError('tombstone_recreation_not_supported')
        links = self.personal._relationships(db, record.kind, record.payload)
        encoded = json.dumps(record.payload, ensure_ascii=False)
        if len(encoded.encode()) > 64000:
            raise ConnectError('record_too_large')
        now = timestamp()
        revision = row['revision'] + 1 if row else 1
        source = {'origin': 'connect_sync', 'device_id': record.editor_device_id, 'at': now}
        provenance = json.loads(row['provenance']) if row else {'created': source}
        provenance['updated'] = source
        if row:
            db.execute('UPDATE records SET body=?,search_text=?,revision=?,updated_at=?,provenance=? WHERE id=?',
                       (encoded, encoded.casefold(), revision, now, json.dumps(provenance), record.record_id))
        else:
            db.execute('INSERT INTO records(id,kind,uid,revision,created_at,updated_at,body,search_text,provenance) VALUES(?,?,?,?,?,?,?,?,?)',
                       (record.record_id, record.kind, record.record_id, revision, now, now, encoded, encoded.casefold(), json.dumps(provenance)))
        db.execute('DELETE FROM links WHERE source=?', (record.record_id,))
        db.executemany('INSERT INTO links VALUES(?,?,?)', [(record.record_id, target, relation) for _, target, relation in links])
        if record.kind == 'reminder':
            db.execute('INSERT OR REPLACE INTO sync_reminder_cutoff_v1 VALUES(?,?)', (record.record_id, now))
        if record.kind in ('task', 'event'):
            db.execute("INSERT OR REPLACE INTO sync_reminder_cutoff_v1 SELECT source,? FROM links WHERE target=? AND relation='reminder_target'", (now, record.record_id))
        if record.kind == 'task' and record.payload['status'] == 'completed':
            db.execute("UPDATE deliveries SET state='cancelled',updated_at=? WHERE reminder_id IN (SELECT source FROM links WHERE target=? AND relation='reminder_target') AND state IN ('pending','snoozed')", (now, record.record_id))
        return revision

    def receive(self, db, peer, values):
        records = [SyncRecord.parse(value) for value in values]
        # A bounded background inventory must never hide a dirty target from
        # the exact batch about to be applied. Capture these IDs transactionally.
        self.capture_targets(db, records)
        # Check every integrity receipt before changing native records. All writes
        # share the native transaction, including receipts and conflict staging.
        for record in records:
            self.receipt(db, record)
        results = []
        for incoming in records:
            current = self.current(db, incoming.record_id)
            if current and current.kind != incoming.kind:
                raise ConnectError('record_kind_collision')
            if current and current.revision == incoming.revision:
                results.append('duplicate')
                continue
            if current and dominates(current.ancestry, incoming.ancestry) and current.ancestry != incoming.ancestry:
                results.append('stale')
                continue
            reason = None
            if current and current.deleted and not incoming.deleted:
                self.conflict(db, peer, current, incoming, 'deleted_record_update')
                results.append('conflict')
                continue
            if current and not (dominates(incoming.ancestry, current.ancestry) and incoming.ancestry != current.ancestry):
                reason = 'concurrent_edit'
            if reason is None:
                try:
                    revision = self.apply_native(db, incoming, peer)
                except (LookupError, ValueError) as error:
                    if isinstance(error, ConnectError):
                        raise
                    safe_reasons = {'conversation_busy', 'conversation_not_shared', 'local_incomplete_message',
                                    'local_conversation_content', 'live_conversation_messages', 'dependent_records'}
                    reason = str(error) if str(error) in safe_reasons else 'missing_dependency'
                else:
                    self.put(db, incoming, revision)
                    results.append('applied')
                    continue
            self.conflict(db, peer, current, incoming, reason)
            results.append('conflict')
        return results

    def save_status(self, db, status):
        db.execute('INSERT OR REPLACE INTO sync_sessions_v1 VALUES(?,?)',
                   (status['peer'], canonical(status).decode()))

    def stored_status(self, peer):
        with self.native.transaction() as db:
            row = db.execute('SELECT status FROM sync_sessions_v1 WHERE peer=?', (peer,)).fetchone()
        return json.loads(row[0]) if row else None

    def conflict_count(self, peer):
        with self.native.transaction() as db:
            return db.execute('SELECT COUNT(*) FROM sync_conflicts_v1 WHERE peer=?', (peer,)).fetchone()[0]

    def cursors(self, db, peer, capability):
        row = db.execute('SELECT sent,received FROM sync_cursors_v1 WHERE peer=? AND capability=?', (peer, capability)).fetchone()
        return tuple(row) if row else (0, 0)

    def checkpoint(self, db, peer, capability, sent, received):
        db.execute('INSERT OR REPLACE INTO sync_cursors_v1 VALUES(?,?,?,?)', (peer, capability, sent, received))

    def conflicts(self):
        with self.native.transaction() as db:
            return [dict(id=row['id'], peer=row['peer'], record_id=row['record_id'],
                         reason=row['reason'], local=self.current(db, row['record_id']).value() if self.current(db, row['record_id']) else None,
                         incoming=json.loads(row['incoming'])) for row in db.execute('SELECT * FROM sync_conflicts_v1 ORDER BY id LIMIT 128')]

    def resolve(self, conflict_id, choice):
        if choice not in ('local', 'incoming'):
            raise ConnectError('invalid_conflict_resolution')
        with self.native.transaction() as db:
            self.capture(db)
            row = db.execute('SELECT * FROM sync_conflicts_v1 WHERE id=?', (conflict_id,)).fetchone()
            if row is None:
                raise ConnectError('unknown_conflict')
            incoming = SyncRecord.parse(json.loads(row['incoming']))
            self.capture_targets(db, [incoming])
            current = self.current(db, row['record_id'])
            # A reviewed version cannot silently resolve over a subsequent edit.
            if (current.revision if current else None) != row['local_revision']:
                db.execute('UPDATE sync_conflicts_v1 SET local_revision=? WHERE id=?', (current.revision if current else None, conflict_id))
                return {'state': 'review_again'}
            chosen = current if choice == 'local' else incoming
            if chosen is None:
                raise ConnectError('missing_local_version')
            if ((current and current.deleted) or incoming.deleted) and not chosen.deleted:
                raise ConnectError('tombstone_recreation_not_supported')
            resolved = self.local_record(chosen.kind, chosen.record_id, chosen.payload, chosen.deleted, current or incoming, incoming)
            revision = self.apply_native(db, resolved, row['peer'])
            self.put(db, resolved, revision)
            db.execute('DELETE FROM sync_conflicts_v1 WHERE id=?', (conflict_id,))
            return {'state': 'resolved', 'revision': resolved.revision}
