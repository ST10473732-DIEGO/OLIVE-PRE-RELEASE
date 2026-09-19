"""C4 facade + trusted Host approval, using real C2 identities and C3 sockets."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from olive.bridge.contracts import validate
from olive.bridge.host import Host
from olive.connect.approvals import ConnectApprovals
from olive.connect.contracts import ConnectError, canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.connect.workspace import DevicesWorkspace
from tests.test_connect_network import pair, request
from tests.test_connect_pairing import MemoryVault


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.a = DesktopDeviceService(Path(self.temp.name)/'a', key_store=DeviceKeyStore(MemoryVault()))
        self.b = DesktopDeviceService(Path(self.temp.name)/'b', key_store=DeviceKeyStore(MemoryVault()))
        self.ui = DevicesWorkspace(self.a)

    def tearDown(self):
        self.a.close(); self.b.close(); self.temp.cleanup()

    def test_off_identity_rename_snapshot_privacy_and_unavailable(self):
        self.assertIsNone(self.a.network)
        public = self.a.cryptographic_identity()
        first = self.ui.snapshot()
        self.a.rename(self.a.local_id, 'Test desktop')
        after = self.ui.snapshot()
        self.assertEqual(after['local']['fingerprint'], first['local']['fingerprint'])
        self.assertEqual(public['device_id'], after['local']['device_id'])
        pair(self.a, self.b)
        with self.assertRaisesRegex(ConnectError, 'capability_unavailable'):
            self.ui.permission(self.b.local_id, 'terminal', 'allow')
        self.assertEqual(self.a.device(self.b.local_id)['permissions'], [])
        payload = json.dumps(self.ui.snapshot())
        for secret in ('certificate_der', 'private_key', 'vault', 'comparison'):
            self.assertNotIn(secret, payload)

    def test_real_interface_enable_disable_and_failed(self):
        self.assertEqual(self.ui.enable('0.0.0.0', False)['network']['state'], 'failed')
        value = self.ui.enable('127.0.0.1', False)
        self.assertEqual(value['network']['state'], 'on')
        self.assertGreater(value['network']['port'], 0)
        self.assertEqual(self.ui.disable()['network']['state'], 'off')
        self.assertIsNone(self.a.network)

    def test_pairing_offer_expiry_new_session_and_mismatch(self):
        state = self.ui.create_pairing()
        raw = state['offer'].encode()
        sid = state['session_id']
        self.a.pairing.receive_reply(self.b.pairing.accept_offer(raw))
        pending = b''
        for _ in range(8):
            pending = self.a.pairing.exchange(sid, self.b.pairing.exchange(sid, pending))
        preview = self.ui.pairing_status(sid)
        self.assertEqual(preview['comparison'], self.b.pairing.preview(sid)['comparison'])
        self.assertNotIn('candidate', preview)
        with self.assertRaisesRegex(ConnectError, 'comparison_mismatch'):
            self.ui.confirm_pairing(sid, 'wrong observed value')
        self.assertEqual(self.ui.pairing_status(sid)['state'], 'failed')
        self.assertEqual(self.a.paired_devices(), [])
        new = self.ui.create_pairing()
        self.assertNotEqual(new['session_id'], sid)
        with patch.object(self.a.pairing, 'clock', return_value=new['expires_at']):
            expired = self.ui.pairing_status(new['session_id'])
        self.assertEqual(expired['state'], 'expired')
        self.assertNotIn('offer', expired)

    def test_restart_remains_off_and_shutdown_serializes_enable(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from olive.connect.network import LocalNetwork
        entered, release = threading.Event(), threading.Event()
        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test release timed out')
            return LocalNetwork(*args, **kwargs)
        with patch('olive.connect.network.LocalNetwork', side_effect=delayed):
            with ThreadPoolExecutor() as pool:
                enabling = pool.submit(self.a.enable_network, '127.0.0.1', discovery=False)
                self.assertTrue(entered.wait(2))
                closing = pool.submit(self.a.close)
                self.assertFalse(closing.done())
                release.set()
                enabling.result(timeout=5)
                closing.result(timeout=5)
        self.assertIsNone(self.a.network)
        self.a = DesktopDeviceService(Path(self.temp.name)/'a', key_store=DeviceKeyStore(MemoryVault()))
        self.assertIsNone(self.a.network)
        self.assertEqual(DevicesWorkspace(self.a).snapshot()['network']['state'], 'off')

    def test_strict_bridge_rejects_remote_authority(self):
        base = dict(v=1, id='c4', method='connect.enable', args=dict(address='127.0.0.1', discovery=False))
        validate(base)
        for key in ('approved', 'confirmed', 'allow', 'remember', 'private_key'):
            with self.assertRaises(ValueError):
                validate({**base, 'args': {**base['args'], key: True}})


class ApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.a, self.b = [DesktopDeviceService(Path(self.temp.name)/name,
            key_store=DeviceKeyStore(MemoryVault())) for name in ('a','b')]
        pair(self.a,self.b)
        self.host = Host(lambda _: None)
        # Exercise the actual pending registry/fingerprint/respond path.
        self.host.activity = lambda: None
        self.b.approvals = ConnectApprovals(self.b, self.host.confirm, asyncio.get_running_loop())
        self.na = self.a.enable_network('127.0.0.1', discovery=False)
        self.nb = self.b.enable_network('127.0.0.1', discovery=False)
        self.channel = await asyncio.to_thread(self.na.connect,self.b.local_id,'127.0.0.1',self.nb.port)
        self.b.set_permission(self.a.local_id,'connect.ping','ask')

    async def asyncTearDown(self):
        await asyncio.to_thread(self.a.close)
        await asyncio.to_thread(self.b.close)
        await asyncio.sleep(0)
        self.temp.cleanup()

    async def send(self, value):
        return await asyncio.to_thread(self.channel.request, canonical(value))

    async def answer(self, approved):
        for _ in range(100):
            if self.host.pending: break
            await asyncio.sleep(.01)
        self.assertTrue(self.host.pending)
        value, _ = next(iter(self.host.pending.values()))
        await self.host.execute('approval.respond', dict(approval_id=value['id'],fingerprint=value['fingerprint'],approved=approved))
        for _ in range(100):
            if not self.host.pending: break
            await asyncio.sleep(.01)

    async def test_deny_allow_once_exact_retry_and_revocation(self):
        value = request(self.a,self.b)
        self.assertEqual((await self.send(value))['error'], 'confirmation_required')
        await self.answer(False)
        self.assertEqual((await self.send(value))['error'], 'request_denied')
        value = request(self.a,self.b)
        self.assertEqual((await self.send(value))['error'], 'confirmation_required')
        await self.answer(True)
        response = await self.send(value)
        self.assertEqual(response['state'], 'completed')
        self.assertEqual(await self.send(value),response)
        self.assertEqual(self.b.permission(self.a.local_id,'connect.ping').value,'ask')
        self.assertIsNotNone(self.na.status(self.b.local_id)['latency_ms'])
        await asyncio.to_thread(self.b.revoke,self.a.local_id)
        self.assertFalse(self.nb.status(self.a.local_id)['encrypted'])
        self.assertIsNone(self.nb.status(self.a.local_id)['latency_ms'])
        self.assertTrue(any(e['result_state']=='request_approved' for e in self.b.repository.activity()))

    async def test_changed_request_cannot_use_approval(self):
        value=request(self.a,self.b)
        await self.send(value)
        await self.answer(True)
        self.assertEqual((await self.send({**value,'arguments':{'nonce':'changed'}}))['error'],'approval_changed_request')
        self.assertEqual((await self.send(value))['error'],'request_denied')

    async def test_permission_revision_invalidates_approval_and_remote_flags_rejected(self):
        value=request(self.a,self.b)
        await self.send(value)
        await self.answer(True)
        self.b.set_permission(self.a.local_id,'connect.ping','deny')
        self.assertEqual((await self.send(value))['error'],'permission_off')
        with self.assertRaisesRegex(ConnectError, 'invalid_envelope_fields'):
            await self.send({**value,'approved':True})

    async def test_snapshot_does_not_exhaust_action_deduplication_budget(self):
        from types import SimpleNamespace
        self.host.services = SimpleNamespace(connect=self.b)
        self.host.requests.update({str(i): (None, None) for i in range(2048)})
        value = await self.host.handle(dict(v=1,id='snapshot',method='connect.snapshot',args={}))
        self.assertEqual(value['local']['device_id'],self.b.local_id)
        self.assertEqual(len(self.host.requests),2048)
        with self.assertRaisesRegex(RuntimeError,'history is full'):
            await self.host.handle(dict(v=1,id='mutate',method='connect.rename',args={'name':'new'}))
        self.host.requests.clear()

    async def test_revocation_cancels_pending_local_approval(self):
        value=request(self.a,self.b)
        await self.send(value)
        for _ in range(100):
            if self.host.pending:break
            await asyncio.sleep(.01)
        self.assertTrue(self.host.pending)
        await asyncio.to_thread(self.b.revoke,self.a.local_id)
        for _ in range(100):
            if not self.host.pending:break
            await asyncio.sleep(.01)
        self.assertFalse(self.host.pending)
        self.assertEqual(self.b.device(self.a.local_id)['trust_state'],'revoked')

    async def test_disabling_cancels_pending_approval_and_clears_latency(self):
        await self.send(request(self.a,self.b))
        await asyncio.sleep(.02)
        self.assertTrue(self.host.pending)
        await asyncio.to_thread(self.b.disable_network)
        await asyncio.sleep(.02)
        self.assertFalse(self.host.pending)
        self.assertIsNone(self.b.network)
        self.assertEqual(DevicesWorkspace(self.b).snapshot()['network']['state'],'off')

    async def test_ui_ping_retries_the_same_pending_request_after_approval(self):
        workspace = DevicesWorkspace(self.a)
        first = await asyncio.to_thread(workspace.ping, self.b.local_id)
        self.assertEqual(first['error'], 'confirmation_required')
        await self.answer(True)
        second = await asyncio.to_thread(workspace.ping, self.b.local_id)
        self.assertEqual(first['request_id'], second['request_id'])
        self.assertEqual(second['state'], 'completed')
        self.assertEqual(self.b.permission(self.a.local_id, 'connect.ping').value, 'ask')
        third = await asyncio.to_thread(workspace.ping, self.b.local_id)
        self.assertNotEqual(third['request_id'], first['request_id'])
        self.assertEqual(third['error'], 'confirmation_required')
