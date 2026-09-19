"""Bounded QR contract and standard TLS 1.3 memory-BIO handshake."""
import json
from OpenSSL import SSL
from .tls_identity import identity_context

from .contracts import ConnectError, _unique_object, canonical, identifier, timestamp
from .identity import validate_public

PROTOCOL = 'olive-pairing-tls13/1'
DESKTOP_PROTOCOL = 'olive-pairing-tls13/2'
MAX_OFFER = 4096
LIFETIME = 120


def validate_endpoint(value):
    """Public routing hint only: numeric RFC1918, loopback or ULA, never DNS."""
    import ipaddress
    try:
        if type(value) is not dict or set(value) != {'address', 'port'}:
            raise ValueError()
        address, port = value['address'], value['port']
        if type(address) is not str or '%' in address:
            raise ValueError()
        ip = ipaddress.ip_address(address)
        ranges = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8') if ip.version == 4 else ('fc00::/7', '::1/128')
        if str(ip) != address or not any(ip in ipaddress.ip_network(n) for n in ranges):
            raise ValueError()
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise ConnectError('invalid_pairing_endpoint') from None


def decode_offer(raw, now):
    try:
        if type(raw) is not bytes or len(raw) > MAX_OFFER:
            raise ValueError()
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict:
            raise ValueError()
        fields = {'protocol', 'session_id', 'created_at', 'expires_at', 'identity'}
        if value.get('protocol') == DESKTOP_PROTOCOL:
            fields |= {'endpoint', 'display_name'}
            validate_endpoint(value.get('endpoint'))
            from .contracts import display_name
            display_name(value.get('display_name'))
        if set(value) != fields:
            raise ValueError()
        if value['protocol'] not in (PROTOCOL, DESKTOP_PROTOCOL):
            raise ConnectError('unsupported_pairing_protocol')
        identifier(value['session_id'])
        timestamp(value['created_at']); timestamp(value['expires_at'])
        if not 0 < value['expires_at'] - value['created_at'] <= LIFETIME:
            raise ValueError()
        if value['created_at'] > now + 5 or value['expires_at'] <= now:
            raise ConnectError('pairing_expired')
        validate_public(value['identity'])
        return value
    except ConnectError:
        raise
    except Exception:
        raise ConnectError('invalid_pairing_offer') from None


def encode_offer(value, now):
    try:
        raw = canonical(value)
        decode_offer(raw, now)
        return raw
    except ConnectError:
        raise
    except Exception:
        raise ConnectError('invalid_pairing_offer') from None


class PairingTLS:
    """No sockets, files, trust-store defaults, session reuse or early data."""
    def __init__(self, key, public, remote, *, server, binding):
        try:
            ctx = identity_context(key, public, [remote])
            self.connection = SSL.Connection(ctx, None)
            (self.connection.set_accept_state if server else self.connection.set_connect_state)()
            self.binding = binding
            self.ready = False
            self.received_bytes = 0
        except Exception:
            raise ConnectError('pairing_tls_failed') from None

    def step(self, incoming=b''):
        if type(incoming) is not bytes or len(incoming) > 32768:
            raise ConnectError('invalid_pairing_message')
        self.received_bytes += len(incoming)
        if self.received_bytes > 131072:
            raise ConnectError('pairing_message_budget_exceeded')
        try:
            if incoming:
                self.connection.bio_write(incoming)
            if not self.ready:
                try:
                    self.connection.do_handshake()
                    self.ready = True
                except SSL.WantReadError:
                    pass
            out = bytearray()
            while True:
                try:
                    out.extend(self.connection.bio_read(32768))
                    if len(out) > 32768:
                        raise ValueError()
                except SSL.WantReadError:
                    break
            return bytes(out)
        except Exception:
            raise ConnectError('pairing_tls_failed') from None

    def comparison(self):
        if not self.ready:
            raise ConnectError('pairing_not_authenticated')
        # Full 256-bit comparison, not an ad-hoc short PIN protocol. RFC 8446 §7.5.
        return self.connection.export_keying_material(
            b'EXPORTER-OLIVE-PAIRING-v1', 32, self.binding).hex(':').upper()

    def confirm(self):
        self.connection.send(b'OLIVE-CONFIRM/1:' + self.binding)

    def receive_confirmation(self, size=128):
        try:
            return self.connection.recv(size)
        except SSL.WantReadError:
            return b''
        except Exception:
            raise ConnectError('pairing_tls_failed') from None

    def close(self):
        # OpenSSL owns and releases ephemeral secrets. Python cannot promise zeroization.
        self.connection = None
        self.binding = b''
        self.ready = False
