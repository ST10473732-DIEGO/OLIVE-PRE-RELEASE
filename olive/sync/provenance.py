"""Revision signatures reuse C2's vault identity; transport alone grants access.

An unpaired historical editor's certificate is provenance evidence, never trust
or sync authority. Known UUID/key substitutions are rejected at the receiver.
"""
import base64
from cryptography.exceptions import InvalidSignature
from ..connect.contracts import ConnectError, canonical
from ..connect.identity import validate_public


def message(value):
    return b'OLIVE-SYNC-REVISION/1\0' + canonical({k: v for k, v in value.items() if k != 'signature'})


def sign(value, public, key):
    value = dict(value, editor_identity=public)
    value['signature'] = base64.b64encode(key.sign(message(value))).decode('ascii')
    return value


def verify(value):
    try:
        public = value['editor_identity']
        if public['device_id'] != value['editor_device_id']:
            raise ConnectError('editor_identity_mismatch')
        signature = value['signature']
        if type(signature) is not str or len(signature) != 88:
            raise ConnectError('invalid_revision_signature')
        validate_public(public).public_key().verify(base64.b64decode(signature, validate=True), message(value))
    except ConnectError:
        raise
    except (InvalidSignature, ValueError, KeyError, TypeError):
        raise ConnectError('invalid_revision_signature') from None


def bind_editors(service, authority, records, peer, public):
    for record in records:
        editor = record['editor_device_id']
        claimed = record['editor_identity']
        if editor == peer and claimed != public:
            raise ConnectError('editor_identity_mismatch')
        known = service.repository.get(authority, editor)
        if known:
            expected = service.network.local_identity[0] if editor == service.local_id else known.get('public_identity')
            if expected != claimed:
                raise ConnectError('editor_identity_mismatch')
