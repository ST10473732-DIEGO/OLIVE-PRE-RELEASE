"""The OLIVE Draw replica rules, applied inside a store transaction.

A drawing is the set of its records. Inserting a record is idempotent (its id
is unique) and commutative: whatever order records arrive in, the materialized
state (``drawings`` row, ``draw_visibility``) is a pure function of the set:

* content operations are drawn in ``(lamport, device, record_id)`` order;
* an operation is hidden iff the greatest visibility record (same order) that
  targets it, *made by the operation's own device*, says hidden;
* ``title`` and ``trashed`` take the value of their greatest meta record;
* a purged drawing drops every record and never comes back.

The same rules are implemented for the renderer (and a future phone) in
``desktop/src/features/draw/replica.ts``; ``conformance_v1.json`` checks both.
"""
import json
import uuid

from .document import (LIMITS, DrawingFormatError, clean_title, encode_record, operation_schema,
                       validate_operation)
from .store import DrawStore, migration_record_id, sort_key, utc_now

DEFAULT_TITLE = 'Untitled drawing'


def key_of(record):
    return sort_key(record['lamport'], record['device'], record['record_id'])


def insert(db, record, *, source='', now=None):
    """Validate, store and materialize one record. Returns 'applied', 'duplicate',
    'purged' or 'rejected:<code>'. Never partially applies."""
    did = record.get('drawing_id') if type(record) is dict else None
    if type(did) is str and DrawStore.purged(db, did):
        return 'purged'
    if type(record) is dict and type(record.get('record_id')) is str and db.execute(
            'SELECT 1 FROM draw_records WHERE record_id=?', (record['record_id'],)).fetchone():
        return 'duplicate'
    try:
        data = encode_record(record)
    except DrawingFormatError as failure:
        return f'rejected:{failure}'
    kind, body = record['kind'], record['body']
    drawing = DrawStore.drawing(db, did)
    if kind == 'create':
        if drawing is not None or db.execute(
                "SELECT 1 FROM draw_records WHERE drawing_id=? AND kind='create'", (did,)).fetchone():
            return 'rejected:invalid_record'
        if drawing is None and db.execute('SELECT COUNT(*) FROM drawings').fetchone()[0] >= LIMITS['max_drawings']:
            return 'rejected:drawings_capacity'
    elif drawing is not None:
        if drawing['record_count'] + 1 > LIMITS['max_records']:
            return 'rejected:drawing_too_large'
        if kind == 'op' and drawing['op_count'] + 1 > LIMITS['max_operations']:
            return 'rejected:too_many_operations'
        if kind == 'op' and drawing['doc_bytes'] + len(data) > LIMITS['max_document_bytes']:
            return 'rejected:drawing_too_large'
    now = now or utc_now()
    seq = DrawStore.next_seq(db)
    db.execute('INSERT INTO draw_records(seq,record_id,drawing_id,kind,device,lamport,sort_key,target,body,bytes,source,'
               'received_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
               (seq, record['record_id'], did, kind, record['device'], record['lamport'], key_of(record),
                body['target'] if kind == 'visibility' else None, data, len(data), source, now))
    if kind == 'create':
        db.execute('INSERT INTO drawings(drawing_id,title,created_at,updated_at,width,height,background,created_by) '
                   'VALUES(?,?,?,?,?,?,?,?)', (did, body['title'] or DEFAULT_TITLE, body['created_at'], now,
                                               body['width'], body['height'], body['background'], record['device']))
        rematerialize(db, did, now=now)
    elif drawing is not None:
        _fold(db, did, record, len(data), now)
    # Local, monotonic "most recently changed" order for the drawing list.
    db.execute('UPDATE drawings SET last_seq=? WHERE drawing_id=?', (seq, did))
    return 'applied'


def _fold(db, did, record, size, now):
    """Incremental materialization of one new record into an existing drawing."""
    kind, body, key = record['kind'], record['body'], key_of(record)
    sets = ['clock=MAX(clock,?)', 'record_count=record_count+1', 'revision=revision+1', 'updated_at=?']
    values = [record['lamport'], now]
    if kind == 'op':
        sets += ['op_count=op_count+1', 'doc_bytes=doc_bytes+?', 'schema_version=MAX(schema_version,?)']
        values += [size, operation_schema(body)]
        _resolve_visibility(db, record['record_id'], record['device'])
        if body['type'] == 'image':
            want(db, did, body['asset_id'], now)
    elif kind == 'visibility':
        target = db.execute('SELECT device FROM draw_records WHERE record_id=?', (body['target'],)).fetchone()
        if target is not None and target['device'] == record['device']:
            current = db.execute('SELECT key FROM draw_visibility WHERE target=?', (body['target'],)).fetchone()
            if current is None or key > current['key']:
                db.execute('INSERT INTO draw_visibility VALUES(?,?,?) ON CONFLICT(target) DO UPDATE SET '
                           'hidden=excluded.hidden, key=excluded.key', (body['target'], int(body['hidden']), key))
    elif kind == 'meta':
        row = DrawStore.drawing(db, did)
        if body['field'] == 'title' and key > row['title_key']:
            sets += ['title=?', 'title_key=?']
            values += [body['value'] or DEFAULT_TITLE, key]
        if body['field'] == 'trashed' and key > row['trashed_key']:
            sets += ['trashed=?', 'trashed_at=?', 'trashed_key=?']
            values += [int(body['value']), record['at'] if body['value'] else '', key]
    db.execute(f'UPDATE drawings SET {", ".join(sets)} WHERE drawing_id=?', values + [did])


def _resolve_visibility(db, target, device):
    """Visibility records that arrived before their operation are folded in now."""
    row = db.execute("SELECT body, sort_key FROM draw_records WHERE target=? AND kind='visibility' AND device=? "
                     'ORDER BY sort_key DESC LIMIT 1', (target, device)).fetchone()
    if row is not None:
        hidden = json.loads(row['body'])['body']['hidden']
        db.execute('INSERT INTO draw_visibility VALUES(?,?,?) ON CONFLICT(target) DO UPDATE SET '
                   'hidden=excluded.hidden, key=excluded.key', (target, int(hidden), row['sort_key']))


def rematerialize(db, did, *, now=None):
    """Recompute a drawing's derived state from its records (create arrived late,
    or a check). The result depends only on the record set."""
    rows = db.execute('SELECT record_id, kind, device, lamport, body, bytes, sort_key FROM draw_records '
                      'WHERE drawing_id=? ORDER BY sort_key', (did,)).fetchall()
    ops = {r['record_id']: r for r in rows if r['kind'] == 'op'}
    db.execute('DELETE FROM draw_visibility WHERE target IN (SELECT record_id FROM draw_records '
               "WHERE drawing_id=? AND kind='op')", (did,))
    title = title_key = trashed_key = trashed_at = None
    trashed, schema, clock, size = False, 1, 0, 0
    winners = {}
    for row in rows:
        record = json.loads(row['body'])
        clock = max(clock, row['lamport'])
        if row['kind'] == 'op':
            schema = max(schema, operation_schema(record['body']))
            size += row['bytes']
            if record['body']['type'] == 'image':
                want(db, did, record['body']['asset_id'], now or utc_now())
        elif row['kind'] == 'visibility':
            target = ops.get(record['body']['target'])
            if target is not None and target['device'] == row['device']:
                winners[target['record_id']] = (row['sort_key'], record['body']['hidden'])
        elif row['kind'] == 'meta':
            if record['body']['field'] == 'title':
                title, title_key = record['body']['value'], row['sort_key']
            else:
                trashed, trashed_key = record['body']['value'], row['sort_key']
                trashed_at = record['at'] if trashed else ''
    for target, (key, hidden) in winners.items():
        db.execute('INSERT INTO draw_visibility VALUES(?,?,?)', (target, int(hidden), key))
    sets = ['clock=?', 'op_count=?', 'record_count=?', 'doc_bytes=?', 'schema_version=?', 'revision=revision+1']
    values = [clock, len(ops), len(rows), size, schema]
    if title_key is not None:
        sets += ['title=?', 'title_key=?']
        values += [title or DEFAULT_TITLE, title_key]
    if trashed_key is not None:
        sets += ['trashed=?', 'trashed_at=?', 'trashed_key=?']
        values += [int(trashed), trashed_at, trashed_key]
    if now:
        sets.append('updated_at=?')
        values.append(now)
    db.execute(f'UPDATE drawings SET {", ".join(sets)} WHERE drawing_id=?', values + [did])


def want(db, did, asset_id, now):
    if not db.execute('SELECT 1 FROM draw_assets WHERE asset_id=?', (asset_id,)).fetchone():
        db.execute('INSERT OR IGNORE INTO draw_wanted VALUES(?,?,?)', (asset_id, did, now))


def make(db, device, did, kind, body, *, record_id=None, lamport=None, at=None):
    """A new local record with the next Lamport clock value for this drawing."""
    drawing = DrawStore.drawing(db, did)
    rid = record_id or uuid.uuid4().hex
    if kind == 'op':
        body = dict(body, id=rid)
    return {'record_id': rid, 'drawing_id': did, 'device': device,
            'lamport': lamport or ((drawing['clock'] if drawing is not None else 0) + 1),
            'kind': kind, 'at': at or utc_now(), 'body': body}


# --- this device's Undo / Redo stacks (local, never synced) ------------------------
def push(db, did, stack, record_id):
    top = db.execute('SELECT MAX(pos) FROM draw_history WHERE drawing_id=? AND stack=?', (did, stack)).fetchone()[0]
    db.execute('INSERT INTO draw_history VALUES(?,?,?,?)', (did, stack, (top or 0) + 1, record_id))
    count = db.execute('SELECT COUNT(*) FROM draw_history WHERE drawing_id=? AND stack=?', (did, stack)).fetchone()[0]
    if count > LIMITS['max_undo']:
        db.execute('DELETE FROM draw_history WHERE drawing_id=? AND stack=? AND pos IN (SELECT pos FROM draw_history '
                   'WHERE drawing_id=? AND stack=? ORDER BY pos LIMIT ?)', (did, stack, did, stack, count - LIMITS['max_undo']))


def pop(db, did, stack):
    row = db.execute('SELECT pos, record_id FROM draw_history WHERE drawing_id=? AND stack=? ORDER BY pos DESC LIMIT 1',
                     (did, stack)).fetchone()
    if row is None:
        return None
    db.execute('DELETE FROM draw_history WHERE drawing_id=? AND stack=? AND pos=?', (did, stack, row['pos']))
    return row['record_id']


def clear_stack(db, did, stack):
    db.execute('DELETE FROM draw_history WHERE drawing_id=? AND stack=?', (did, stack))


def history(db, did):
    counts = dict(db.execute('SELECT stack, COUNT(*) FROM draw_history WHERE drawing_id=? GROUP BY stack', (did,)).fetchall())
    return {'undo': counts.get('undo', 0), 'redo': counts.get('redo', 0)}


def hidden(db, record_id):
    row = db.execute('SELECT hidden FROM draw_visibility WHERE target=?', (record_id,)).fetchone()
    return bool(row and row['hidden'])


# --- store schema 1 -> 2 -------------------------------------------------------------
def migrate_v1_drawing(db, device, row, ops):
    """One v1 drawing (ops + head) as records made by this device (see store)."""
    did = row['drawing_id']
    at = row['updated_at']
    try:
        title = clean_title(row['title']) or DEFAULT_TITLE
    except DrawingFormatError:
        title = DEFAULT_TITLE
    create = {'record_id': migration_record_id(did, 'create'), 'drawing_id': did, 'device': device, 'lamport': 1,
              'kind': 'create', 'at': row['created_at'],
              'body': {'width': row['width'], 'height': row['height'], 'background': row['background'],
                       'title': title, 'created_at': row['created_at']}}
    if insert(db, create, now=at) != 'applied':
        return
    lamport, ids, corrupt = 1, [], False
    for index, op in enumerate(ops):
        rid = migration_record_id(did, 'op', index, op.get('id', '') if type(op) is dict else '')
        try:
            body = validate_operation(dict(op, id=rid))
        except (DrawingFormatError, TypeError):
            corrupt = True
            break
        lamport += 1
        if insert(db, {'record_id': rid, 'drawing_id': did, 'device': device, 'lamport': lamport, 'kind': 'op',
                       'at': at, 'body': body}, now=at) == 'applied':
            ids.append(rid)
    head = min(row['head'], len(ids))
    for index, rid in enumerate(ids[head:]):
        lamport += 1
        insert(db, {'record_id': migration_record_id(did, 'hide', index), 'drawing_id': did, 'device': device,
                    'lamport': lamport, 'kind': 'visibility', 'at': at, 'body': {'target': rid, 'hidden': True}}, now=at)
    if row['trashed']:
        lamport += 1
        insert(db, {'record_id': migration_record_id(did, 'trash'), 'drawing_id': did, 'device': device,
                    'lamport': lamport, 'kind': 'meta', 'at': row['trashed_at'] or at,
                    'body': {'field': 'trashed', 'value': True}}, now=at)
    for rid in ids[:head]:
        push(db, did, 'undo', rid)
    for rid in reversed(ids[head:]):
        push(db, did, 'redo', rid)
    db.execute('UPDATE drawings SET updated_at=?, status=? WHERE drawing_id=?', (at, 'corrupt' if corrupt else 'ok', did))
