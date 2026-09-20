"""Additive C8 tables: local share bindings and metadata-only durable receipts."""
import json
import uuid
from .contracts import ConnectError


class StudioStore:
    def __init__(self, repository):
        self.repository = repository
        with repository.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS studio_shares_v1 (
                peer TEXT, reference TEXT, workspace TEXT, root_hash TEXT, revision INTEGER,
                PRIMARY KEY(peer,reference), UNIQUE(peer,workspace))''')
            db.execute('''CREATE TABLE IF NOT EXISTS studio_requests_v1 (
                peer TEXT, request TEXT, fingerprint TEXT, workspace TEXT, operation TEXT,
                result TEXT, PRIMARY KEY(peer,request))''')
            db.execute('''CREATE TABLE IF NOT EXISTS studio_activity_v1 (
                id INTEGER PRIMARY KEY, peer TEXT, workspace TEXT, operation TEXT,
                result TEXT, timestamp INTEGER)''')

            for peer, identity, value in db.execute("SELECT peer,request,result FROM studio_requests_v1 WHERE operation IN ('build','test','run')").fetchall():
                result = json.loads(value) if value else {}
                if result.get('state') in {'starting', 'running'}:
                    db.execute('UPDATE studio_requests_v1 SET result=? WHERE peer=? AND request=?',
                        (json.dumps({'state': 'connection_lost', 'job_id': identity, 'error': 'request_indeterminate'}), peer, identity))

    def shares(self, db, peer):
        return [dict(workspace_id=r[0], local_id=r[1], root_hash=r[2], share_revision=r[3])
                for r in db.execute('SELECT reference,workspace,root_hash,revision FROM studio_shares_v1 WHERE peer=?', (peer,))]

    def share(self, db, peer, workspace, root_hash):
        existing = next((s for s in self.shares(db, peer) if s['local_id'] == workspace), None)
        if existing:
            return existing
        if len(self.shares(db, peer)) >= 8:
            raise ConnectError('busy')
        ref = str(uuid.uuid4())
        db.execute('INSERT INTO studio_shares_v1 VALUES(?,?,?,?,1)', (peer, ref, workspace, root_hash))
        return next(s for s in self.shares(db, peer) if s['workspace_id'] == ref)

    def get(self, db, req):
        row = db.execute('SELECT fingerprint,result FROM studio_requests_v1 WHERE peer=? AND request=?',
                         (req.source_device_id, req.request_id)).fetchone()
        if not row:
            return None
        if row[0] != req.fingerprint():
            raise ConnectError('changed_duplicate')
        return json.loads(row[1]) if row[1] else {'state': 'request_indeterminate'}

    def claim(self, db, req):
        if db.execute('SELECT count(*) FROM studio_requests_v1').fetchone()[0] >= 10000:
            raise ConnectError('ledger_full')
        db.execute('INSERT INTO studio_requests_v1 VALUES(?,?,?,?,?,NULL)',
                   (req.source_device_id, req.request_id, req.fingerprint(), req.workspace_id, req.operation))

    def finish(self, db, req, result):
        # Only save revision or job identity/state; never code or process output.
        db.execute('UPDATE studio_requests_v1 SET result=? WHERE peer=? AND request=?',
                   (json.dumps(result), req.source_device_id, req.request_id))

    def audit(self, db, req, result, now):
        db.execute('INSERT INTO studio_activity_v1(peer,workspace,operation,result,timestamp) VALUES(?,?,?,?,?)',
                   (req.source_device_id, req.workspace_id, req.operation, result, now))
        db.execute('DELETE FROM studio_activity_v1 WHERE id NOT IN (SELECT id FROM studio_activity_v1 ORDER BY id DESC LIMIT 1000)')
        event = 'remote_studio_' + ('denied' if result in ('permission_denied', 'confirmation_required') else
            {'save': 'edit', 'tree': 'view', 'read': 'view', 'workspaces': 'view', 'run_cancel': 'cancel'}.get(req.operation, req.operation))
        self.repository.audit(db, req.source_device_id, req.request_id, req.capability, now, event)
