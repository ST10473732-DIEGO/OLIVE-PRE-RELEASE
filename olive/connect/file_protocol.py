"""C6 strict metadata plus bounded raw bytes. Never a filesystem RPC."""
from dataclasses import dataclass, asdict
import hashlib
import json
import re
import struct
import unicodedata

from .contracts import ConnectError, canonical, identifier, timestamp, _unique_object

PROTOCOL = 'olive-files/1'
CHUNK_SIZE = 64 * 1024
MAX_FILE_SIZE = 64 * 1024 * 1024
MAX_METADATA = 4096
MAX_PACKET = 4 + MAX_METADATA + CHUNK_SIZE
TERMINAL = frozenset({'completed', 'declined', 'cancelled', 'failed', 'interrupted', 'dismissed'})
STATES = TERMINAL | {'offered', 'awaiting_approval', 'accepted', 'transferring', 'verifying'}


def filename(value):
    # Reject ambiguous remote names rather than interpreting any platform's paths.
    if (type(value) is not str or not value or len(value.encode('utf-8')) > 180
            or value != value.strip() or value.endswith('.') or '..' in value
            or any(c in '/\\:<>"|?*' or unicodedata.category(c).startswith('C') for c in value)
            or unicodedata.normalize('NFKC', value.split('.')[0]).upper() in {'CON', 'PRN', 'AUX', 'NUL',
                *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
        raise ConnectError('invalid_filename')
    return value


def metadata(value):
    if type(value) is not dict or set(value) != {'name', 'size', 'sha256', 'mime'}:
        raise ConnectError('invalid_file_metadata')
    filename(value['name'])
    if type(value['size']) is not int or not 0 <= value['size'] <= MAX_FILE_SIZE:
        raise ConnectError('file_too_large_or_invalid_size')
    if type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ConnectError('invalid_content_hash')
    if type(value['mime']) is not str or not re.fullmatch(r'[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+', value['mime']) or len(value['mime']) > 100:
        raise ConnectError('invalid_file_type')
    return value


@dataclass(frozen=True)
class FileRequest:
    request_id: str
    protocol_version: str
    transfer_id: str
    source_device_id: str
    target_device_id: str
    operation: str
    arguments: dict
    timestamp: int
    expires_at: int

    @property
    def capability(self):
        return 'files.receive'

    def fingerprint(self):
        return hashlib.sha256(canonical(asdict(self))).hexdigest()

    def encode(self, data=b''):
        raw = canonical(asdict(self))
        packet = struct.pack('!I', len(raw)) + raw + data
        self.decode(packet)
        return packet

    @classmethod
    def decode(cls, packet):
        try:
            if type(packet) is not bytes or not 4 <= len(packet) <= MAX_PACKET:
                raise ValueError()
            length = struct.unpack('!I', packet[:4])[0]
            if not 1 <= length <= MAX_METADATA or 4 + length > len(packet):
                raise ValueError()
            value = json.loads(packet[4:4 + length], object_pairs_hook=_unique_object,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
                raise ValueError()
            for key in ('request_id', 'transfer_id', 'source_device_id', 'target_device_id'):
                identifier(value[key])
            if value['protocol_version'] != PROTOCOL:
                raise ValueError()
            timestamp(value['timestamp']); timestamp(value['expires_at'])
            if not 0 < value['expires_at'] - value['timestamp'] <= 120:
                raise ValueError()
            args, op = value['arguments'], value['operation']
            data = packet[4 + length:]
            if type(args) is not dict or type(op) is not str:
                raise ValueError()
            if op == 'offer':
                metadata(args)
            elif op == 'chunk':
                if set(args) != {'offset'} or type(args['offset']) is not int or not 0 <= args['offset'] <= MAX_FILE_SIZE or not 1 <= len(data) <= CHUNK_SIZE:
                    raise ValueError()
            elif op not in {'complete', 'cancel', 'status'} or args:
                raise ValueError()
            if op != 'chunk' and data:
                raise ValueError()
            return cls(**value), data
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, struct.error):
            raise ConnectError('invalid_file_packet') from None


def response(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
        if (type(value) is not dict or set(value) != {'protocol_version', 'request_id', 'state', 'result' if value.get('state') == 'completed' else 'error'}
                or value['protocol_version'] != PROTOCOL or value['state'] not in {'completed', 'rejected'}):
            raise ValueError()
        identifier(value['request_id'])
        if value['state'] == 'completed':
            result = value['result']
            if type(result) is not dict or set(result) != {'state', 'received_size'} or result['state'] not in STATES or type(result['received_size']) is not int or not 0 <= result['received_size'] <= MAX_FILE_SIZE:
                raise ValueError()
        elif type(value['error']) is not str or not re.fullmatch('[a-z_]{1,80}', value['error']):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ConnectError('invalid_file_response') from None
