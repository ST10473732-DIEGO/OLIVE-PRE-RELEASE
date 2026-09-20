"""Durable metadata receipts. No prompts, responses, model tags or private paths."""
from .contracts import ConnectError


class InferenceStore:
    def __init__(self, repository):
        self.repository = repository
        with repository.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS remote_inference_v1 (
                peer TEXT NOT NULL, job TEXT NOT NULL, fingerprint TEXT NOT NULL,
                preset TEXT NOT NULL, input_bytes INTEGER NOT NULL, output_bytes INTEGER NOT NULL,
                state TEXT NOT NULL, error TEXT, created INTEGER NOT NULL, duration_ms INTEGER NOT NULL,
                PRIMARY KEY(peer,job))''')
            db.execute("UPDATE remote_inference_v1 SET state='connection_lost',error='request_indeterminate' WHERE state IN ('awaiting_approval','queued','starting','streaming')")

    def get(self, db, peer, job):
        row = db.execute('SELECT fingerprint,state,error FROM remote_inference_v1 WHERE peer=? AND job=?', (peer, job)).fetchone()
        return dict(fingerprint=row[0], state=row[1], error=row[2]) if row else None

    def claim(self, db, req, size, now):
        if db.execute('SELECT count(*) FROM remote_inference_v1').fetchone()[0] >= 10_000:
            raise ConnectError('ledger_full')
        db.execute('INSERT INTO remote_inference_v1 VALUES(?,?,?,?,?,0,?,NULL,?,0)',
            (req.source_device_id, req.job_id, req.fingerprint(), req.arguments['preset'], size, 'awaiting_approval', now))

    def finish(self, db, job, state, error, duration):
        db.execute('UPDATE remote_inference_v1 SET state=?,error=?,output_bytes=?,duration_ms=? WHERE peer=? AND job=?',
            (state, error, job.output_bytes, int(duration * 1000), job.peer, job.request.job_id))

    def recent(self, peer):
        with self.repository.transaction(read_only=True) as db:
            return [dict(job_id=r[0], preset=r[1], input_bytes=r[2], output_bytes=r[3], state=r[4], error=r[5], duration_ms=r[6])
                for r in db.execute('SELECT job,preset,input_bytes,output_bytes,state,error,duration_ms FROM remote_inference_v1 WHERE peer=? ORDER BY created DESC,rowid DESC LIMIT 20', (peer,))]
