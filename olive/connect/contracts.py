"""Bounded wire vocabulary. Nothing here grants tool or execution authority."""
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import uuid

PROTOCOL = 'olive-connect/1'
MAX_MESSAGE_BYTES = 16_384
MAX_AGE_SECONDS = 120


class ConnectError(ValueError):
    """Public errors contain fixed codes, never remote content or exceptions."""


class TrustState(str, Enum):
    UNPAIRED = 'unpaired'
    PAIRING = 'pairing'
    PAIRED = 'paired'
    REVOKED = 'revoked'


class ConnectionState(str, Enum):
    OFFLINE = 'offline'
    DISCOVERING = 'discovering'
    CONNECTING = 'connecting'
    ONLINE = 'online'


# Vocabulary is broader than C1's dispatch registry. Advertisement grants nothing.
CAPABILITIES = frozenset({
    'connect.ping', 'device.status', 'chat.metadata.read', 'chat', 'tasks',
    'calendar', 'reminders', 'notifications', 'files.receive', 'files.send', 'files.shared',
    'filesystem.full', 'studio.view', 'studio.edit', 'studio.build', 'studio.test', 'studio.debug', 'studio.run', 'models.remote', 'apps.launch',
    'terminal', 'desktop_control', 'software.install',
    'sync.tasks', 'sync.calendar', 'sync.reminders', 'sync.chat', 'sync.notes',
})
SAFE_OPERATIONS = {'connect.ping': 'ping', 'device.status': 'read', 'chat.metadata.read': 'read'}


@dataclass(frozen=True)
class CapabilityMetadata:
    capability: str
    supported: bool
    policy_disabled: bool = False

    def __post_init__(self):
        if (self.capability not in CAPABILITIES or type(self.supported) is not bool
                or type(self.policy_disabled) is not bool):
            raise ConnectError('invalid_capability_metadata')


def identifier(value):
    if type(value) is not str:
        raise ConnectError('invalid_identity')
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise ConnectError('invalid_identity') from None
    return value


def timestamp(value):
    if type(value) is not int or not 0 <= value <= 253402300799:
        raise ConnectError('invalid_timestamp')
    return value


def display_name(value):
    if (type(value) is not str or not 1 <= len(value.strip()) <= 100
            or any(ord(c) < 32 for c in value)):
        raise ConnectError('invalid_display_name')
    return value.strip()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConnectError('duplicate_field')
        result[key] = value
    return result


@dataclass(frozen=True)
class RequestEnvelope:
    request_id: str
    protocol_version: str
    source_device_id: str
    target_device_id: str
    capability: str
    operation: str
    arguments: dict
    timestamp: int
    expires_at: int

    @classmethod
    def decode(cls, raw):
        if type(raw) is not bytes:
            raise ConnectError('invalid_message_type')
        if len(raw) > MAX_MESSAGE_BYTES:
            raise ConnectError('message_too_large')
        try:
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
                raise ConnectError('invalid_envelope_fields')
            for key in ('request_id', 'source_device_id', 'target_device_id'):
                identifier(value[key])
            if value['protocol_version'] != PROTOCOL:
                raise ConnectError('unsupported_protocol')
            capability = value['capability']
            if type(capability) is not str or capability not in CAPABILITIES:
                raise ConnectError('unknown_capability')
            if type(value['operation']) is not str or len(value['operation']) > 64:
                raise ConnectError('invalid_operation')
            if type(value['arguments']) is not dict:
                raise ConnectError('invalid_arguments')
            timestamp(value['timestamp']); timestamp(value['expires_at'])
            if not 0 < value['expires_at'] - value['timestamp'] <= MAX_AGE_SECONDS:
                raise ConnectError('invalid_lifetime')
            return cls(**value)
        except ConnectError:
            raise
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise ConnectError('malformed_message') from None

    def validate_operation(self):
        if self.capability not in SAFE_OPERATIONS:
            raise ConnectError('capability_unavailable')
        if self.operation != SAFE_OPERATIONS[self.capability]:
            raise ConnectError('unknown_operation')
        # A bounded untrusted nonce is deliberately never echoed or logged.
        allowed = {'nonce'} if self.capability == 'connect.ping' else set()
        if set(self.arguments) - allowed:
            raise ConnectError('invalid_arguments')
        if 'nonce' in self.arguments and (type(self.arguments['nonce']) is not str
                                        or len(self.arguments['nonce']) > 128):
            raise ConnectError('invalid_arguments')

    def fingerprint(self):
        from dataclasses import asdict
        return hashlib.sha256(canonical(asdict(self))).hexdigest()
