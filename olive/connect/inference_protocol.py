"""Remote AI v1: explicit text input, public presets, no executable authority."""
from dataclasses import asdict, dataclass
import hashlib
import json
import uuid

from .contracts import ConnectError, canonical, identifier, timestamp, _unique_object

PROTOCOL = 'olive-inference/1'
CAPABILITY = 'models.remote'
PRESETS = ('fast', 'normal', 'max')
MAX_FRAME = 72_000
MAX_MESSAGES = 24
MAX_MESSAGE = 16_000
MAX_INPUT = 48_000
MAX_TOKENS = 2048
MAX_OUTPUT = 64_000
MAX_SECONDS = 120
CHUNK_BYTES = 4096
STATES = {'awaiting_approval', 'queued', 'starting', 'streaming', 'completed',
          'cancelled', 'failed', 'timed_out', 'connection_lost', 'revoked'}
TERMINAL = STATES - {'awaiting_approval', 'queued', 'starting', 'streaming'}
ERRORS = {'permission_denied', 'confirmation_required', 'device_revoked', 'device_unavailable',
          'model_unavailable', 'busy', 'rate_limited', 'input_too_large', 'output_limit',
          'generation_timeout', 'cancelled', 'connection_lost', 'inference_failed',
          'invalid_request', 'changed_duplicate', 'expired_request', 'unknown_request',
          'stream_invalid', 'request_indeterminate', 'ledger_full'}


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ConnectError('invalid_request')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def input_size(messages):
    if type(messages) is not list or not 1 <= len(messages) <= MAX_MESSAGES:
        raise ConnectError('input_too_large')
    total = 0
    for item in messages:
        if (type(item) is not dict or set(item) != {'role', 'content'}
                or item['role'] not in ('user', 'assistant') or type(item['content']) is not str):
            raise ConnectError('invalid_request')
        size = len(item['content'].encode('utf-8'))
        if not size or size > MAX_MESSAGE:
            raise ConnectError('input_too_large')
        total += size
    if total > MAX_INPUT:
        raise ConnectError('input_too_large')
    if messages[-1]['role'] != 'user':
        raise ConnectError('invalid_request')
    return total


def decode(raw):
    if type(raw) is not bytes or len(raw) > MAX_FRAME:
        raise ConnectError('input_too_large')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ConnectError('invalid_request') from None


@dataclass(frozen=True)
class InferenceRequest:
    request_id: str
    protocol_version: str
    source_device_id: str
    target_device_id: str
    job_id: str
    operation: str
    arguments: dict
    timestamp: int
    expires_at: int

    capability = CAPABILITY

    @classmethod
    def decode(cls, raw):
        try:
            v = decode(raw)
            if type(v) is not dict or set(v) != set(cls.__dataclass_fields__):
                raise ConnectError('invalid_request')
            for key in ('request_id', 'source_device_id', 'target_device_id', 'job_id'):
                identifier(v[key])
            if v['protocol_version'] != PROTOCOL:
                raise ConnectError('invalid_request')
            timestamp(v['timestamp']); timestamp(v['expires_at'])
            integer(v['expires_at'] - v['timestamp'], 1, MAX_SECONDS)
            a = v['arguments']
            if type(a) is not dict:
                raise ConnectError('invalid_request')
            if v['operation'] == 'start':
                if set(a) != {'preset', 'messages', 'input_fingerprint', 'max_tokens', 'max_output_bytes', 'seconds'}:
                    raise ConnectError('invalid_request')
                if type(a['preset']) is not str or a['preset'] not in PRESETS:
                    raise ConnectError('model_unavailable')
                input_size(a['messages'])
                if a['input_fingerprint'] != digest(a['messages']):
                    raise ConnectError('invalid_request')
                integer(a['max_tokens'], 1, MAX_TOKENS)
                integer(a['max_output_bytes'], 1, MAX_OUTPUT)
                integer(a['seconds'], 1, MAX_SECONDS)
                if v['request_id'] != v['job_id']:
                    raise ConnectError('invalid_request')
            elif v['operation'] == 'poll':
                if set(a) != {'after'}:
                    raise ConnectError('invalid_request')
                integer(a['after'], 0, MAX_OUTPUT)
            elif v['operation'] not in ('cancel', 'status') or a:
                raise ConnectError('invalid_request')
            return cls(**v)
        except ConnectError:
            raise
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ConnectError('invalid_request') from None

    def encode(self):
        return canonical(asdict(self))

    def fingerprint(self):
        return digest(asdict(self))


def request(source, target, operation, *, job_id=None, arguments=None, now):
    identity = str(uuid.uuid4())
    value = InferenceRequest(job_id if operation == 'start' and job_id else identity,
        PROTOCOL, source, target, job_id or identity, operation, arguments or {}, now, now + MAX_SECONDS)
    return InferenceRequest.decode(value.encode())


def response(raw):
    """Strict peer output, including ordered content-only events and coarse status."""
    try:
        v = decode(raw)
        if (type(v) is not dict or set(v) != {'protocol_version', 'request_id', 'job_id', 'result', 'error'}
                or v['protocol_version'] != PROTOCOL):
            raise ValueError()
        identifier(v['request_id']); identifier(v['job_id'])
        if v['error'] is not None:
            if v['error'] not in ERRORS or v['result'] is not None:
                raise ValueError()
            return v
        r = v['result']
        if type(r) is not dict:
            raise ValueError()
        if set(r) == {'presets', 'permission', 'busy'}:
            if (type(r['presets']) is not dict or set(r['presets']) != set(PRESETS)
                    or any(type(x) is not bool for x in r['presets'].values())
                    or r['permission'] not in ('deny', 'ask', 'allow') or type(r['busy']) is not bool):
                raise ValueError()
        elif set(r) == {'state', 'events', 'error'}:
            if r['state'] not in STATES or r['error'] is not None and r['error'] not in ERRORS:
                raise ValueError()
            if type(r['events']) is not list or len(r['events']) > 8:
                raise ValueError()
            for event in r['events']:
                if type(event) is not dict or set(event) != {'sequence', 'text'}:
                    raise ValueError()
                integer(event['sequence'], 1, MAX_OUTPUT)
                if type(event['text']) is not str or not 1 <= len(event['text'].encode()) <= CHUNK_BYTES:
                    raise ValueError()
        else:
            raise ValueError()
        return v
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ConnectError('stream_invalid') from None
