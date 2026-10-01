"""olive-world/1: the relay rendezvous protocol and World route credentials.

World is a transport beneath OLIVE Connect. After rendezvous the relay forwards
binary WebSocket messages that carry the paired devices' own TLS 1.3 stream
(pinned Ed25519 certificates, ephemeral ECDHE, AEAD records). Nothing here is
application cryptography: the route credential only decides which two
connections the relay joins, and grants no OLIVE authority.

Key schedule (HKDF-SHA256, RFC 5869, salt = CONTEXT):
  route_secret = HKDF(master, "route-secret" || local || peer || generation || identity)
  route_id     = HKDF(master, "route-id"     || local || peer || generation || identity)[:16]
  credential   = HKDF(route_secret, "relay-credential")
  rendezvous   = SHA-256("olive-world/1 rendezvous" || 0x00 || route_id || credential)  (relay only)
"""
from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
import json
import re
import struct
from urllib.parse import urlsplit

PROTOCOL = 'olive-world/1'
SUBPROTOCOL = 'olive-world.1'
PATH = '/olive-world/1'
VERSION = 1
CONTEXT = b'olive-connect-world/v1'
ROLES = ('desktop', 'phone')
MAX_HELLO = 512
MAX_URL = 256
# Binary tunnel messages. Peers send at most CHUNK; the relay refuses more than MAX_MESSAGE.
CHUNK = 65536
MAX_MESSAGE = 262144

CLOSE_CODES = {
    'normal': 1000,
    'going_away': 1001,
    'protocol_error': 4000,
    'unsupported_version': 4001,
    'hello_timeout': 4002,
    'replaced': 4003,
    'peer_left': 4004,
    'rate_limited': 4005,
    'too_large': 4006,
    'peer_unavailable': 4007,
    'capacity': 4008,
    'idle_timeout': 4009,
}
CLOSE_NAMES = {code: name for name, code in CLOSE_CODES.items()}


class WorldError(ValueError):
    """Fixed category codes, never secrets or peer content."""


def hkdf_sha256(ikm, *, info, length=32, salt=CONTEXT):
    """RFC 5869 HKDF with HMAC-SHA256 (standard library hmac)."""
    if type(ikm) is not bytes or not 1 <= length <= 255 * 32:
        raise WorldError('invalid_key_material')
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    out, block, counter = b'', b'', 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _route_info(label, local_id, peer_id, generation, identity):
    if type(generation) is not int or not 1 <= generation < 2 ** 63:
        raise WorldError('invalid_generation')
    return b'\x00'.join((label, local_id.encode('ascii'), peer_id.encode('ascii'),
                         struct.pack('!Q', generation), identity.encode('ascii')))


def route_secret(master, local_id, peer_id, generation, identity):
    """Per-pair, per-generation route secret. ``identity`` binds it to this Connect identity."""
    if type(master) is not bytes or len(master) != 32:
        raise WorldError('invalid_master_key')
    return hkdf_sha256(master, info=_route_info(b'route-secret', local_id, peer_id, generation, identity))


def route_id(master, local_id, peer_id, generation, identity):
    if type(master) is not bytes or len(master) != 32:
        raise WorldError('invalid_master_key')
    return hkdf_sha256(master, info=_route_info(b'route-id', local_id, peer_id, generation, identity), length=16)


def relay_credential(secret):
    if type(secret) is not bytes or len(secret) != 32:
        raise WorldError('invalid_route_secret')
    return hkdf_sha256(secret, info=b'relay-credential')


def rendezvous(route, credential):
    """The relay's in-memory route key. Knowing a route id alone cannot claim it."""
    return hashlib.sha256(b'olive-world/1 rendezvous\x00' + route + credential).digest()


_HEX32 = re.compile(r'[0-9a-f]{32}')
_HEX64 = re.compile(r'[0-9a-f]{64}')


def hello(role, route, credential):
    if role not in ROLES or type(route) is not bytes or len(route) != 16 or type(credential) is not bytes or len(credential) != 32:
        raise WorldError('invalid_hello')
    return json.dumps(dict(v=VERSION, role=role, route=route.hex(), credential=credential.hex()),
                      sort_keys=True, separators=(',', ':'))


def parse_hello(text):
    """Strict hello. Returns (role, route, credential); raises WorldError with a fixed code."""
    if type(text) is not str or len(text) > MAX_HELLO:
        raise WorldError('protocol_error')
    try:
        value = json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, RecursionError):
        raise WorldError('protocol_error') from None
    if type(value) is not dict or 'v' not in value:
        raise WorldError('protocol_error')
    if value['v'] != VERSION or type(value['v']) is not int:
        raise WorldError('unsupported_version')
    if set(value) != {'v', 'role', 'route', 'credential'} or value['role'] not in ROLES:
        raise WorldError('protocol_error')
    route, credential = value['route'], value['credential']
    if type(route) is not str or type(credential) is not str or not _HEX32.fullmatch(route) or not _HEX64.fullmatch(credential):
        raise WorldError('protocol_error')
    return value['role'], bytes.fromhex(route), bytes.fromhex(credential)


EVENTS = ('waiting', 'paired')


def event(name):
    if name not in EVENTS:
        raise WorldError('invalid_event')
    return json.dumps(dict(v=VERSION, event=name), sort_keys=True, separators=(',', ':'))


def parse_event(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError, RecursionError):
        raise WorldError('protocol_error') from None
    if type(value) is not dict or set(value) != {'v', 'event'} or value['v'] != VERSION or value['event'] not in EVENTS:
        raise WorldError('protocol_error')
    return value['event']


@dataclass(frozen=True)
class RelayURL:
    url: str
    tls: bool
    host: str
    port: int
    path: str

    @property
    def host_header(self):
        host = '[%s]' % self.host if ':' in self.host else self.host
        default = 443 if self.tls else 80
        return host if self.port == default else '%s:%d' % (host, self.port)


LOOPBACK_NAMES = {'localhost'}


def is_loopback(host):
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_private(host):
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private and not address.is_unspecified and not address.is_multicast


def parse_relay_url(url, *, dev=False, test_lan=False):
    """wss:// with normal system trust. ws:// only for explicit development on loopback,
    or (TEST-ONLY, ``test_lan``) a private LAN address for the Mac physical-iPhone test host."""
    if type(url) is not str or not 1 <= len(url) <= MAX_URL or url != url.strip() or any(ord(c) < 33 for c in url):
        raise WorldError('relay_url_invalid')
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise WorldError('relay_url_invalid') from None
    if parts.scheme not in ('wss', 'ws') or not parts.hostname or parts.username or parts.password \
            or parts.query or parts.fragment or '%' in url:
        raise WorldError('relay_url_invalid')
    host = parts.hostname.lower()
    tls = parts.scheme == 'wss'
    if not tls and not ((dev and is_loopback(host)) or (test_lan and is_private(host))):
        # Never a silent plaintext downgrade outside explicit local development.
        raise WorldError('relay_url_requires_wss')
    path = parts.path or '/'
    if path == '/':
        path = PATH
    if not path.startswith('/') or len(path) > 128 or not re.fullmatch(r'[A-Za-z0-9/._~-]+', path):
        raise WorldError('relay_url_invalid')
    return RelayURL(url=url, tls=tls, host=host, port=port or (443 if tls else 80), path=path)


def relay_host(url):
    """Hostname for diagnostics; never the path, credentials or route."""
    try:
        return urlsplit(url).hostname
    except (ValueError, TypeError):
        return None
