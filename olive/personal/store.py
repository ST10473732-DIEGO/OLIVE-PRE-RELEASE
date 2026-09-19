"""Additive SQLite repository with revisions, tombstones and durable deliveries."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import json
import sqlite3
import threading
import uuid
from contextvars import ContextVar

WRITE_GUARD=ContextVar('personal_write_guard',default=None)
WRITE_SOURCE=ContextVar('personal_write_source',default={'origin':'local_service'})

KINDS = {'profile', 'contact', 'calendar', 'event', 'task', 'reminder'}


class RevisionConflict(ValueError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class PersonalStore:
    VERSION = 4

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        with self.transaction() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1,2,3,self.VERSION):
                raise ValueError('Unsupported Personal Core schema; original database retained')
            if version == 0:
                db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE records (
                        id TEXT PRIMARY KEY, kind TEXT NOT NULL, uid TEXT NOT NULL,
                        revision INTEGER NOT NULL, created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
                        body TEXT NOT NULL, search_text TEXT NOT NULL, UNIQUE(kind, uid));
                    CREATE INDEX records_kind ON records(kind, deleted, updated_at);
                    CREATE TABLE links (
                        source TEXT NOT NULL REFERENCES records(id),
                        target TEXT NOT NULL REFERENCES records(id),
                        relation TEXT NOT NULL, PRIMARY KEY(source,target,relation));
                    CREATE TABLE deliveries (
                        id TEXT PRIMARY KEY, reminder_id TEXT NOT NULL REFERENCES records(id),
                        occurrence TEXT NOT NULL, due_at TEXT NOT NULL, state TEXT NOT NULL,
                        delivered_at TEXT, updated_at TEXT NOT NULL,
                        UNIQUE(reminder_id, occurrence));
                    CREATE INDEX delivery_due ON deliveries(state, due_at);
                    PRAGMA user_version=1;
                ''')
            if version<2:
                db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                db.execute('PRAGMA user_version=2')
            if version<3:
                db.execute("ALTER TABLE records ADD COLUMN provenance TEXT NOT NULL DEFAULT '{}'")
                db.execute('PRAGMA user_version=3')
            if version<4:
                # Early M3 initial profiles stored the calendar ID in their body
                # but omitted its derived relationship. Repair only that known
                # additive edge, after validating its actual target.
                for row in db.execute("SELECT id,body FROM records WHERE kind='profile' AND deleted=0"):
                    target=json.loads(row['body']).get('default_calendar')
                    if target:
                        self.get(db,'calendar',target)
                        db.execute("INSERT OR IGNORE INTO links VALUES(?,?,'default_calendar')",(row['id'],target))
                db.execute('PRAGMA user_version=4')

    @contextmanager
    def transaction(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('BEGIN IMMEDIATE')
                guard=WRITE_GUARD.get()
                if guard:guard()
                yield db
                if guard:guard()
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def unpack(row):
        if row is None:
            raise LookupError('Personal record not found')
        return dict(json.loads(row['body']), id=row['id'], kind=row['kind'], uid=row['uid'],
                    revision=row['revision'], created_at=row['created_at'], updated_at=row['updated_at'],provenance=json.loads(row['provenance']))

    def get(self, db, kind, record_id):
        if kind not in KINDS:
            raise ValueError('Unknown personal domain')
        return self.unpack(db.execute('SELECT * FROM records WHERE kind=? AND id=? AND deleted=0',
                                     (kind, record_id)).fetchone())

    def list(self, db, kind, *, limit=200, offset=0):
        if kind not in KINDS or type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
            raise ValueError('Invalid bounded personal query')
        return [self.unpack(r) for r in db.execute(
            'SELECT * FROM records WHERE kind=? AND deleted=0 ORDER BY updated_at DESC,id LIMIT ? OFFSET ?',
            (kind, limit, offset))]

    def save(self, db, kind, body, *, record_id=None, revision=None, uid=None, source=None):
        if kind not in KINDS:
            raise ValueError('Unknown personal domain')
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False)
        search_text = encoded.casefold()
        if len(encoded.encode()) > 64000:
            raise ValueError('Personal record exceeds size limit')
        now = timestamp()
        origin={**(source or WRITE_SOURCE.get()),'at':now}
        if record_id:
            previous = self.get(db, kind, record_id)
            if type(revision) is not int or revision != previous['revision']:
                raise RevisionConflict('This record changed. Reload or compare before saving.')
            provenance={**previous['provenance'],'updated':origin}
            db.execute('UPDATE records SET body=?,search_text=?,revision=revision+1,updated_at=? WHERE id=?',
                       (encoded, search_text, now, record_id))
        else:
            provenance={'created':origin,'updated':origin}
            record_id = uuid.uuid4().hex
            db.execute('INSERT INTO records(id,kind,uid,revision,created_at,updated_at,body,search_text) VALUES(?,?,?,1,?,?,?,?)',
                       (record_id, kind, uid or uuid.uuid4().hex, now, now, encoded, search_text))
        db.execute('UPDATE records SET provenance=? WHERE id=?',(json.dumps(provenance),record_id))
        return self.get(db, kind, record_id)

    def delete(self, db, kind, record_id, revision):
        record = self.get(db, kind, record_id)
        if type(revision) is not int or record['revision'] != revision:
            raise RevisionConflict('This record changed. Review deletion again.')
        db.execute('UPDATE records SET deleted=1,revision=revision+1,updated_at=? WHERE id=?', (timestamp(),record_id))
        db.execute('DELETE FROM links WHERE source=? OR target=?', (record_id,record_id))
        return {'id':record_id, 'revision':revision+1, 'status':'deleted'}

    @staticmethod
    def body(record):
        return {k:v for k,v in record.items() if k not in {'id','kind','uid','revision','created_at','updated_at','recovery_warning','occurrence_id','provenance'}}

    @staticmethod
    def validate_database(path):
        with closing(sqlite3.connect(path)) as db:
            db.row_factory=sqlite3.Row
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or version not in (1,2,3,4):
                raise ValueError('Invalid Personal Core backup database')
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Invalid Personal Core backup relationships')
            expected_links=set()
            for row in db.execute('SELECT * FROM records'):
                kind=row['kind'];body=json.loads(row['body'])
                if kind not in KINDS or not isinstance(body,dict) or row['revision']<1 or row['deleted'] not in (0,1):
                    raise ValueError('Invalid Personal Core backup record')
                from . import validation as v
                from .calendar import event
                from .reminders import validate_reminder
                validators={'contact':v.contact,'calendar':v.calendar,'event':event,'task':v.task,'reminder':validate_reminder}
                if kind in validators:validators[kind](body)
                if 'provenance' in row.keys():
                    provenance=json.loads(row['provenance'])
                    if not isinstance(provenance,dict) or set(provenance)-{'created','updated'}:
                        raise ValueError('Invalid Personal Core provenance')
                    for entry in provenance.values():
                        if not isinstance(entry,dict) or any(not isinstance(k,str) or not isinstance(value,str) for k,value in entry.items()):
                            raise ValueError('Invalid Personal Core provenance')
                if row['deleted']:continue
                links=[]
                if kind=='event':links.append(('calendar',body['calendar_id'],'calendar'))
                if kind=='profile' and body.get('default_calendar'):links.append(('calendar',body['default_calendar'],'default_calendar'))
                if kind in {'event','task'}:links.extend(('contact',identity,'contact') for identity in body.get('contact_ids',[]))
                if kind=='task' and body.get('event_id'):links.append(('event',body['event_id'],'calendar_block'))
                if kind=='reminder':links.append((body['target_kind'],body['target_id'],'reminder_target'))
                for target_kind,target_id,relation in links:
                    target=db.execute('SELECT kind,deleted FROM records WHERE id=?',(target_id,)).fetchone()
                    if not target or target['kind']!=target_kind or target['deleted']:
                        raise ValueError('Invalid Personal Core backup relationship target')
                    expected_links.add((row['id'],target_id,relation))
            actual_links={tuple(row) for row in db.execute('SELECT source,target,relation FROM links')}
            if version<4:expected_links={edge for edge in expected_links if edge[2]!='default_calendar' or edge in actual_links}
            if expected_links!=actual_links:
                raise ValueError('Personal Core backup links do not match record relationships')
            for row in db.execute('SELECT d.*,r.kind FROM deliveries d JOIN records r ON r.id=d.reminder_id'):
                if row['kind']!='reminder' or row['state'] not in {'pending','delivered','snoozed','dismissed','cancelled','restored'}:
                    raise ValueError('Invalid Personal Core reminder recovery state')
                for key in ('due_at','updated_at','delivered_at'):
                    if row[key] and datetime.fromisoformat(row[key]).tzinfo is None:
                        raise ValueError('Invalid Personal Core reminder timestamp')
