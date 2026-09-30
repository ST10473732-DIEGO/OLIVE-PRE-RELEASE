"""olive-draw/1 wire format: strict JSON, explicit schemas, bounded sizes.

Carried over OLIVE Connect frames 15/16 (Notes uses 13/14). Nothing from the
network is deserialized into objects or executed; records are validated field
by field by ``document.validate_record`` before the store sees them. Unknown
versions, operations or fields fail closed.
"""
import base64
import json
import re
import uuid
from pathlib import Path

from .document import AT, IMAGE_TYPES, LIMITS as DOCUMENT_LIMITS, UUID

SPEC = json.loads(Path(__file__).with_name('protocol_v1.json').read_text(encoding='utf-8'))
PROTOCOL = SPEC['protocol']
CAPABILITY = SPEC['capability']
LIMITS = SPEC['limits']
SCHEMAS = SPEC['document_schemas']
OPERATIONS = SPEC['operations']
STATUSES = frozenset(SPEC['statuses'])
ASSET_STATUSES = frozenset(SPEC['asset_statuses'])
ERRORS = frozenset(SPEC['errors'])
REQUEST_FIELDS = {'protocol_version', 'request_id', 'source_device_id', 'target_device_id', 'operation',
                  'arguments', 'timestamp', 'expires_at'}
SHA256 = re.compile(r'^[0-9a-f]{64}$')


class DrawProtocolError(ValueError):
    """Fixed error codes only."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DrawProtocolError('malformed_message')
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError()


def _loads(raw):
    if type(raw) is not bytes:
        raise DrawProtocolError('malformed_message')
    if len(raw) > LIMITS['max_frame_bytes']:
        raise DrawProtocolError('payload_too_large')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique, parse_constant=_reject_constant)
    except DrawProtocolError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise DrawProtocolError('malformed_message') from None


def dumps(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(raw) > LIMITS['max_frame_bytes']:
        raise DrawProtocolError('payload_too_large')
    return raw


def uuid_text(value):
    if type(value) is not str or not UUID.fullmatch(value):
        raise DrawProtocolError('malformed_message')
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise DrawProtocolError('malformed_message') from None
    return value


def integer(value, low=0, high=2 ** 53):
    if type(value) is not int or not low <= value <= high:
        raise DrawProtocolError('malformed_message')
    return value


def _fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise DrawProtocolError('malformed_message')


def _wants(value):
    if type(value) is not list or len(value) > LIMITS['max_wants'] or any(
            type(v) is not str or not SHA256.fullmatch(v) for v in value) or len(set(value)) != len(value):
        raise DrawProtocolError('malformed_message')
    return list(value)


def _versions(value):
    if type(value) is not list or not 1 <= len(value) <= 4 or any(type(v) is not str or len(v) > 32 for v in value):
        raise DrawProtocolError('malformed_message')
    return list(value)


def _schemas(value):
    if type(value) is not list or not 1 <= len(value) <= 16 or any(type(v) is not int or not 1 <= v <= 1000 for v in value):
        raise DrawProtocolError('malformed_message')
    return list(value)


def validate_entry(entry):
    if type(entry) is not dict:
        raise DrawProtocolError('malformed_message')
    if set(entry) == {'seq', 'record'}:
        integer(entry['seq'], 1)
        # Shape only here; the receiver validates each record fully and refuses
        # just that entry, so one record it cannot accept (a newer operation
        # type, a size limit) never blocks the rest of the feed.
        if type(entry['record']) is not dict or type(entry['record'].get('record_id')) is not str:
            raise DrawProtocolError('malformed_message')
        return entry
    if set(entry) == {'seq', 'purge'}:
        integer(entry['seq'], 1)
        purge = entry['purge']
        _fields(purge, SPEC['purge'])
        uuid_text(purge['drawing_id'])
        uuid_text(purge['device'])
        if type(purge['at']) is not str or not AT.fullmatch(purge['at']):
            raise DrawProtocolError('malformed_message')
        return entry
    raise DrawProtocolError('malformed_message')


def validate_arguments(operation, arguments):
    """Returns arguments with byte fields decoded."""
    spec = OPERATIONS.get(operation)
    if spec is None:
        raise DrawProtocolError('malformed_message')
    _fields(arguments, spec['required'], spec['optional'])
    if operation == 'hello':
        return {'versions': _versions(arguments['versions']), 'schemas': _schemas(arguments['schemas'])}
    uuid_text(arguments['epoch'])
    if operation == 'sync':
        entries = arguments['entries']
        if type(entries) is not list or len(entries) > LIMITS['max_entries']:
            raise DrawProtocolError('payload_too_large' if type(entries) is list else 'malformed_message')
        seqs = [validate_entry(e)['seq'] for e in entries]
        if len(set(seqs)) != len(seqs):
            raise DrawProtocolError('malformed_message')
        return {'epoch': arguments['epoch'], 'entries': entries}
    # asset
    chunk = LIMITS['asset_chunk_bytes']
    count_limit = -(-LIMITS['max_asset_bytes'] // chunk)
    side = DOCUMENT_LIMITS['max_asset_side']
    if type(arguments['asset_id']) is not str or not SHA256.fullmatch(arguments['asset_id']):
        raise DrawProtocolError('malformed_message')
    if arguments['mime'] not in IMAGE_TYPES:
        raise DrawProtocolError('unsupported_image')
    result = {'epoch': arguments['epoch'], 'transfer_id': uuid_text(arguments['transfer_id']),
              'asset_id': arguments['asset_id'], 'mime': arguments['mime'],
              'width': integer(arguments['width'], 1, side), 'height': integer(arguments['height'], 1, side),
              'total_bytes': integer(arguments['total_bytes'], 1, LIMITS['max_asset_bytes']),
              'count': integer(arguments['count'], 1, count_limit), 'index': integer(arguments['index'], 0, count_limit - 1)}
    if result['index'] >= result['count'] or result['count'] != -(-result['total_bytes'] // chunk):
        raise DrawProtocolError('malformed_message')
    value = arguments['data']
    if type(value) is not str or len(value) > (chunk * 4) // 3 + 4:
        raise DrawProtocolError('payload_too_large' if type(value) is str else 'malformed_message')
    try:
        data = base64.b64decode(value, validate=True)
    except Exception:
        raise DrawProtocolError('malformed_message') from None
    if not data or len(data) > chunk:
        raise DrawProtocolError('malformed_message')
    result['data'] = data
    return result


def b64(raw):
    return base64.b64encode(raw).decode('ascii')


def encode_request(request_id, source, target, operation, arguments, now):
    value = {'protocol_version': PROTOCOL, 'request_id': request_id, 'source_device_id': source,
             'target_device_id': target, 'operation': operation, 'arguments': arguments,
             'timestamp': now, 'expires_at': now + LIMITS['max_request_lifetime_seconds']}
    return dumps(value)


def decode_request(raw):
    value = _loads(raw)
    if type(value) is not dict or set(value) != REQUEST_FIELDS:
        raise DrawProtocolError('malformed_message')
    if value['protocol_version'] != PROTOCOL:
        raise DrawProtocolError('unsupported_protocol')
    for key in ('request_id', 'source_device_id', 'target_device_id'):
        uuid_text(value[key])
    if type(value['operation']) is not str or value['operation'] not in OPERATIONS:
        raise DrawProtocolError('malformed_message')
    integer(value['timestamp'], 0, 253402300799)
    integer(value['expires_at'], 0, 253402300799)
    if not 0 < value['expires_at'] - value['timestamp'] <= LIMITS['max_request_lifetime_seconds']:
        raise DrawProtocolError('malformed_message')
    value['arguments'] = validate_arguments(value['operation'], value['arguments'])
    return value


def check_fresh(request, now):
    if request['timestamp'] > now + LIMITS['future_tolerance_seconds'] or request['expires_at'] <= now:
        raise DrawProtocolError('expired_request')


def encode_response(request_id, *, result=None, error=None):
    if error is not None:
        if error not in ERRORS:
            error = 'malformed_message'
        return dumps({'protocol_version': PROTOCOL, 'request_id': request_id, 'state': 'rejected', 'error': error})
    return dumps({'protocol_version': PROTOCOL, 'request_id': request_id, 'state': 'completed', 'result': result})


def decode_response(raw):
    value = _loads(raw)
    if type(value) is not dict or value.get('protocol_version') != PROTOCOL or value.get('state') not in ('completed', 'rejected'):
        raise DrawProtocolError('malformed_message')
    expected = {'protocol_version', 'request_id', 'state', 'result' if value['state'] == 'completed' else 'error'}
    if set(value) != expected:
        raise DrawProtocolError('malformed_message')
    if value['request_id'] is not None:
        uuid_text(value['request_id'])
    if value['state'] == 'rejected' and (type(value['error']) is not str or len(value['error']) > 64):
        raise DrawProtocolError('malformed_message')
    return value


def validate_result(operation, result, entries=None):
    """Sender-side validation of a peer's completed result."""
    if operation == 'hello':
        _fields(result, ('versions', 'epoch', 'schemas', 'wants'))
        _versions(result['versions'])
        _schemas(result['schemas'])
        uuid_text(result['epoch'])
        return dict(result, wants=_wants(result['wants']))
    if operation == 'sync':
        _fields(result, ('epoch', 'results', 'wants'))
        uuid_text(result['epoch'])
        rows = result['results']
        if type(rows) is not list or len(rows) != len(entries):
            raise DrawProtocolError('malformed_message')
        decoded = []
        for row in rows:
            _fields(row, ('status',), ('error',))
            if row['status'] not in STATUSES:
                raise DrawProtocolError('malformed_message')
            if 'error' in row and (type(row['error']) is not str or row['error'] not in ERRORS):
                raise DrawProtocolError('malformed_message')
            decoded.append({'status': row['status'], 'error': row.get('error')})
        return {'epoch': result['epoch'], 'results': decoded, 'wants': _wants(result['wants'])}
    if operation == 'asset':
        _fields(result, ('epoch', 'status'), ('error',))
        uuid_text(result['epoch'])
        if result['status'] not in ASSET_STATUSES:
            raise DrawProtocolError('malformed_message')
        if 'error' in result and (type(result['error']) is not str or result['error'] not in ERRORS):
            raise DrawProtocolError('malformed_message')
        return {'epoch': result['epoch'], 'status': result['status'], 'error': result.get('error')}
    raise DrawProtocolError('malformed_message')
