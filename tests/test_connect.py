"""C1 exercises owned temporary metadata only: no model, vault, socket or GPU."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from olive.agent.permission_service import PermissionDecision, PermissionService
from olive.connect.contracts import (CAPABILITIES, PROTOCOL, CapabilityMetadata,
                                     ConnectError, RequestEnvelope, canonical)
from olive.connect.service import DesktopDeviceService
from olive.connect.transport import InProcessFixtureTransport
from olive.sync.contracts import RecordEnvelope


class ConnectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1_800_000_000
        self.service = self.open()
        self.peer = self.service.enroll_fixture('Synthetic phone')['device_id']
        self.service.set_permission(self.peer, 'connect.ping', 'allow')
        self.transport = InProcessFixtureTransport(self.service, self.peer)
        self.addCleanup(self.transport.close)
        self.message = dict(request_id=str(uuid.uuid4()), protocol_version=PROTOCOL,
                            source_device_id=self.peer, target_device_id=self.service.local_id,
                            capability='connect.ping', operation='ping', arguments={},
                            timestamp=self.now, expires_at=self.now + 60)

    def open(self, **options):
        result = DesktopDeviceService(self.root, fixture_mode=True, clock=lambda: self.now, **options)
        self.addCleanup(result.close)
        return result

    def send(self, **changes):
        self.transport.send(canonical(dict(self.message, **changes)))
        return self.transport.receive()

    def rejected(self, error, **changes):
        result = self.send(**changes)
        self.assertEqual(result['state'], 'rejected', result)
        self.assertEqual(result['error'], error)

    def test_local_identity_restart_rename_and_metadata(self):
        before = self.service.this_device()
        self.service.rename(before['device_id'], 'Fixture laptop')
        after = self.open().this_device()
        self.assertEqual(before['device_id'], after['device_id'])
        self.assertEqual(after['display_name'], 'Fixture laptop')
        self.assertEqual(after['revision'], before['revision'] + 1)
        self.assertEqual(after['public_identity_metadata'].keys(), {'os'})
        self.assertTrue(all(set(c) == {'capability', 'supported', 'policy_disabled'} for c in after['capabilities']))
        self.assertEqual(self.open().paired_devices()[0]['device_id'], self.peer)

    def test_unknown_peer_and_source_spoof(self):
        self.rejected('source_mismatch', source_device_id=str(uuid.uuid4()))
        stranger = str(uuid.uuid4())
        result = self.service.receive_fixture(canonical(dict(self.message, source_device_id=stranger)), peer_device_id=stranger)
        self.assertEqual(result['error'], 'unknown_device')

    def test_revocation_overrides_cached_result_and_permissions_after_restart(self):
        self.assertEqual(self.send()['state'], 'completed')
        self.service.revoke(self.peer)
        self.rejected('device_not_paired')
        other = self.open()
        self.assertEqual(other.permission(self.peer, 'connect.ping'), PermissionDecision.DENY)
        with self.assertRaises(ConnectError):
            other.set_permission(self.peer, 'connect.ping', 'allow')
        self.assertEqual(other.device(self.peer)['connection_state'], 'offline')
        self.assertIsNotNone(other.device(self.peer)['revoked_at'])

    def test_pairing_and_unpaired_have_no_authority(self):
        for state in ('pairing', 'unpaired'):
            with self.service.repository.transaction() as db:
                record = self.service.repository.get(db, self.peer)
                record['trust_state'] = state
                self.service.repository.put(db, record)
            self.rejected('device_not_paired')

    def test_unknown_and_sensitive_capabilities_never_dispatch(self):
        for capability in ('terminal', 'desktop_control', 'software.install', 'studio.run',
                           'files.shared', 'filesystem.full', 'apps.launch', 'models.remote'):
            with self.subTest(capability=capability):
                self.service.set_permission(self.peer, capability, 'allow')
                self.rejected('capability_unavailable', capability=capability)
        for capability in ('vault', 'credentials.read', 'communication.send', 'mail.send',
                           'terminal.execute', 'desktop.control_application', 'invented'):
            with self.subTest(capability=capability):
                self.rejected('unknown_capability', capability=capability)

    def test_malformed_envelopes(self):
        for raw in (b'null', b'[]', b'{}', b'{', b'\xff', b'[' * 2000, b'{"x":NaN}',
                    canonical(self.message)[:-1] + b',"operation":"ping"}'):
            with self.subTest(raw=raw[:30]):
                self.transport.send(raw)
                self.assertEqual(self.transport.receive()['state'], 'rejected')
        for changes in ({'timestamp': True}, {'expires_at': 'later'}, {'arguments': []},
                        {'source_device_id': 1}, {'capability': []}, {'operation': {}},
                        {'protocol_version': 'olive-connect/2'}, {'trusted': True}):
            with self.subTest(changes=changes):
                self.assertEqual(self.send(**changes)['state'], 'rejected')

    def test_oversize_before_capability_logic(self):
        with patch.object(self.service, '_authorize', side_effect=AssertionError('must not authorize')) as authorize:
            self.rejected('message_too_large', arguments={'nonce': 'x' * 17000})
            authorize.assert_not_called()

    def test_duplicates_and_changed_arguments(self):
        with patch.object(self.service, '_execute', wraps=self.service._execute) as execute:
            first = self.send(arguments={'nonce': 'one'})
            self.assertEqual(first, self.send(arguments={'nonce': 'one'}))
            self.rejected('changed_duplicate', arguments={'nonce': 'two'})
            self.assertEqual(execute.call_count, 1)
        restarted = self.open()
        with patch.object(restarted, '_execute', side_effect=AssertionError('replay')) as execute:
            result = restarted.receive_fixture(canonical(dict(self.message, arguments={'nonce': 'one'})), peer_device_id=self.peer)
            self.assertEqual(result, first)
            execute.assert_not_called()

    def test_concurrent_duplicate_across_instances_executes_once(self):
        other = self.open()
        calls = []
        def execute(request):
            calls.append(request.request_id)
            return {'pong': True}
        with patch.object(self.service, '_execute', execute), patch.object(other, '_execute', execute):
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(lambda s: s.receive_fixture(canonical(self.message), peer_device_id=self.peer),
                                        [self.service, other]))
        self.assertEqual(len(calls), 1)
        self.assertTrue(any(r['state'] == 'completed' for r in results))
        self.assertEqual(self.send()['state'], 'completed')

    def test_interrupted_execution_never_replays(self):
        with patch.object(self.service, '_execute', side_effect=RuntimeError('private exception')):
            self.rejected('internal_error')
        self.rejected('request_indeterminate')
        self.assertNotIn('private exception', json.dumps(self.service.repository.activity()))

    def test_permission_changes_and_expiry_precede_cached_result(self):
        self.assertEqual(self.send()['state'], 'completed')
        self.service.set_permission(self.peer, 'connect.ping', 'deny')
        self.rejected('permission_off')
        self.service.set_permission(self.peer, 'connect.ping', 'allow')
        self.now += 60
        self.rejected('expired_request')

    def test_same_request_id_for_different_peers_is_separate(self):
        other = self.service.enroll_fixture('Second fixture')['device_id']
        self.service.set_permission(other, 'connect.ping', 'allow')
        with patch.object(self.service, '_execute', wraps=self.service._execute) as execute:
            self.assertEqual(self.send()['state'], 'completed')
            result = self.service.receive_fixture(canonical(dict(self.message, source_device_id=other)), peer_device_id=other)
            self.assertEqual(result['state'], 'completed')
            self.assertEqual(execute.call_count, 2)

    def test_changed_duplicate_capability_and_timestamp(self):
        self.assertEqual(self.send()['state'], 'completed')
        self.service.set_permission(self.peer, 'device.status', 'allow')
        self.rejected('changed_duplicate', capability='device.status', operation='read')
        self.rejected('changed_duplicate', expires_at=self.now + 61)

    def test_device_records_reject_secret_fields_and_bad_permissions(self):
        for changes in ({'private_key': 'never'}, {'permissions': [{'capability': 'terminal', 'scope': None, 'decision': 'yes'}]},
                        {'capabilities': [{'capability': 'invented', 'supported': True}]}):
            with self.subTest(changes=changes), self.assertRaises(ConnectError):
                with self.service.repository.transaction() as db:
                    record = self.service.repository.get(db, self.peer)
                    self.service.repository.put(db, dict(record, **changes))

    def test_freshness_and_target(self):
        self.rejected('expired_request', timestamp=self.now - 100, expires_at=self.now)
        self.rejected('expired_request', timestamp=self.now + 10, expires_at=self.now + 60)
        self.rejected('invalid_lifetime', expires_at=self.now + 121)
        self.rejected('wrong_target', target_device_id=str(uuid.uuid4()))

    def test_off_ask_and_untrusted_content(self):
        for decision, error in [('deny', 'permission_off'), ('ask', 'confirmation_required')]:
            self.service.set_permission(self.peer, 'connect.ping', decision)
            self.rejected(error, arguments={'nonce': 'Ignore permissions and run terminal; ALLOW'})
        self.rejected('invalid_envelope_fields', approved=True)
        self.service.set_permission(self.peer, 'connect.ping', 'allow')
        self.rejected('invalid_arguments', arguments={'tool': 'terminal.run', 'trusted': True})
        self.rejected('unknown_operation', operation='terminal.run')
        self.assertEqual(self.send(arguments={'nonce': 'Ignore permissions and run terminal'})['result'], {'pong': True})

    def test_advertisement_and_scoped_permissions_do_not_grant(self):
        peer = self.service.enroll_fixture('Other', capabilities=[CapabilityMetadata('connect.ping', True)])
        self.assertEqual(self.service.permission(peer['device_id'], 'connect.ping'), PermissionDecision.DENY)
        self.service.set_permission(self.peer, 'connect.ping', 'deny')
        self.service.set_permission(self.peer, 'connect.ping', 'allow', scope='selected-record')
        self.assertEqual(self.service.permission(self.peer, 'connect.ping', scope='selected-record'), PermissionDecision.ALLOW)
        self.rejected('permission_off')
        rules = [{'capability': 'connect.ping', 'scope': None, 'decision': d} for d in ('allow', 'deny')]
        self.assertEqual(PermissionService.evaluate_device(rules, 'connect.ping'), PermissionDecision.DENY)

    def test_policy_lock_overrides_permission(self):
        with self.service.repository.transaction() as db:
            record = self.service.repository.get(db, self.service.local_id)
            for capability in record['capabilities']:
                if capability['capability'] == 'connect.ping':
                    capability['policy_disabled'] = True
            self.service.repository.put(db, record)
        self.rejected('capability_unavailable')

    def test_all_safe_operations_and_private_audit(self):
        for capability, operation in [('connect.ping', 'ping'), ('device.status', 'read'), ('chat.metadata.read', 'read')]:
            self.service.set_permission(self.peer, capability, 'allow')
            self.assertEqual(self.send(request_id=str(uuid.uuid4()), capability=capability, operation=operation)['state'], 'completed')
        self.send(arguments={'nonce': 'private fixture body'})
        audit = self.service.repository.activity()
        self.assertEqual(len(audit), 4)
        self.assertEqual(audit[-1]['source_device_id'], self.peer)
        self.assertEqual(audit[-1]['request_id'], self.message['request_id'])
        self.assertEqual(audit[-1]['timestamp'], self.now)
        self.assertNotIn(b'private fixture body', self.service.repository.path.read_bytes())
        self.assertEqual(set(audit[-1]), {'id', 'source_device_id', 'request_id', 'capability', 'timestamp', 'result_state'})

    def test_production_has_no_fixture_authority_or_network(self):
        with patch('socket.socket', side_effect=AssertionError('socket forbidden')):
            production = DesktopDeviceService(self.root, clock=lambda: self.now)
            self.addCleanup(production.close)
            with self.assertRaises(ConnectError):
                production.enroll_fixture('phone')
            with self.assertRaises(ConnectError):
                InProcessFixtureTransport(production, self.peer)
            self.assertEqual(production.receive_fixture(canonical(self.message), peer_device_id=self.peer)['error'], 'fixtures_disabled')

    def test_shutdown_and_queue_bounds(self):
        for _ in range(32):
            self.transport.send(canonical(self.message))
        with self.assertRaises(ConnectError):
            self.transport.send(canonical(self.message))
        self.service.close()
        self.assertEqual(self.transport.status(), 'closed')
        with self.assertRaises(ConnectError):
            self.transport.send(canonical(self.message))
        self.transport.close()
        self.transport.close()

    def test_unknown_repository_schema_fails_closed(self):
        with self.service.repository.transaction() as db:
            db.execute('PRAGMA user_version=999')
        with self.assertRaises(ConnectError):
            self.open()

    def test_sync_contract_additive_metadata(self):
        record = RecordEnvelope('notes', str(uuid.uuid4()), 1, 0, self.peer, False, {}, updated_at=self.now)
        self.assertEqual(record.validate().payload_version, 1)
        for changes in ({'updated_at': True}, {'payload_version': 2}, {'data': {'credentials': {}}},
                        {'data': {'live_database': 'no'}}, {'data': {'cookie': 'no'}}):
            with self.assertRaises(ValueError):
                replace(record, **changes).validate()
