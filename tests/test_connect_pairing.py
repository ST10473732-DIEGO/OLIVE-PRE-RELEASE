"""Real TLS/Ed25519, synthetic vault only. Never prints private material."""
import base64
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from olive.connect.contracts import ConnectError, canonical
from olive.connect.identity import DeviceKeyStore, KEY_REFERENCE, fingerprint, public_identity
from olive.connect.pairing_wire import decode_offer, encode_offer
from olive.connect.service import DesktopDeviceService


class MemoryVault:
    """Test-only secure-store contract double; no production fallback."""
    def __init__(self):
        self.values = {}
        self.available = True
        self.writes = 0

    def require_available(self):
        if not self.available:
            raise RuntimeError('fixture vault unavailable')

    def contains(self, ref):
        self.require_available()
        return ref in self.values

    def put(self, ref, secret):
        self.require_available()
        self.writes += 1
        self.values[ref] = secret

    def read_for_provider(self, ref):
        self.require_available()
        return self.values[ref]


class PairingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = int(time.time())
        self.ticks = 1000
        self.vaults = [MemoryVault(), MemoryVault()]
        self.a, self.b = [DesktopDeviceService(self.root / str(i), fixture_mode=True,
            key_store=DeviceKeyStore(v), clock=lambda: self.now, monotonic=lambda: self.ticks)
            for i, v in enumerate(self.vaults)]

    def tearDown(self):
        self.a.close(); self.b.close()
        self.temp.cleanup()

    def start(self):
        offer = self.a.pairing.create_offer()
        reply = self.b.pairing.accept_offer(offer)
        self.sid = json.loads(offer)['session_id']
        self.a.pairing.receive_reply(reply)
        self.pump()
        return offer, reply

    def pump(self):
        pending = b''
        for _ in range(8):
            outgoing = self.b.pairing.exchange(self.sid, pending)
            pending = self.a.pairing.exchange(self.sid, outgoing)

    def pair(self):
        self.start()
        left = self.a.pairing.preview(self.sid)
        right = self.b.pairing.preview(self.sid)
        self.assertEqual(left['comparison'], right['comparison'])
        self.a.pairing.confirm(self.sid, right['comparison'])
        self.b.pairing.confirm(self.sid, left['comparison'])
        self.pump()
        return self.a.pairing.complete(self.sid), self.b.pairing.complete(self.sid)

    def test_identity_once_restart_rename_and_different_install(self):
        public = self.a.cryptographic_identity()
        self.a.rename(self.a.local_id, 'Main laptop')
        self.assertEqual(self.a.cryptographic_identity(), public)
        restart = DesktopDeviceService(self.root / '0', key_store=DeviceKeyStore(self.vaults[0]))
        try:
            self.assertEqual(restart.cryptographic_identity(), public)
            self.assertEqual(self.vaults[0].writes, 1)
            self.assertNotEqual(fingerprint(public), fingerprint(self.b.cryptographic_identity()))
        finally:
            restart.close()

    def test_missing_and_malformed_vault_never_replace(self):
        self.a.cryptographic_identity()
        for bad in [None, 'broken', 'ed25519/1:' + base64.b64encode(bytes(32)).decode()]:
            if bad is None:
                self.vaults[0].values.clear()
            else:
                self.vaults[0].values[KEY_REFERENCE] = bad
            with self.assertRaisesRegex(ConnectError, 'secure_identity_unavailable'):
                self.a.cryptographic_identity()
        self.assertEqual(self.vaults[0].writes, 1)

    def test_unavailable_vault_fails_closed(self):
        self.vaults[0].available = False
        with self.assertRaises(Exception):
            self.a.cryptographic_identity()
        self.assertEqual(self.vaults[0].writes, 0)
        self.assertEqual(self.a.paired_devices(), [])

    def test_interrupted_creation_requires_recovery(self):
        with patch.object(self.vaults[0], 'put', side_effect=RuntimeError('unavailable')):
            with self.assertRaises(ConnectError):
                self.a.cryptographic_identity()
        with self.assertRaisesRegex(ConnectError, 'recovery_required'):
            self.a.cryptographic_identity()
        self.assertEqual(self.vaults[0].writes, 0)

    def test_pair_binds_mutual_identity_and_conservative_permissions(self):
        left, right = self.pair()
        self.assertEqual(left['public_identity'], self.b.cryptographic_identity())
        self.assertEqual(right['public_identity'], self.a.cryptographic_identity())
        self.assertEqual(left['permissions'], [])
        self.assertEqual(left['capabilities'], [])
        self.assertEqual(left['connection_state'], 'offline')
        for cap in ['chat', 'terminal', 'desktop_control', 'software.install']:
            self.assertEqual(self.a.permission(left['device_id'], cap).value, 'deny')
        self.assertEqual(self.a.require_paired_identity(left['public_identity']), left)

    def test_offer_strict_schema_versions_size_and_duplicates(self):
        raw = self.a.pairing.create_offer()
        obj = decode_offer(raw, self.now)
        self.assertEqual(encode_offer(obj, self.now), raw)
        cases = [b'x' * 4097, b'[]', b'\xff', b'{"a":1,"a":2}', b'null']
        for key, value in [('protocol', 'future'), ('created_at', True), ('expires_at', self.now + 999),
                           ('permissions', [{'capability':'terminal','decision':'allow'}]),
                           ('capabilities', ['desktop_control']), ('hostname', 'same'), ('account', 'same'),
                           ('ip', '127.0.0.1')]:
            cases.append(canonical(dict(obj, **{key:value})))
        for case in cases:
            with self.subTest(kind=len(case)), self.assertRaises(ConnectError):
                self.b.pairing.accept_offer(case)
        self.assertEqual(self.b.paired_devices(), [])

    def test_expired_offer_and_monotonic_expiry(self):
        raw = self.a.pairing.create_offer()
        self.now += 120
        with self.assertRaisesRegex(ConnectError, 'expired'):
            self.b.pairing.accept_offer(raw)
        self.now -= 120
        self.start()
        self.now -= 60
        self.ticks += 120
        with self.assertRaisesRegex(ConnectError, 'expired'):
            self.a.pairing.preview(self.sid)
        self.assertIsNone(self.a.pairing._sessions[self.sid]['tls'])

    def test_consumed_offer_rejected_even_after_restart(self):
        offer, _ = self.start()
        with self.assertRaisesRegex(ConnectError, 'replayed'):
            self.b.pairing.accept_offer(offer)
        self.b.close()
        self.b = DesktopDeviceService(self.root / '1', key_store=DeviceKeyStore(self.vaults[1]), clock=lambda:self.now)
        with self.assertRaisesRegex(ConnectError, 'replayed'):
            self.b.pairing.accept_offer(offer)

    def test_cancel_invalidates_and_cleans(self):
        offer, _ = self.start()
        self.a.pairing.cancel(self.sid)
        self.assertEqual(self.a.paired_devices(), [])
        for field in ['tls', 'peer', 'offer', 'reply']:
            self.assertIsNone(self.a.pairing._sessions[self.sid][field])
        with self.assertRaises(ConnectError):
            self.a.pairing.exchange(self.sid)
        with self.assertRaises(ConnectError):
            self.b.pairing.accept_offer(offer)

    def test_no_confirmation_no_trust_and_one_sided_insufficient(self):
        self.start()
        with self.assertRaisesRegex(ConnectError, 'confirmation_required'):
            self.a.pairing.complete(self.sid)
        self.a.pairing.confirm(self.sid, self.b.pairing.preview(self.sid)['comparison'])
        self.pump()
        for service in [self.a, self.b]:
            with self.assertRaisesRegex(ConnectError, 'confirmation_required'):
                service.pairing.complete(self.sid)
            self.assertEqual(service.paired_devices(), [])

    def test_mismatched_comparison_fails_closed(self):
        self.start()
        with self.assertRaisesRegex(ConnectError, 'comparison_mismatch'):
            self.a.pairing.confirm(self.sid, '00:' * 32)
        with self.assertRaises(ConnectError):
            self.a.pairing.complete(self.sid)
        self.assertEqual(self.a.paired_devices(), [])

    def test_non_ascii_comparison_fails_and_cleans_session(self):
        self.start()
        with self.assertRaisesRegex(ConnectError, 'comparison_mismatch'):
            self.a.pairing.confirm(self.sid, 'é')
        self.assertIsNone(self.a.pairing._sessions[self.sid]['tls'])

    def test_changed_reply_cannot_replace_candidate(self):
        _, reply = self.start()
        changed = json.loads(reply)
        changed['identity'] = public_identity(self.b.local_id, Ed25519PrivateKey.generate(), self.now)
        with self.assertRaises(ConnectError):
            self.a.pairing.receive_reply(canonical(changed))

    def test_substituted_certificate_fails_tls(self):
        offer = self.a.pairing.create_offer()
        reply = json.loads(self.b.pairing.accept_offer(offer))
        self.sid = json.loads(offer)['session_id']
        reply['identity'] = public_identity(self.b.local_id, Ed25519PrivateKey.generate(), self.now)
        self.a.pairing.receive_reply(canonical(reply))
        with self.assertRaisesRegex(ConnectError, 'authentication_failed'):
            self.pump()
        self.assertEqual(self.a.paired_devices(), [])

    def test_changed_transcript_fails(self):
        offer = self.a.pairing.create_offer()
        reply = json.loads(self.b.pairing.accept_offer(offer))
        reply['expires_at'] -= 1
        with self.assertRaisesRegex(ConnectError, 'transcript_mismatch'):
            self.a.pairing.receive_reply(canonical(reply))

    def test_changed_key_and_metadata_do_not_inherit_trust(self):
        record, _ = self.pair()
        changed = public_identity(self.b.local_id, Ed25519PrivateKey.generate(), self.now)
        with self.assertRaisesRegex(ConnectError, 'identity_mismatch'):
            self.a.require_paired_identity(changed)
        self.a.rename(record['device_id'], 'same user same hostname same IP')
        with self.assertRaises(ConnectError):
            self.a.require_paired_identity(changed)

    def test_revocation_and_duplicate_completion(self):
        record, _ = self.pair()
        self.assertEqual(self.a.pairing.complete(self.sid), record)
        with self.assertRaises(ConnectError):
            self.a.pairing.exchange(self.sid)
        self.a.revoke(record['device_id'])
        with self.assertRaises(ConnectError):
            self.a.require_paired_identity(record['public_identity'])
        with self.assertRaises(ConnectError):
            self.a.pairing.complete(self.sid)
        with self.assertRaises(ConnectError):
            self.start()

    def test_no_secrets_in_db_audit_payload_or_logs(self):
        with self.assertNoLogs(level='DEBUG'):
            offer, reply = self.start()
        ordinary = self.a.repository.path.read_bytes() + self.b.repository.path.read_bytes()
        ordinary += canonical(self.a.repository.activity()) + offer + reply
        for vault in self.vaults:
            encoded = vault.values[KEY_REFERENCE]
            self.assertFalse(encoded.encode() in ordinary)
            self.assertFalse(base64.b64decode(encoded[10:]) in ordinary)
        self.assertFalse(b'PRIVATE KEY' in ordinary)
        self.assertFalse(b'certificate' in canonical(self.a.repository.activity()))

    def test_no_socket_or_private_key_file_and_shutdown_cleanup(self):
        with patch('socket.socket', side_effect=AssertionError('socket forbidden')):
            self.pair()
        self.a.close()
        self.assertEqual(self.a.pairing._sessions, {})
        self.assertEqual(sorted(p.name for p in (self.root / '0' / 'connect').iterdir()), ['devices.sqlite3'])


    def test_closed_pairing_cannot_provision_a_key(self):
        self.a.close()
        with self.assertRaisesRegex(ConnectError, 'pairing_closed'):
            self.a.pairing.create_offer()
        self.assertEqual(self.vaults[0].writes, 0)

    def test_orphaned_vault_key_is_never_overwritten(self):
        self.vaults[0].values[KEY_REFERENCE] = 'existing fixture slot'
        with self.assertRaises(ConnectError):
            self.a.cryptographic_identity()
        self.assertEqual(self.vaults[0].writes, 0)

    def test_fingerprint_is_stable_public_and_versioned(self):
        public = self.a.cryptographic_identity()
        self.assertTrue(fingerprint(public).startswith('C2/1:'))
        self.assertEqual(fingerprint(public), fingerprint(json.loads(json.dumps(public))))
        changed = dict(public, key_version=2)
        with self.assertRaises(ConnectError):
            fingerprint(changed)

    def test_same_display_name_does_not_pair(self):
        self.a.rename(self.a.local_id, 'same user')
        self.b.rename(self.b.local_id, 'same user')
        self.start()
        self.assertEqual(self.a.paired_devices(), [])
        self.assertEqual(self.b.paired_devices(), [])

    def test_completion_is_idempotent_after_restart(self):
        record, _ = self.pair()
        self.a.close()
        self.a = DesktopDeviceService(self.root / '0', key_store=DeviceKeyStore(self.vaults[0]))
        self.assertEqual(self.a.pairing.complete(self.sid), record)
        with self.assertRaises(ConnectError):
            self.a.pairing.exchange(self.sid)

    def test_changed_duplicate_completion_rejected(self):
        self.pair()
        with self.assertRaisesRegex(ConnectError, 'changed_duplicate'):
            self.a.pairing.complete(self.sid, name='Changed request')

    def test_permission_allow_cannot_enable_unsupported_or_bypass_authentication(self):
        from dataclasses import asdict
        from olive.connect.contracts import RequestEnvelope, PROTOCOL
        import uuid
        peer, _ = self.pair()
        self.a.set_permission(peer['device_id'], 'terminal', 'allow')
        req = RequestEnvelope(str(uuid.uuid4()), PROTOCOL, peer['device_id'], self.a.local_id,
                              'terminal', 'run', {}, self.now, self.now + 60)
        result = self.a.receive_fixture(canonical(asdict(req)), peer_device_id=peer['device_id'])
        self.assertEqual(result['error'], 'unauthenticated_transport')
        self.assertFalse(next(x for x in self.a.capabilities() if x['capability'] == 'terminal')['supported'])

    def test_expiry_after_confirmation_cannot_complete(self):
        self.start()
        comparison = self.a.pairing.preview(self.sid)['comparison']
        self.a.pairing.confirm(self.sid, comparison)
        self.b.pairing.confirm(self.sid, comparison)
        self.pump()
        self.now += 120
        with self.assertRaisesRegex(ConnectError, 'expired'):
            self.a.pairing.complete(self.sid)
        self.assertEqual(self.a.paired_devices(), [])

    def test_tls_corrupted_message_is_not_confirmation(self):
        self.start()
        self.a.pairing.confirm(self.sid, self.b.pairing.preview(self.sid)['comparison'])
        outgoing = bytearray(self.a.pairing.exchange(self.sid))
        outgoing[-1] ^= 1
        with self.assertRaisesRegex(ConnectError, 'authentication_failed'):
            self.b.pairing.exchange(self.sid, bytes(outgoing))
        self.assertEqual(self.b.paired_devices(), [])

    def test_tls_record_replay_fails(self):
        self.start()
        self.a.pairing.confirm(self.sid, self.b.pairing.preview(self.sid)['comparison'])
        outgoing = self.a.pairing.exchange(self.sid)
        self.b.pairing.exchange(self.sid, outgoing)
        with self.assertRaisesRegex(ConnectError, 'authentication_failed'):
            self.b.pairing.exchange(self.sid, outgoing)

    def test_oversized_handshake_clears_session(self):
        self.start()
        with self.assertRaises(ConnectError):
            self.a.pairing.exchange(self.sid, b'x' * 32769)
        self.assertIsNone(self.a.pairing._sessions[self.sid]['tls'])

    def test_c1_schema_migration_preserves_records(self):
        original = self.a.this_device()
        with self.a.repository.transaction() as db:
            db.execute('DROP TABLE connect_keys')
            db.execute('DROP TABLE pairing_ledger')
            db.execute('PRAGMA user_version=1')
        from olive.connect.repository import DeviceRepository
        repo = DeviceRepository(self.a.repository.path)
        with repo.transaction() as db:
            self.assertEqual(repo.get(db, self.a.local_id), original)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_revoked_key_with_new_id_is_rejected(self):
        record, _ = self.pair()
        self.a.revoke(record['device_id'])
        key = self.b.identities.key_store.load(self.b.cryptographic_identity())
        import uuid
        alias = public_identity(str(uuid.uuid4()), key, self.now)
        with self.assertRaisesRegex(ConnectError, 'device_revoked'):
            self.a.pairing._check_candidate(alias)

    def test_split_mitm_handshakes_produce_different_comparison_values(self):
        attackers = [DesktopDeviceService(self.root / name, key_store=DeviceKeyStore(MemoryVault()),
                     clock=lambda:self.now) for name in ('attacker-one', 'attacker-two')]
        try:
            ids = []
            for honest, attacker in zip((self.a, self.b), attackers):
                offer = honest.pairing.create_offer()
                sid = json.loads(offer)['session_id']
                ids.append(sid)
                honest.pairing.receive_reply(attacker.pairing.accept_offer(offer))
                pending = b''
                for _ in range(8):
                    pending = honest.pairing.exchange(sid, attacker.pairing.exchange(sid, pending))
            first = self.a.pairing.preview(ids[0])['comparison']
            second = self.b.pairing.preview(ids[1])['comparison']
            self.assertNotEqual(first, second)
            with self.assertRaisesRegex(ConnectError, 'comparison_mismatch'):
                self.a.pairing.confirm(ids[0], second)
            with self.assertRaisesRegex(ConnectError, 'comparison_mismatch'):
                self.b.pairing.confirm(ids[1], first)
            self.assertEqual(self.a.paired_devices(), [])
            self.assertEqual(self.b.paired_devices(), [])
        finally:
            for attacker in attackers:
                attacker.close()

    def test_expire_and_shutdown_clear_unfinished_sessions(self):
        self.start()
        self.ticks += 121
        self.a.pairing.expire()
        self.assertEqual(self.a.pairing._sessions[self.sid]['state'], 'expired')
        self.assertIsNone(self.a.pairing._sessions[self.sid]['tls'])
        self.b.close()
        self.assertEqual(self.b.pairing._sessions, {})
        self.assertEqual(self.b.paired_devices(), [])

    def test_linux_vault_slot_absence_locked_and_duplicate_are_distinct(self):
        from contextlib import contextmanager
        from unittest.mock import MagicMock
        from olive.services.linux_credentials import operate
        from olive.platform_support import PlatformUnavailable
        store = MagicMock()
        @contextmanager
        def collection():
            yield store
        with patch('olive.services.linux_credentials.collection', collection):
            store.search_items.return_value = []
            self.assertFalse(operate('contains', 'fixture'))
            item = MagicMock()
            item.is_locked.return_value = False
            store.search_items.return_value = [item]
            self.assertTrue(operate('contains', 'fixture'))
            item.is_locked.return_value = True
            with self.assertRaises(PlatformUnavailable):
                operate('contains', 'fixture')
            store.search_items.return_value = [item, item]
            with self.assertRaises(PlatformUnavailable):
                operate('contains', 'fixture')

    def test_windows_vault_contract_preserved(self):
        from unittest.mock import MagicMock
        from olive.services.credential_vault import CredentialVault
        win = MagicMock()
        win.CRED_TYPE_GENERIC = 1
        win.CRED_PERSIST_LOCAL_MACHINE = 2
        with patch('sys.platform', 'win32'), patch.dict('sys.modules', {'win32cred': win}):
            vault = CredentialVault(self.root / 'windows')
            self.assertTrue(vault.namespace.startswith('DMDO/'))
            missing = OSError('not found')
            missing.winerror = 1168
            win.CredRead.side_effect = missing
            self.assertFalse(vault.contains(KEY_REFERENCE))
            store = DeviceKeyStore(vault)
            key = Ed25519PrivateKey.generate()
            public = public_identity(self.a.local_id, key, self.now)
            store.create(key)
            written = win.CredWrite.call_args.args[0]
            self.assertEqual(written['TargetName'], vault._target(KEY_REFERENCE))
            win.CredRead.side_effect = None
            win.CredRead.return_value = {'CredentialBlob': written['CredentialBlob'].encode('utf-16-le'),
                                        'Comment': written['Comment']}
            self.assertTrue(vault.contains(KEY_REFERENCE))
            self.assertTrue(store.load(public).public_key() == key.public_key())
            win.CredRead.side_effect = OSError('unavailable')
            with self.assertRaises(RuntimeError):
                vault.contains(KEY_REFERENCE)


if __name__ == '__main__':
    unittest.main()
