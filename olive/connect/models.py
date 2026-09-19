"""Device metadata contains public, bounded fields only. No key material."""
from dataclasses import dataclass

from ..agent.permission_service import PermissionDecision
from .contracts import (CAPABILITIES, CapabilityMetadata, ConnectError, ConnectionState,
                        TrustState, display_name, identifier, timestamp)


def _metadata(record):
    identifier(record.device_id)
    display_name(record.display_name)
    if record.platform not in {'windows', 'linux', 'macos', 'ios', 'android', 'unknown'}:
        raise ConnectError('invalid_platform')
    if record.device_class not in {'desktop', 'laptop', 'phone', 'tablet', 'unknown'}:
        raise ConnectError('invalid_device_class')
    if type(record.revision) is not int or record.revision < 1:
        raise ConnectError('invalid_revision')
    if type(record.capabilities) is not list or len(record.capabilities) > len(CAPABILITIES):
        raise ConnectError('invalid_capability_metadata')
    seen = set()
    for capability in record.capabilities:
        value = CapabilityMetadata(**capability)
        if value.capability in seen:
            raise ConnectError('duplicate_capability')
        seen.add(value.capability)


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    display_name: str
    platform: str
    device_class: str
    created_at: int
    public_identity_metadata: dict
    capabilities: list[dict]
    revision: int

    def __post_init__(self):
        _metadata(self)
        timestamp(self.created_at)
        if type(self.public_identity_metadata) is not dict or set(self.public_identity_metadata) != {'os'}:
            raise ConnectError('invalid_public_metadata')
        display_name(self.public_identity_metadata['os'])


@dataclass(frozen=True)
class PairedDevice:
    device_id: str
    display_name: str
    platform: str
    device_class: str
    trust_state: str
    paired_at: int | None
    last_seen: int | None
    connection_state: str
    connection_kind: str
    capabilities: list[dict]
    permissions: list[dict]
    revision: int
    revoked_at: int | None

    def __post_init__(self):
        _metadata(self)
        TrustState(self.trust_state)
        ConnectionState(self.connection_state)
        if self.connection_kind not in {'none', 'fixture', 'local', 'direct', 'relay'}:
            raise ConnectError('invalid_connection_kind')
        for value in (self.paired_at, self.last_seen, self.revoked_at):
            if value is not None:
                timestamp(value)
        if self.trust_state == 'paired' and (self.paired_at is None or self.revoked_at is not None):
            raise ConnectError('invalid_trust_state')
        if self.trust_state == 'revoked' and self.revoked_at is None:
            raise ConnectError('invalid_trust_state')
        if type(self.permissions) is not list or len(self.permissions) > 256:
            raise ConnectError('invalid_permissions')
        for rule in self.permissions:
            if type(rule) is not dict or set(rule) != {'capability', 'scope', 'decision'}:
                raise ConnectError('invalid_permissions')
            if rule['capability'] not in CAPABILITIES:
                raise ConnectError('unknown_capability')
            PermissionDecision(rule['decision'])
            if rule['scope'] is not None and (type(rule['scope']) is not str or not 1 <= len(rule['scope']) <= 160):
                raise ConnectError('invalid_scope')


def validate_record(record):
    try:
        (DeviceIdentity if 'created_at' in record else PairedDevice)(**record)
    except (TypeError, ValueError, KeyError):
        raise ConnectError('invalid_device_record') from None
    return record
