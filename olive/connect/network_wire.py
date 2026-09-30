"""C3 bounded framing and fresh C2-identity TLS contexts; no system trust store."""
from datetime import datetime, timezone
import struct

from cryptography.hazmat.primitives import serialization

from .contracts import ConnectError, MAX_MESSAGE_BYTES
from .file_protocol import MAX_PACKET
from .inference_protocol import MAX_FRAME as MAX_INFERENCE_BYTES
from .identity import validate_public
from .tls_identity import identity_context

HEADER = struct.Struct('!IBB')
VERSION = 1
REQUEST, RESPONSE, CLOSE, HELLO = 1, 2, 3, 4
SYNC_REQUEST, SYNC_RESPONSE = 5, 6
MAX_SYNC_BYTES = 256_000
FILE_REQUEST, FILE_RESPONSE = 7, 8
INFERENCE_REQUEST, INFERENCE_RESPONSE = 9, 10
STUDIO_REQUEST, STUDIO_RESPONSE = 11, 12
NOTES_REQUEST, NOTES_RESPONSE = 13, 14  # olive-notes/1; bound shared with olive/notes/protocol_v1.json
# olive-draw/1; bound shared with olive/draw/protocol_v1.json. Sent only to peers
# that have shown they speak it (see olive/connect/draw.py).
DRAW_REQUEST, DRAW_RESPONSE = 15, 16
# olive-chat/1 (Remote Chat v2: every Chat mode, attachments and media artifacts).
# Phone -> desktop requests only; sent only to desktops that list it in the probe.
CHAT_REQUEST, CHAT_RESPONSE = 17, 18
KINDS = (REQUEST, RESPONSE, CLOSE, HELLO, SYNC_REQUEST, SYNC_RESPONSE, FILE_REQUEST, FILE_RESPONSE,
         INFERENCE_REQUEST, INFERENCE_RESPONSE, STUDIO_REQUEST, STUDIO_RESPONSE, NOTES_REQUEST, NOTES_RESPONSE,
         DRAW_REQUEST, DRAW_RESPONSE, CHAT_REQUEST, CHAT_RESPONSE)


def limit(kind):
    if kind in (CHAT_REQUEST, CHAT_RESPONSE):
        from .chat_protocol import MAX_FRAME as CHAT_LIMIT
        return CHAT_LIMIT
    if kind in (DRAW_REQUEST, DRAW_RESPONSE):
        from ..draw.protocol import LIMITS as DRAW_LIMITS
        return DRAW_LIMITS['max_frame_bytes']
    if kind in (NOTES_REQUEST, NOTES_RESPONSE):
        from ..notes.limits import LIMITS
        return LIMITS['max_frame_bytes']
    if kind in (STUDIO_REQUEST, STUDIO_RESPONSE):
        from .studio_protocol import MAX_FRAME
        return MAX_FRAME
    if kind in (INFERENCE_REQUEST, INFERENCE_RESPONSE):
        return MAX_INFERENCE_BYTES
    return MAX_PACKET if kind == FILE_REQUEST else MAX_SYNC_BYTES if kind in (SYNC_REQUEST, SYNC_RESPONSE) else MAX_MESSAGE_BYTES


def frame(kind, payload=b''):
    if kind not in KINDS or type(payload) is not bytes:
        raise ConnectError('invalid_frame')
    if len(payload) > limit(kind) or (kind in (CLOSE, HELLO) and payload):
        raise ConnectError('invalid_frame_size')
    return HEADER.pack(len(payload), VERSION, kind) + payload


def header(raw):
    size, version, kind = HEADER.unpack(raw)
    if size > limit(kind):
        raise ConnectError('frame_too_large')
    if version != VERSION:
        raise ConnectError('unsupported_protocol')
    if kind not in KINDS or (kind in (CLOSE, HELLO) and size):
        raise ConnectError('invalid_frame')
    return size, kind


def certificate_bytes(public):
    return validate_public(public).public_bytes(serialization.Encoding.DER)


def require_current(public):
    cert = validate_public(public)
    now = datetime.now(timezone.utc)
    if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
        raise ConnectError('certificate_expired_or_not_yet_valid')
    return cert


def tls_context(service, expected=None, *, local=None):
    """Same C2 key, certificate and OpenSSL verification rules, fresh per socket.

    A listener pins all currently paired certificates; outgoing sockets pin only
    the selected peer. Revocation and exact DER are checked again after handshake.
    """
    public, key = local if local is not None else (service.cryptographic_identity(), None)
    require_current(public)
    if key is None:
        key = service.identities.key_store.load(public)
    peers = {}
    for record in service.paired_devices(timeout=.25):
        if (record['trust_state'] == 'paired' and record.get('revoked_at') is None
                and record.get('public_identity') and (expected is None or record['device_id'] == expected)):
            remote = record['public_identity']
            if expected is not None:
                require_current(remote)
            peers[certificate_bytes(remote)] = remote
    if expected is not None and not peers:
        raise ConnectError('device_not_paired')
    ctx = identity_context(key, public, peers.values())
    return ctx, peers
