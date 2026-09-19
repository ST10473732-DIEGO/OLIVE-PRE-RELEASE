"""Transactional Mail records and immutable binary content in one backup unit.

Mail has its own additive schema. Personal Core schema 4 and its IDs are untouched.
No reusable credentials are stored here. Submission recovery never opens a socket.
"""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from contextvars import ContextVar

WRITE_GUARD=ContextVar('mail_write_guard',default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class MailStore:
    VERSION = 1
    KINDS = {'connection', 'folder', 'message', 'draft', 'submission', 'sync', 'annotation'}

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.transaction() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, self.VERSION):
                raise ValueError('Unsupported Mail schema; original data retained')
            if version == 0:
                db.execute('CREATE TABLE records(id TEXT PRIMARY KEY, kind TEXT NOT NULL, revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, body TEXT NOT NULL)')
                db.execute('CREATE INDEX mail_kind ON records(kind,updated_at,id)')
                db.execute('CREATE TABLE blobs(hash TEXT PRIMARY KEY, bytes BLOB NOT NULL)')
                db.execute('CREATE TABLE sources(source TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id))')
                db.execute('PRAGMA user_version=1')

    @contextmanager
    def transaction(self):
        with self.lock, closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.create_function('casefold',1,lambda value:str(value or '').casefold(),deterministic=True)
            from email.utils import parseaddr
            db.create_function('mail_sender',1,lambda value:parseaddr(str(value or ''))[1].casefold(),deterministic=True)
            from .folders import role
            db.create_function('mail_folder_role',2,role,deterministic=True)
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('BEGIN IMMEDIATE')
            try:
                guard=WRITE_GUARD.get()
                if guard:guard()
                yield db
                if guard:guard()
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def unpack(row):
        if row is None:
            raise LookupError('Mail record no longer exists')
        return dict(json.loads(row['body']), id=row['id'], kind=row['kind'],
                    revision=row['revision'], created_at=row['created_at'], updated_at=row['updated_at'])

    def get(self, db, kind, identity):
        if kind not in self.KINDS:
            raise ValueError('Unknown Mail record kind')
        return self.unpack(db.execute('SELECT * FROM records WHERE id=? AND kind=?', (identity, kind)).fetchone())

    @staticmethod
    def body(record):
        return {k: v for k, v in record.items() if k not in {'id','kind','revision','created_at','updated_at','remote_operation'}}

    def save(self, db, kind, body, identity=None, revision=None):
        if kind not in self.KINDS:
            raise ValueError('Unknown Mail record kind')
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 500_000:
            raise ValueError('Mail record exceeds its content limit')
        instant = now()
        if identity:
            old = self.get(db, kind, identity)
            if type(revision) is not int or old['revision'] != revision:
                raise Conflict('This Mail record changed. Reload or compare before saving.')
            db.execute('UPDATE records SET body=?,revision=revision+1,updated_at=? WHERE id=?', (encoded, instant, identity))
        else:
            identity = uuid.uuid4().hex
            db.execute('INSERT INTO records VALUES(?,?,1,?,?,?)', (identity, kind, instant, instant, encoded))
        return self.get(db, kind, identity)

    def list(self, db, kind, limit=100, offset=0):
        if kind not in self.KINDS or type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
            raise ValueError('Invalid bounded Mail query')
        return [self.unpack(r) for r in db.execute('SELECT * FROM records WHERE kind=? ORDER BY updated_at DESC,id LIMIT ? OFFSET ?', (kind,limit,offset))]

    def blob(self, db, data):
        if not isinstance(data, bytes) or len(data) > 20_000_000:
            raise ValueError('Mail content exceeds 20 MB')
        key = hashlib.sha256(data).hexdigest()
        db.execute('INSERT OR IGNORE INTO blobs VALUES(?,?)', (key,data))
        return key

    def read_blob(self, db, key):
        row = db.execute('SELECT bytes FROM blobs WHERE hash=?', (key,)).fetchone()
        if row is None or hashlib.sha256(row[0]).hexdigest() != key:
            raise ValueError('Mail content is missing or damaged')
        return bytes(row[0])

    def recover(self, *, restored=False):
        with self.transaction() as db:
            for row in db.execute("SELECT * FROM records WHERE kind IN ('submission','connection','annotation')").fetchall():
                record = self.unpack(row)
                body = self.body(record)
                if record['kind']=='annotation' and body.get('type')=='remote_operation' and body.get('state')=='pending':
                    body.update(state='outcome_uncertain',category='Interrupted')
                    self.save(db,'annotation',body,record['id'],record['revision'])
                if record['kind']=='submission' and body.get('sent_copy_state')=='copying':
                    body['sent_copy_state']='outcome_uncertain'
                    record=self.save(db,'submission',body,record['id'],record['revision'])
                if record['kind'] == 'submission' and body['state'] in {'submitting','awaiting_approval','prepared'}:
                    body['state'] = 'outcome_uncertain' if body['state'] == 'submitting' else 'cancelled'
                    body['reason'] = 'Interrupted; never retried automatically. Review before creating a new submission.'
                    self.save(db,'submission',body,record['id'],record['revision'])
                    if record['state']=='submitting':
                        draft=self.get(db,'draft',record['draft_id'])
                        draft_body=self.body(draft);draft_body.update(submission_state='outcome_uncertain',folder='Outbox')
                        self.save(db,'draft',draft_body,draft['id'],draft['revision'])
                elif restored and record['kind'] == 'connection':
                    body.update(enabled=False, credential_ref=None, state='review_required')
                    self.save(db,'connection',body,record['id'],record['revision'])

    @classmethod
    def validate_database(cls, path):
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
            objects=db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if any(kind not in {'table','index'} for kind,name in objects) or {name for kind,name in objects if kind=='table'}!={'records','blobs','sources'}:
                raise ValueError('Mail backup contains an unexpected database object')
            if db.execute('PRAGMA user_version').fetchone()[0] != cls.VERSION or db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Mail backup schema or integrity is invalid')
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Mail backup contains broken source references')
            hashes=set()
            for key,data in db.execute('SELECT hash,bytes FROM blobs'):
                if not isinstance(data,bytes) or len(data)>20_000_000 or hashlib.sha256(data).hexdigest()!=key:raise ValueError('Mail backup contains damaged content')
                hashes.add(key)
            ids={row[0]:row[1] for row in db.execute('SELECT id,kind FROM records')}
            for identity,kind,revision,encoded in db.execute('SELECT id,kind,revision,body FROM records'):
                body=json.loads(encoded)
                if kind not in cls.KINDS or not isinstance(body,dict) or revision<1 or len(encoded.encode())>500000:
                    raise ValueError('Mail backup contains an invalid record')
                if body.get('raw_hash') and body['raw_hash'] not in hashes:raise ValueError('Mail backup has a missing source snapshot')
                for attachment in body.get('attachments',[]):
                    if not isinstance(attachment,dict) or attachment.get('hash') not in hashes:raise ValueError('Mail backup has a missing attachment')
                if kind=='connection':
                    from .connections import validate_config
                    if set(body)&{'password','secret','token'}:raise ValueError('Mail backup must not contain reusable credentials')
                    validate_config({k:body[k] for k in {'name','sender','username','smtp','imap','sync_enabled','sent_folder','sent_copy','ca_pem'} if k in body})
                if kind=='submission' and (ids.get(body.get('draft_id'))!='draft' or ids.get(body.get('connection_id'))!='connection'):
                    raise ValueError('Mail backup has broken submission relationships')
