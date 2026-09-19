"""Bounded QR contract and standard TLS 1.3 memory-BIO handshake."""
import json
from OpenSSL import SSL
from .tls_identity import identity_context

from .contracts import ConnectError, _unique_object, canonical, identifier, timestamp
from .identity import validate_public

PROTOCOL = 'olive-pairing-tls13/1'
MAX_OFFER = 4096
LIFETIME = 120


def decode_offer(raw, now):
    try:
        if type(raw) is not bytes or len(raw) > MAX_OFFER:
            raise ValueError()
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict or set(value) != {'protocol', 'session_id', 'created_at', 'expires_at', 'identity'}:
            raise ValueError()
        if value['protocol'] != PROTOCOL:
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

    def receive_confirmation(self):
        try:
            return self.connection.recv(128)
        except SSL.WantReadError:
            return b''
        except Exception:
            raise ConnectError('pairing_tls_failed') from None

    def close(self):
        # OpenSSL owns and releases ephemeral secrets. Python cannot promise zeroization.
        self.connection = None
        self.binding = b''
        self.ready = False
