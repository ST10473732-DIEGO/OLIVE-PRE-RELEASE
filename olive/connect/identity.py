"""Public Ed25519 identities and vault-only private keys; no recovery by replacement."""
import base64
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.x509.oid import NameOID

from .contracts import ConnectError, canonical, identifier, timestamp

ALGORITHM = 'olive-ed25519-x509/1'
KEY_REFERENCE = 'connect-identity-v1'


def digest(raw):
    value = hashes.Hash(hashes.SHA256())
    value.update(raw)
    return value.finalize()


def public_identity(device_id, key, now):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, device_id)])
    date = datetime.fromtimestamp(now, timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(date - timedelta(minutes=5))
            .not_valid_after(date + timedelta(days=3650)).sign(key, None))
    return dict(device_id=device_id, algorithm=ALGORITHM, key_version=1, created_at=now,
                certificate=base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode('ascii'))


def validate_public(value):
    try:
        if type(value) is not dict or set(value) != {'device_id', 'algorithm', 'key_version', 'created_at', 'certificate'}:
            raise ValueError()
        identifier(value['device_id']); timestamp(value['created_at'])
        if value['algorithm'] != ALGORITHM or type(value['key_version']) is not int or value['key_version'] != 1:
            raise ValueError()
        encoded = value['certificate']
        if type(encoded) is not str or len(encoded) > 2048:
            raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
        cert = x509.load_der_x509_certificate(raw)
        if base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode('ascii') != encoded:
            raise ValueError()
        if cert.subject != x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, value['device_id'])]) or cert.issuer != cert.subject:
            raise ValueError()
        key = cert.public_key()
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError()
        key.verify(cert.signature, cert.tbs_certificate_bytes)
        if cert.not_valid_before_utc != datetime.fromtimestamp(value['created_at'], timezone.utc) - timedelta(minutes=5):
            raise ValueError()
        return cert
    except Exception:
        raise ConnectError('invalid_public_identity') from None


def fingerprint(value):
    cert = validate_public(value)
    # Stable across certificate renewal; display metadata is never an input.
    key = cert.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    material = dict(algorithm=value['algorithm'], key_version=value['key_version'],
                    device_id=value['device_id'], public_key=key.hex())
    return 'C2/1:' + digest(canonical(material)).hex(':').upper()


class DeviceKeyStore:
    """The only Connect adapter permitted to serialize private identity material."""
    def __init__(self, vault):
        self.vault = vault

    def require_empty(self):
        try:
            self.vault.require_available()
            if self.vault.contains(KEY_REFERENCE):
                raise ValueError()
        except Exception:
            raise ConnectError('secure_identity_unavailable') from None

    def create(self, key):
        try:
            self.require_empty()
            raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                    serialization.NoEncryption())
            self.vault.put(KEY_REFERENCE, 'ed25519/1:' + base64.b64encode(raw).decode('ascii'))
        except Exception:
            raise ConnectError('secure_identity_unavailable') from None

    def load(self, public):
        try:
            self.vault.require_available()
            value = self.vault.read_for_provider(KEY_REFERENCE)
            if type(value) is not str or not value.startswith('ed25519/1:') or len(value) != 54:
                raise ValueError()
            key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(value[10:], validate=True))
            cert = validate_public(public)
            if key.public_key() != cert.public_key():
                raise ValueError()
            return key
        except Exception:
            raise ConnectError('secure_identity_unavailable') from None


class DeviceIdentityService:
    def __init__(self, repository, local_id, key_store, clock):
        self.repository, self.local_id = repository, local_id
        self.key_store, self.clock = key_store, clock

    def ensure(self):
        import json
        # Durable reservation precedes vault write. Interrupted provisioning requires
        # explicit future recovery; it can NEVER overwrite an established key.
        with self.repository.transaction() as db:
            row = db.execute('SELECT public,state FROM connect_keys WHERE device_id=?', (self.local_id,)).fetchone()
            if row:
                if row[1] != 'ready':
                    raise ConnectError('identity_recovery_required')
                public = json.loads(row[0])
                self.key_store.load(public)
                return public
            self.key_store.require_empty()
            key = Ed25519PrivateKey.generate()
            public = public_identity(self.local_id, key, int(self.clock()))
            db.execute('INSERT INTO connect_keys VALUES(?,?,?)', (self.local_id, json.dumps(public), 'pending'))
        self.key_store.create(key)
        self.key_store.load(public)
        with self.repository.transaction() as db:
            db.execute("UPDATE connect_keys SET state='ready' WHERE device_id=?", (self.local_id,))
        return public
