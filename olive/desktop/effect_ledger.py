"""Durable, content-free reservations for non-repeatable GUI submissions."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time


class EffectLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS effects (task TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(task,digest))')

    @contextmanager
    def connect(self):
        if self.path.is_symlink():
            raise PermissionError('Effect ledger must not be a symlink')
        connection = sqlite3.connect(self.path, timeout=.25)
        try:
            connection.execute('PRAGMA synchronous=FULL')
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def digest(scope):
        return hashlib.sha256(json.dumps([scope.application, scope.effect, scope.content,
            scope.destination, scope.account, scope.server], ensure_ascii=True).encode()).hexdigest()

    def reserve(self, grant):
        # The commit finishes before input starts; failed storage means no effect.
        with self.connect() as connection:
            try:
                connection.execute('INSERT INTO effects VALUES (?,?,?,?)',
                    (grant.id, self.digest(grant.scope), 'outcome-unknown', time.time()))
            except sqlite3.IntegrityError as error:
                raise PermissionError('Submission already attempted; inspect outcome, never automatically repeat') from error

    def verified(self, grant):
        with self.connect() as connection:
            changed = connection.execute('UPDATE effects SET state=? WHERE task=? AND digest=?',
                ('verified', grant.id, self.digest(grant.scope))).rowcount
            if changed != 1:
                raise RuntimeError('Required effect receipt is missing')
