"""Selected native Chat adapter; safe fields only, per-message identities.

The small materialization journal bridges SQLite and the atomic JSON repository.
Desktop calls run on its owning event loop, including native capture and flush,
so chat mutations cannot interleave with an incoming committed batch.
"""
import json
import hashlib
from datetime import datetime
from ..connect.contracts import ConnectError, canonical
from ..models import Chat, Message
from .records import record_id


def conversation(value):
    if type(value) is not dict or set(value) != {'title', 'project_id', 'created_at'}:
        raise ConnectError('invalid_chat_fields')
    if type(value['title']) is not str or len(value['title']) > 200:
        raise ConnectError('invalid_chat_title')
    if value['project_id'] is not None and (type(value['project_id']) is not str or len(value['project_id']) > 100):
        raise ConnectError('invalid_project_id')
    instant(value['created_at'])
    return value


def instant(value):
    if type(value) is not str or len(value) > 80:
        raise ConnectError('invalid_chat_time')
    datetime.fromisoformat(value)  # Existing native legacy times can be naive.


def message(value):
    if type(value) is not dict or set(value) != {'conversation_id', 'after', 'role', 'content', 'created_at'}:
        raise ConnectError('invalid_message_fields')
    record_id(value['conversation_id'])
    if value['after'] is not None:
        record_id(value['after'])
    if value['role'] not in ('user', 'assistant') or type(value['content']) is not str or len(value['content'].encode()) > 64000:
        raise ConnectError('invalid_message')
    instant(value['created_at'])
    return value


class ChatAdapter:
    def __init__(self, store, repository, *, live=None, busy=lambda: set(), publish=lambda: None):
        self.store, self.repository = store, repository
        self.live, self.busy, self.publish = live, busy, publish
        self.capture_pending = False
        with store.native.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sync_chat_selection_v1 (peer TEXT NOT NULL, conversation TEXT NOT NULL, selected INTEGER NOT NULL, PRIMARY KEY(peer,conversation))')
            db.execute('CREATE TABLE IF NOT EXISTS sync_chat_scan_v1 (conversation TEXT PRIMARY KEY, position INTEGER NOT NULL, fingerprint TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sync_chat_pending_v1 (id TEXT PRIMARY KEY, record TEXT NOT NULL)')
        self.flush()

    def chats(self):
        return self.live() if self.live else self.repository.load_all()

    def select(self, peer, conversation_id, selected):
        record_id(conversation_id)
        if type(selected) is not bool or conversation_id not in self.chats():
            raise ConnectError('unknown_conversation')
        with self.store.native.transaction() as db:
            if selected:
                db.execute('INSERT OR REPLACE INTO sync_chat_selection_v1 VALUES(?,?,1)', (peer, conversation_id))
                # Selection resets only this domain's outbound inventory cursor.
                db.execute("UPDATE sync_cursors_v1 SET sent=0 WHERE peer=? AND capability='sync.chat'", (peer,))
            else:
                db.execute('INSERT OR REPLACE INTO sync_chat_selection_v1 VALUES(?,?,0)', (peer, conversation_id))
        return self.selections(peer)

    def selections(self, peer):
        with self.store.native.transaction() as db:
            selected = {row[0] for row in db.execute('SELECT conversation FROM sync_chat_selection_v1 WHERE peer=? AND selected=1', (peer,))}
        return [dict(id=c.id, title=c.title, selected=c.id in selected) for c in self.chats().values()][:500]

    def allowed(self, db, peer, record):
        conversation_id = record.record_id if record.kind == 'conversation' else record.payload.get('conversation_id')
        if record.deleted and record.kind == 'message':
            # Tombstones carry no content; the local message relationship is retained.
            row = db.execute('SELECT conversation FROM sync_chat_message_links_v1 WHERE id=?', (record.record_id,)).fetchone()
            conversation_id = row[0] if row else None
        if not record.deleted and conversation_id not in self.chats():
            return False
        parent = self.store.current(db, conversation_id) if conversation_id else None
        if record.kind == 'message' and not record.deleted and parent and parent.deleted:
            return False
        return bool(db.execute('SELECT 1 FROM sync_chat_selection_v1 WHERE peer=? AND conversation=? AND selected=1', (peer, conversation_id)).fetchone())

    def capture(self, db):
        self.capture_pending = False
        chats = self.chats()
        selected = {row[0] for row in db.execute('SELECT DISTINCT conversation FROM sync_chat_selection_v1 WHERE selected=1')}
        busy = self.busy()
        budget = 256
        for identity in sorted(selected):
            if identity in busy:
                self.capture_pending = True
                continue
            chat = chats.get(identity)
            previous = self.store.current(db, identity)
            if chat is None:
                # Only the local deletion authors child tombstones. A received
                # parent tombstone must not manufacture new child revisions.
                if previous is None or previous.deleted:
                    continue
                scan = db.execute('SELECT fingerprint FROM sync_chat_scan_v1 WHERE conversation=?', (identity,)).fetchone()
                if scan and scan[0] == 'deleted':
                    continue
                from .records import SyncRecord
                for row in db.execute('SELECT c.record FROM sync_current_v1 c JOIN sync_chat_message_links_v1 l ON l.id=c.id WHERE l.conversation=?', (identity,)).fetchall():
                    value = json.loads(row[0])
                    if value['deleted']:
                        continue
                    if budget <= 0:
                        self.capture_pending = True
                        return
                    current = SyncRecord.parse(value)
                    self.store.put(db, self.store.local_record('message', current.record_id, {}, True, current), 0)
                    budget -= 1
                self.store.put(db, self.store.local_record('conversation', identity, {}, True, previous), 0)
                db.execute("INSERT OR REPLACE INTO sync_chat_scan_v1 VALUES(?,-1,'deleted')", (identity,))
                continue
            payload = dict(title=chat.title, project_id=chat.project_id, created_at=chat.created_at)
            self.capture_one(db, 'conversation', identity, payload)
            hasher = hashlib.sha256()
            for item in chat.messages:
                hasher.update(canonical([item.id, item.role, item.content, item.created_at, item.completion_state]))
            fingerprint = hasher.hexdigest()
            scan = db.execute('SELECT position,fingerprint FROM sync_chat_scan_v1 WHERE conversation=?', (identity,)).fetchone()
            if scan and scan[1] == fingerprint and scan[0] == -1:
                continue
            start = min(scan[0], len(chat.messages)) if scan and scan[1] == fingerprint else 0
            stop = min(len(chat.messages), start + budget)
            eligible = [m for m in chat.messages if m.role in ('user', 'assistant') and m.completion_state == 'complete']
            previous_messages = [m for m in chat.messages[:start] if m.role in ('user', 'assistant') and m.completion_state == 'complete']
            predecessor = previous_messages[-1].id if previous_messages else None
            existing = {m.id for m in eligible}
            db.execute('INSERT OR REPLACE INTO sync_chat_scan_v1 VALUES(?,?,?)', (identity, stop if stop < len(chat.messages) else -1, fingerprint))
            for item in chat.messages[start:stop]:
                if item.role not in ('user', 'assistant') or item.completion_state != 'complete':
                    continue
                current = self.store.current(db, item.id)
                # Predecessor belongs to the immutable append, not its current
                # sorted position after concurrent branches have merged.
                after = current.payload['after'] if current and not current.deleted else predecessor
                payload = dict(conversation_id=identity, after=after, role=item.role,
                               content=item.content, created_at=item.created_at)
                self.capture_one(db, 'message', item.id, payload)
                predecessor = item.id
                budget -= 1
            if stop < len(chat.messages):
                self.capture_pending = True
                return
            for row in db.execute('SELECT id FROM sync_chat_message_links_v1 WHERE conversation=?', (identity,)).fetchall():
                current = self.store.current(db, row[0])
                if row[0] not in existing and current and not current.deleted:
                    self.store.put(db, self.store.local_record('message', row[0], {}, True, current), 0)

    def capture_one(self, db, kind, identity, payload):
        current = self.store.current(db, identity)
        if current and current.deleted:
            return  # Deleted messages/conversations require explicit recreation design.
        changed = not current or current.payload != payload
        if changed:
            record = self.store.local_record(kind, identity, payload, False, current)
            self.store.put(db, record, 0)
        if kind == 'message':
            db.execute('INSERT OR IGNORE INTO sync_chat_message_links_v1 VALUES(?,?,?)', (identity, payload['conversation_id'], payload['after']))

        return changed

    def stage(self, db, peer, record):
        identity = record.record_id
        current = self.store.current(db, identity)
        conversation_id = identity if record.kind == 'conversation' else (
            record.payload.get('conversation_id') or (current.payload.get('conversation_id') if current else None))
        if conversation_id and conversation_id in self.chats():
            selection = db.execute('SELECT selected FROM sync_chat_selection_v1 WHERE peer=? AND conversation=?', (peer, conversation_id)).fetchone()
            if not selection or not selection[0]:
                raise LookupError('conversation_not_shared')
        if conversation_id in self.busy():
            raise LookupError('conversation_busy')
        if record.kind == 'conversation' and record.deleted:
            chat = self.chats().get(identity)
            if chat:
                if chat.draft or chat.notes or chat.documents:
                    raise LookupError('local_conversation_content')
                for item in chat.messages:
                    head = self.store.current(db, item.id)
                    if not head or not head.deleted:
                        raise LookupError('live_conversation_messages')
        if record.kind == 'conversation' and not record.deleted:
            project = record.payload['project_id']
            if project and project not in self.store.personal.projects():
                raise LookupError('missing_project')
        if record.kind == 'message' and not record.deleted:
            conversation_record = self.store.current(db, conversation_id)
            if not conversation_record or conversation_record.kind != 'conversation' or conversation_record.deleted:
                raise LookupError('missing_conversation')
            after = record.payload['after']
            if after:
                parent = self.store.current(db, after)
                link = db.execute('SELECT conversation FROM sync_chat_message_links_v1 WHERE id=?', (after,)).fetchone()
                if after == identity or not parent or parent.kind != 'message' or not link or link[0] != conversation_id:
                    raise LookupError('missing_predecessor')
            if current and not current.deleted and (current.payload['conversation_id'] != conversation_id or current.payload['after'] != after):
                raise ConnectError('message_order_is_immutable')
            db.execute('INSERT OR IGNORE INTO sync_chat_message_links_v1 VALUES(?,?,?)', (identity, conversation_id, after))
        if conversation_id:
            # Receipt grants continuity back to this source only, never onward
            # disclosure to another paired device. Their local permission still applies.
            db.execute('INSERT OR IGNORE INTO sync_chat_selection_v1 VALUES(?,?,1)', (peer, conversation_id))
        db.execute('INSERT OR REPLACE INTO sync_chat_pending_v1 VALUES(?,?)', (identity, canonical(record.value()).decode()))
        return 0

    def flush(self):
        with self.store.native.transaction() as db:
            pending = [json.loads(row[0]) for row in db.execute('SELECT record FROM sync_chat_pending_v1')]
            if not pending:
                return
            chats = self.chats()
            # Native file write is atomic; if interrupted, the journal is replayed
            # before local capture. Applying the same IDs is deterministic.
            for value in sorted(pending, key=lambda r: (r['kind'] != 'conversation', r['record_id'])):
                identity, payload = value['record_id'], value['payload']
                if value['kind'] == 'conversation':
                    if value['deleted']:
                        chats.pop(identity, None)
                    else:
                        chat = chats.setdefault(identity, Chat(id=identity))
                        chat.title, chat.project_id, chat.created_at = payload['title'], payload['project_id'], payload['created_at']
                        chat.touch()
                else:
                    link = db.execute('SELECT conversation FROM sync_chat_message_links_v1 WHERE id=?', (identity,)).fetchone()
                    chat = chats.get(link[0]) if link else None
                    if chat is None:
                        continue
                    chat.messages = [m for m in chat.messages if m.id != identity]
                    chat.summary = ''
                    chat.summary_message_count = 0
                    chat.touch()
                    if not value['deleted']:
                        chat.messages.append(Message(id=identity, role=payload['role'], content=payload['content'], created_at=payload['created_at']))
            for chat in chats.values():
                # Deterministic sibling ordering by stable ID; never timestamps.
                by_id = {m.id: m for m in chat.messages}
                nodes = {}
                for row in db.execute('SELECT id,predecessor FROM sync_chat_message_links_v1 WHERE conversation=?', (chat.id,)):
                    nodes[row[0]] = row[1]
                children = {}
                for identity, parent in nodes.items():
                    children.setdefault(parent, []).append(identity)
                ordered, visited = [], set()
                pending_ids = sorted(children.get(None, []), reverse=True)
                while pending_ids:
                    child = pending_ids.pop()
                    if child in visited:
                        raise ConnectError('cyclic_message_order')
                    visited.add(child)
                    if child in by_id:
                        ordered.append(by_id[child])
                    pending_ids.extend(sorted(children.get(child, []), reverse=True))
                # Keep unsynchronized/private/incomplete native messages intact.
                ordered.extend(m for m in chat.messages if m.id not in visited)
                chat.messages = ordered
            self.repository.save_all(chats.values())
            db.execute('DELETE FROM sync_chat_pending_v1')
        self.publish()
