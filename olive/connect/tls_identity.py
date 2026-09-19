"""Shared C2/C3 TLS policy: exact Ed25519 certificates, no ambient CA trust."""
from OpenSSL import SSL, crypto
from cryptography.hazmat.primitives import serialization

from .identity import validate_public


def identity_context(key, public, remotes):
    cert = validate_public(public)
    peers = [validate_public(remote) for remote in remotes]
    expected = {peer.public_bytes(serialization.Encoding.DER) for peer in peers}
    ctx = SSL.Context(SSL.TLS_METHOD)
    ctx.set_min_proto_version(SSL.TLS1_3_VERSION)
    ctx.set_max_proto_version(SSL.TLS1_3_VERSION)
    ctx.set_session_cache_mode(SSL.SESS_CACHE_OFF)
    ctx.set_options(SSL.OP_NO_TICKET)
    ctx.use_certificate(cert)
    ctx.use_privatekey(key)
    ctx.check_privatekey()
    for peer in peers:
        ctx.get_cert_store().add_cert(crypto.X509.from_cryptography(peer))
    def verify(connection, certificate, error, depth, valid):
        return bool(valid and depth == 0 and certificate.to_cryptography().public_bytes(
            serialization.Encoding.DER) in expected)
    ctx.set_verify(SSL.VERIFY_PEER | SSL.VERIFY_FAIL_IF_NO_PEER_CERT, verify)
    ctx.set_verify_depth(0)
    return ctx
