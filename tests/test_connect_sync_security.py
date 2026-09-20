"""Trusted Ask, execution-time denial, interruption and bounded sync wire tests."""
import asyncio
from dataclasses import asdict
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from olive.bridge.host import Host
from olive.connect.approvals import ConnectApprovals
from olive.connect.contracts import ConnectError, canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.personal.service import PersonalService
from olive.sync.records import SyncRequest, PROTOCOL
from tests.test_connect_network import pair
from tests.test_connect_pairing import MemoryVault


class SyncApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.services = []
        for i in range(2):
            path = Path(self.temp.name)/str(i)
            s = DesktopDeviceService(path,key_store=DeviceKeyStore(MemoryVault()))
            s.attach_sync(PersonalService(path/'personal.sqlite3')); self.services.append(s)
        self.a,self.b = self.services; pair(self.a,self.b)
        self.host = Host(lambda _:None); self.host.activity=lambda:None
        self.b.approvals = ConnectApprovals(self.b,self.host.confirm,asyncio.get_running_loop())
        self.a.enable_network('127.0.0.1',discovery=False); self.b.enable_network('127.0.0.1',discovery=False)
        self.channel = await asyncio.to_thread(self.a.network.connect,self.b.local_id,'127.0.0.1',self.b.network.port)
        self.b.set_permission(self.a.local_id,'sync.tasks','ask')
        task = self.a.sync.store.personal.save('task',{'title':'Ask task'})
        with self.a.sync.store.native.transaction() as db:
            self.a.sync.store.capture(db); self.record=self.a.sync.store.current(db,task['id']).value()

    async def asyncTearDown(self):
        for s in self.services: await asyncio.to_thread(s.close)
        self.temp.cleanup()

    def request(self):
        now=int(time.time())
        return asdict(SyncRequest(PROTOCOL,str(uuid.uuid4()),self.a.local_id,self.b.local_id,self.a.local_id,
                                  'sync.tasks','exchange',dict(records=[self.record],cursor=0),now,now+90))

    async def send(self,value):
        return await asyncio.to_thread(self.channel.sync_request,canonical(value))

    async def approve(self):
        for _ in range(100):
            if self.host.pending:break
            await asyncio.sleep(.01)
        self.assertTrue(self.host.pending)
        value,_=next(iter(self.host.pending.values()))
        self.assertEqual(value['arguments']['capability'],'sync.tasks')
        await self.host.execute('approval.respond',dict(approval_id=value['id'],fingerprint=value['fingerprint'],approved=True))
        await asyncio.sleep(.02)

    async def test_exact_scope_approval_policy_change_and_no_remote_approval(self):
        request=self.request()
        self.assertEqual((await self.send(request))['error'],'confirmation_required')
        with self.assertRaises(LookupError): self.b.sync.store.personal.get('task',self.record['record_id'])
        await self.approve()
        response = await self.send(request)
        self.assertEqual(response['state'], 'completed')
        self.b.sync.store.personal.save('task', {'title': 'Created after approved response'})
        self.assertEqual(await self.send(request), response)
        self.assertEqual(self.b.permission(self.a.local_id,'sync.tasks').value,'ask')
        with self.assertRaises(ConnectError): await self.send({**request,'approved':True})
        self.b.set_permission(self.a.local_id,'sync.tasks','deny')
        self.assertEqual((await self.send(request))['error'],'permission_off')
        self.b.set_permission(self.a.local_id,'sync.tasks','ask')
        changed=self.request()
        self.assertEqual((await self.send(changed))['error'],'confirmation_required')
        await self.approve()
        changed['arguments']['cursor']=1
        self.assertEqual((await self.send(changed))['error'],'approval_changed_request')

    async def test_cancel_awaiting_approval_and_resume_after_permission(self):
        self.a.set_permission(self.b.local_id,'sync.tasks','allow')
        self.a.sync.start(self.b.local_id)
        for _ in range(150):
            if self.a.sync.status()['state']=='awaiting_approval': break
            await asyncio.sleep(.01)
        self.assertEqual(self.a.sync.status()['state'],'awaiting_approval')
        self.a.sync.cancel(); await asyncio.to_thread(self.a.sync.worker.join,6)
        self.assertEqual(self.a.sync.status()['state'],'cancelled')
        self.b.set_permission(self.a.local_id,'sync.tasks','allow')
        self.a.sync.start(self.b.local_id); await asyncio.to_thread(self.a.sync.worker.join,6)
        self.assertEqual(self.a.sync.status()['state'],'completed')
        self.assertEqual(self.b.sync.store.personal.get('task',self.record['record_id'])['title'],'Ask task')

    async def test_drop_after_commit_before_ack_is_idempotent(self):
        self.b.set_permission(self.a.local_id,'sync.tasks','allow')
        original=self.b.sync.receive
        def drop(raw,peer,public):
            response=original(raw,peer,public)
            self.b.network.channels[peer].close()
            return response
        request=self.request()
        with patch.object(self.b.sync,'receive',drop):
            with self.assertRaises(ConnectError): await self.send(request)
        self.assertEqual(self.b.sync.store.personal.get('task',self.record['record_id'])['title'],'Ask task')
        await asyncio.sleep(.1)
        self.channel=await asyncio.to_thread(self.a.network.connect,self.b.local_id,'127.0.0.1',self.b.network.port)
        self.assertEqual((await self.send(request))['result']['results'],['duplicate'])
        self.assertEqual(len(self.b.sync.store.personal.search('task')['items']),1)
