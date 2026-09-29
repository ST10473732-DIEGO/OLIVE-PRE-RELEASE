"""olive-notes/1 wire format: strict JSON, explicit schemas, bounded sizes.

Nothing from the network is deserialized into objects or executed. Byte fields
are base64 strings decoded with explicit limits before any CRDT library sees
them. Unknown versions, operations or fields fail closed.
"""
import base64
import json
import re
import uuid

from .limits import LIMITS, PROTOCOL, SPEC
from . import statevector

OPERATIONS = SPEC['operations']
STATUSES = frozenset(SPEC['statuses'])
ERRORS = frozenset(SPEC['errors'])
REQUEST_FIELDS = {'protocol_version', 'request_id', 'source_device_id', 'target_device_id', 'operation',
                  'arguments', 'timestamp', 'expires_at'}
SHA256 = re.compile(r'^[0-9a-f]{64}$')


class NotesProtocolError(ValueError):
    """Fixed error codes only."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NotesProtocolError('malformed_message')
        result[key] = value
    return result


def _loads(raw):
    if type(raw) is not bytes:
        raise NotesProtocolError('malformed_message')
    if len(raw) > LIMITS['max_frame_bytes']:
        raise NotesProtocolError('payload_too_large')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except NotesProtocolError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise NotesProtocolError('malformed_message') from None


def dumps(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(raw) > LIMITS['max_frame_bytes']:
        raise NotesProtocolError('payload_too_large')
    return raw


def uuid_text(value):
    if type(value) is not str or len(value) != 36:
        raise NotesProtocolError('malformed_message')
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise NotesProtocolError('malformed_message') from None
    return value


def integer(value, low=0, high=2 ** 53):
    if type(value) is not int or not low <= value <= high:
        raise NotesProtocolError('malformed_message')
    return value


def data(value, limit, *, allow_empty=False):
    if type(value) is not str or len(value) > (limit * 4) // 3 + 4:
        raise NotesProtocolError('payload_too_large' if type(value) is str else 'malformed_message')
    try:
        decoded = base64.b64decode(value, validate=True)
    except Exception:
        raise NotesProtocolError('malformed_message') from None
    if len(decoded) > limit:
        raise NotesProtocolError('payload_too_large')
    if not decoded and not allow_empty:
        raise NotesProtocolError('malformed_message')
    return decoded


def state_vector(value):
    decoded = data(value, LIMITS['max_state_vector_bytes'])
    try:
        statevector.decode(decoded)
    except statevector.StateVectorError:
        raise NotesProtocolError('malformed_message') from None
    return decoded


def b64(raw):
    return base64.b64encode(raw).decode('ascii')


def _fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise NotesProtocolError('malformed_message')


def validate_arguments(operation, arguments):
    """Returns arguments with byte fields decoded."""
    spec = OPERATIONS.get(operation)
    if spec is None:
        raise NotesProtocolError('malformed_message')
    _fields(arguments, spec['required'], spec['optional'])
    if operation == 'hello':
        versions = arguments['versions']
        if type(versions) is not list or not 1 <= len(versions) <= 4 or any(type(v) is not str or len(v) > 32 for v in versions):
            raise NotesProtocolError('malformed_message')
        return {'versions': list(versions)}
    uuid_text(arguments['epoch'])
    if operation == 'sync':
        entries = arguments['entries']
        if type(entries) is not list or len(entries) > LIMITS['max_entries']:
            raise NotesProtocolError('payload_too_large' if type(entries) is list else 'malformed_message')
        seen, total, decoded = set(), 0, []
        for entry in entries:
            _fields(entry, SPEC['entry']['required'], SPEC['entry']['optional'])
            nid = uuid_text(entry['note_id'])
            if nid in seen or type(entry['purged']) is not bool:
                raise NotesProtocolError('malformed_message')
            seen.add(nid)
            item = {'note_id': nid, 'seq': integer(entry['seq']), 'sv': state_vector(entry['sv']), 'purged': entry['purged']}
            if 'update' in entry:
                if entry['purged']:
                    raise NotesProtocolError('malformed_message')
                item['update'] = data(entry['update'], LIMITS['max_inline_update_bytes'])
                total += len(item['update'])
            decoded.append(item)
        if total > LIMITS['max_request_update_bytes']:
            raise NotesProtocolError('payload_too_large')
        return {'epoch': arguments['epoch'], 'entries': decoded}
    # chunk
    count_limit = -(-LIMITS['max_transfer_bytes'] // LIMITS['max_chunk_bytes'])
    result = {'epoch': arguments['epoch'], 'transfer_id': uuid_text(arguments['transfer_id']),
              'note_id': uuid_text(arguments['note_id']), 'seq': integer(arguments['seq']),
              'sv': state_vector(arguments['sv']), 'index': integer(arguments['index'], 0, count_limit - 1),
              'count': integer(arguments['count'], 1, count_limit),
              'total_bytes': integer(arguments['total_bytes'], 1, LIMITS['max_transfer_bytes']),
              'data': data(arguments['data'], LIMITS['max_chunk_bytes'])}
    if type(arguments['sha256']) is not str or not SHA256.fullmatch(arguments['sha256']) or result['index'] >= result['count']:
        raise NotesProtocolError('malformed_message')
    result['sha256'] = arguments['sha256']
    return result


def encode_request(request_id, source, target, operation, arguments, now):
    value = {'protocol_version': PROTOCOL, 'request_id': request_id, 'source_device_id': source,
             'target_device_id': target, 'operation': operation, 'arguments': arguments,
             'timestamp': now, 'expires_at': now + LIMITS['max_request_lifetime_seconds']}
    return dumps(value)


def decode_request(raw):
    value = _loads(raw)
    if type(value) is not dict or set(value) != REQUEST_FIELDS:
        raise NotesProtocolError('malformed_message')
    if value['protocol_version'] != PROTOCOL:
        raise NotesProtocolError('unsupported_protocol')
    for key in ('request_id', 'source_device_id', 'target_device_id'):
        uuid_text(value[key])
    if type(value['operation']) is not str or value['operation'] not in OPERATIONS:
        raise NotesProtocolError('malformed_message')
    integer(value['timestamp'], 0, 253402300799)
    integer(value['expires_at'], 0, 253402300799)
    if not 0 < value['expires_at'] - value['timestamp'] <= LIMITS['max_request_lifetime_seconds']:
        raise NotesProtocolError('malformed_message')
    value['arguments'] = validate_arguments(value['operation'], value['arguments'])
    return value


def check_fresh(request, now):
    if request['timestamp'] > now + LIMITS['future_tolerance_seconds'] or request['expires_at'] <= now:
        raise NotesProtocolError('expired_request')


def encode_response(request_id, *, result=None, error=None):
    if error is not None:
        if error not in ERRORS:
            error = 'malformed_message'
        return dumps({'protocol_version': PROTOCOL, 'request_id': request_id, 'state': 'rejected', 'error': error})
    return dumps({'protocol_version': PROTOCOL, 'request_id': request_id, 'state': 'completed', 'result': result})


def decode_response(raw):
    value = _loads(raw)
    if type(value) is not dict or value.get('protocol_version') != PROTOCOL or value.get('state') not in ('completed', 'rejected'):
        raise NotesProtocolError('malformed_message')
    expected = {'protocol_version', 'request_id', 'state', 'result' if value['state'] == 'completed' else 'error'}
    if set(value) != expected:
        raise NotesProtocolError('malformed_message')
    if value['request_id'] is not None:
        uuid_text(value['request_id'])
    if value['state'] == 'rejected' and (type(value['error']) is not str or len(value['error']) > 64):
        raise NotesProtocolError('malformed_message')
    return value


def validate_result(operation, result, entries=None):
    """Sender-side validation of a peer's completed result."""
    if operation == 'hello':
        _fields(result, ('versions', 'epoch'))
        if type(result['versions']) is not list or not 1 <= len(result['versions']) <= 4 or any(type(v) is not str for v in result['versions']):
            raise NotesProtocolError('malformed_message')
        uuid_text(result['epoch'])
        return result
    if operation == 'sync':
        _fields(result, ('epoch', 'results'))
        uuid_text(result['epoch'])
        rows = result['results']
        if type(rows) is not list or len(rows) != len(entries):
            raise NotesProtocolError('malformed_message')
        decoded = []
        for row, entry in zip(rows, entries):
            _fields(row, ('note_id', 'status', 'sv'), ('error',))
            if row['note_id'] != entry['note_id'] or row['status'] not in STATUSES or row['status'] == 'partial':
                raise NotesProtocolError('malformed_message')
            if 'error' in row and (type(row['error']) is not str or row['error'] not in ERRORS):
                raise NotesProtocolError('malformed_message')
            sv = state_vector(row['sv']) if row['status'] in ('applied', 'current', 'needs') else None
            decoded.append({'note_id': row['note_id'], 'status': row['status'], 'sv': sv, 'error': row.get('error')})
        return {'epoch': result['epoch'], 'results': decoded}
    if operation == 'chunk':
        _fields(result, ('epoch', 'status', 'sv'), ('error',))
        uuid_text(result['epoch'])
        if result['status'] not in STATUSES:
            raise NotesProtocolError('malformed_message')
        sv = state_vector(result['sv']) if result['status'] in ('applied', 'current', 'needs') else None
        return {'epoch': result['epoch'], 'status': result['status'], 'sv': sv, 'error': result.get('error')}
    raise NotesProtocolError('malformed_message')
