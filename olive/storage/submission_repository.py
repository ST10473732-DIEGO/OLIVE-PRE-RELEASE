"""Durable no-replay records; contains identities/digests, never credentials."""
from contextlib import contextmanager
import sqlite3


class SubmissionRepository:
    def __init__(self, path):
        self.path = path
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS submissions (id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, message_id TEXT)')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, action_id):
        with self.connection() as db:
            return db.execute('SELECT digest,state,message_id FROM submissions WHERE id=?',(action_id,)).fetchone()

    def reserve(self, action_id, digest):
        with self.connection() as db:
            db.execute('INSERT INTO submissions VALUES (?,?,?,NULL)',(action_id,digest,'uncertain'))

    def accepted(self, action_id, message_id):
        with self.connection() as db:
            db.execute('UPDATE submissions SET state=?,message_id=? WHERE id=?',('accepted',message_id,action_id))

    def rejected(self, action_id):
        with self.connection() as db:
            db.execute('UPDATE submissions SET state=? WHERE id=?',('failed',action_id))
