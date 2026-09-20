"""C5 portable records. Native validators, explicit schemas, no authority fields."""
from dataclasses import dataclass, asdict
import hashlib
import json
import uuid

from ..connect.contracts import ConnectError, canonical, identifier, _unique_object
from ..personal import validation
from ..personal.calendar import event
from ..personal.reminders import validate_reminder

PROTOCOL = 'olive-sync/1'
DOMAINS = {'task': 'tasks', 'calendar': 'calendar', 'event': 'calendar',
           'reminder': 'reminders', 'conversation': 'chat', 'message': 'chat'}
CAPABILITIES = frozenset('sync.' + value for value in DOMAINS.values())
MAX_RECORD = 72_000
MAX_BATCH = 8
MAX_BYTES = 256_000
MAX_DEVICES = 32
VALIDATORS = {'task': validation.task, 'calendar': validation.calendar,
              'event': event, 'reminder': validate_reminder}


def record_id(value):
    if type(value) is not str or len(value) not in (32, 36):
        raise ConnectError('invalid_record_id')
    try:
        parsed = uuid.UUID(value)
        if value not in (parsed.hex, str(parsed)):
            raise ValueError()
    except ValueError:
        raise ConnectError('invalid_record_id') from None
    return value


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def vector(value):
    if type(value) is not dict or not 1 <= len(value) <= MAX_DEVICES:
        raise ConnectError('invalid_revision_vector')
    for device, count in value.items():
        identifier(device)
        if type(count) is not int or not 1 <= count <= 2**53:
            raise ConnectError('invalid_revision_vector')
    return value


def dominates(left, right):
    return all(left.get(k, 0) >= v for k, v in right.items())


@dataclass(frozen=True)
class SyncRecord:
    kind: str
    record_id: str
    schema_version: int
    revision: str
    ancestry: dict
    origin_device_id: str
    editor_device_id: str
    updated_at: str
    deleted: bool
    payload: dict
    editor_identity: dict
    signature: str

    def value(self):
        return asdict(self)

    def fingerprint(self):
        return digest(self.value())

    @classmethod
    def parse(cls, value):
        try:
            if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
                raise ConnectError('invalid_record_fields')
            record = cls(**value)
            if type(record.schema_version) is not int or record.schema_version != 1:
                raise ConnectError('unsupported_record_version')
            if record.kind not in DOMAINS:
                raise ConnectError('unsupported_record_kind')
            record_id(record.record_id)
            identifier(record.revision)
            identifier(record.origin_device_id)
            identifier(record.editor_device_id)
            vector(record.ancestry)
            if record.editor_device_id not in record.ancestry:
                raise ConnectError('invalid_revision_vector')
            if type(record.deleted) is not bool or type(record.payload) is not dict:
                raise ConnectError('invalid_record')
            from datetime import datetime
            if type(record.updated_at) is not str or len(record.updated_at) > 80 or datetime.fromisoformat(record.updated_at).tzinfo is None:
                raise ConnectError('invalid_record_time')
            if record.deleted:
                if record.payload:
                    raise ConnectError('invalid_tombstone')
            else:
                if record.kind in ('conversation', 'message'):
                    from .chat import conversation, message
                    payload = (conversation if record.kind == 'conversation' else message)(record.payload)
                else:
                    payload = VALIDATORS[record.kind](record.payload)
                if payload != record.payload:
                    raise ConnectError('noncanonical_record')
                # Agent attempts are execution state, never a portable relationship.
                if record.payload.get('agent_task_id'):
                    raise ConnectError('unsyncable_relationship')
            if len(canonical(value)) > MAX_RECORD:
                raise ConnectError('record_too_large')
            from .provenance import verify
            verify(value)
            return record
        except ConnectError:
            raise
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ConnectError('invalid_record') from None


@dataclass(frozen=True)
class SyncRequest:
    protocol_version: str
    request_id: str
    source_device_id: str
    target_device_id: str
    updated_by_device_id: str
    capability: str
    operation: str
    arguments: dict
    timestamp: int
    expires_at: int

    def fingerprint(self):
        return digest(asdict(self))

    @classmethod
    def decode(cls, raw):
        try:
            if type(raw) is not bytes or len(raw) > MAX_BYTES:
                raise ConnectError('sync_message_too_large')
            value = json.loads(raw, object_pairs_hook=_unique_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
                raise ConnectError('invalid_sync_fields')
            request = cls(**value)
            if request.protocol_version != PROTOCOL:
                raise ConnectError('unsupported_protocol')
            for key in ('request_id', 'source_device_id', 'target_device_id', 'updated_by_device_id'):
                identifier(getattr(request, key))
            if request.source_device_id != request.updated_by_device_id:
                raise ConnectError('source_mismatch')
            if request.capability not in CAPABILITIES or request.operation != 'exchange':
                raise ConnectError('unsupported_sync_operation')
            if (type(request.timestamp) is not int or type(request.expires_at) is not int
                    or not 0 < request.expires_at - request.timestamp <= 120):
                raise ConnectError('invalid_lifetime')
            args = request.arguments
            if type(args) is not dict or set(args) != {'records', 'cursor'}:
                raise ConnectError('invalid_sync_scope')
            if type(args['cursor']) is not int or not 0 <= args['cursor'] <= 2**53:
                raise ConnectError('invalid_sync_cursor')
            if type(args['records']) is not list or len(args['records']) > MAX_BATCH:
                raise ConnectError('sync_batch_too_large')
            seen = set()
            for value in args['records']:
                record = SyncRecord.parse(value)
                if 'sync.' + DOMAINS[record.kind] != request.capability:
                    raise ConnectError('sync_scope_mismatch')
                if record.record_id in seen:
                    raise ConnectError('duplicate_batch_record')
                seen.add(record.record_id)
            return request
        except ConnectError:
            raise
        except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
            raise ConnectError('malformed_sync_message') from None
