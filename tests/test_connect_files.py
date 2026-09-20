"""Actual C3 file bytes, isolated profiles, portable security boundaries."""
import hashlib
import errno
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from olive.connect.contracts import ConnectError
from olive.connect.file_protocol import FileRequest, PROTOCOL, CHUNK_SIZE, MAX_FILE_SIZE, filename
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import pair, until, request
from olive.connect.contracts import canonical


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.a, self.b, self.c = [DesktopDeviceService(self.root / str(i), key_store=DeviceKeyStore(MemoryVault())) for i in range(3)]
        pair(self.a, self.b)
        self.na = self.a.enable_network('127.0.0.1', discovery=False)
        self.nb = self.b.enable_network('127.0.0.1', discovery=False)
        self.channel = self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)
        until(lambda: self.nb.status(self.a.local_id)['encrypted'])
        self.data = bytes(range(256)) * 1100
        self.path = self.root / 'RaceDay.bin'
        self.path.write_bytes(self.data)
        self.a.set_permission(self.b.local_id, 'files.send', 'allow')

    def tearDown(self):
        for s in (self.a, self.b, self.c): s.close()
        self.temp.cleanup()

    def offer(self):
        now = int(time.time())
        return FileRequest(str(uuid.uuid4()), PROTOCOL, str(uuid.uuid4()), self.a.local_id,
            self.b.local_id, 'offer', dict(name='RaceDay.bin', size=len(self.data),
            sha256=hashlib.sha256(self.data).hexdigest(), mime='application/octet-stream'), now, now + 120)

    def send_request(self, offer, operation, args=None, data=b''):
        from dataclasses import replace
        req = replace(offer, request_id=str(uuid.uuid4()), operation=operation, arguments=args or {})
        return self.channel.file_request(req.encode(data))

    def allow(self): self.b.set_permission(self.a.local_id, 'files.receive', 'allow')

    def diagnostics(self):
        return dict(local=self.na.status(self.b.local_id), remote=self.nb.status(self.a.local_id),
                    channel_failure=self.channel.failure_category,
                    file_io=list(self.a.files.io_failures) + list(self.b.files.io_failures))

    def send_file(self):
        row = self.a.files.prepare(self.b.local_id, self.path)
        self.a.files.start(row['transfer_id'])
        until(lambda: self.a.files.list()[0]['state'] in {'completed','failed','interrupted'}, timeout=15)
        result = self.a.files.list()[0]
        if result['error'] == 'file_io_failed':
            result = {**result, 'test_diagnostics': self.diagnostics()}
        return result

    def test_real_multichunk_export_inert_and_off_default(self):
        self.assertEqual(self.b.permission(self.a.local_id, 'files.receive').value, 'deny')
        offer = self.offer()
        self.assertEqual(self.channel.file_request(offer.encode())['error'], 'permission_off')
        self.assertEqual(self.b.files.list(), [])
        self.allow()
        row = self.send_file()
        self.assertEqual(row['state'], 'completed', row)
        incoming = self.b.files.list()[0]
        artifact = self.b.files.store.path(row['transfer_id'], 'bin')
        self.assertEqual(artifact.read_bytes(), self.data)
        self.assertEqual(incoming['received_size'], len(self.data))
        self.assertNotIn(str(self.path), str(incoming))
        activity = str(self.b.repository.activity())
        for private in (str(self.path), incoming['metadata']['name'], incoming['metadata']['sha256']):
            self.assertNotIn(private, activity)
        self.assertFalse(artifact.stat().st_mode & 0o111)
        saved = self.root / 'saved.bin'
        self.b.files.export(row['transfer_id'], saved)
        self.assertEqual(saved.read_bytes(), self.data)
        with self.assertRaises(FileExistsError): self.b.files.export(row['transfer_id'], saved)
        self.b.revoke(self.a.local_id)
        self.assertEqual(artifact.read_bytes(), self.data)

    def test_tamper_size_ordering_and_duplicate(self):
        self.allow()
        for mode in ('hash', 'early', 'offset', 'overshoot', 'duplicate'):
            offer = self.offer()
            self.assertEqual(self.channel.file_request(offer.encode())['result']['state'], 'accepted')
            if mode == 'hash':
                for offset in range(0, len(self.data), CHUNK_SIZE):
                    self.send_request(offer, 'chunk', {'offset':offset}, b'x' * min(CHUNK_SIZE,len(self.data)-offset))
                answer = self.send_request(offer, 'complete')
            elif mode == 'early': answer = self.send_request(offer, 'complete')
            elif mode == 'offset': answer = self.send_request(offer, 'chunk', {'offset':1}, b'a')
            elif mode == 'overshoot':
                for offset in range(0,len(self.data),CHUNK_SIZE): self.send_request(offer,'chunk',{'offset':offset},self.data[offset:offset+CHUNK_SIZE])
                answer=self.send_request(offer,'chunk',{'offset':len(self.data)},b'a')
            else:
                self.send_request(offer,'chunk',{'offset':0},b'a')
                answer=self.send_request(offer,'chunk',{'offset':0},b'b')
            self.assertEqual(answer['state'], 'rejected', mode)
            self.assertFalse(self.b.files.store.path(offer.transfer_id,'bin').exists())
            self.assertFalse(self.b.files.store.path(offer.transfer_id,'part').exists())

    def test_completed_replay_and_changed_duplicate(self):
        from dataclasses import replace
        self.allow(); offer = self.offer()
        self.channel.file_request(offer.encode())
        for offset in range(0,len(self.data),CHUNK_SIZE): self.send_request(offer,'chunk',{'offset':offset},self.data[offset:offset+CHUNK_SIZE])
        self.send_request(offer,'complete')
        self.assertEqual(self.channel.file_request(offer.encode())['result']['state'],'completed')
        changed=replace(offer,arguments={**offer.arguments,'sha256':'0'*64})
        self.assertEqual(self.channel.file_request(changed.encode())['error'],'changed_duplicate')
        self.assertEqual(len(list(self.b.files.store.directory.glob('*.bin'))),1)

    def test_cancel_permission_and_revocation_between_chunks(self):
        self.allow()
        for mode in ('cancel','permission','revoke'):
            offer=self.offer();self.channel.file_request(offer.encode())
            self.send_request(offer,'chunk',{'offset':0},self.data[:CHUNK_SIZE])
            if mode=='cancel': self.b.files.cancel(offer.transfer_id)
            elif mode=='permission': self.b.set_permission(self.a.local_id,'files.receive','deny')
            else: self.b.revoke(self.a.local_id)
            if mode!='revoke':
                answer=self.send_request(offer,'chunk',{'offset':CHUNK_SIZE},b'x')
                self.assertTrue(answer['state']=='rejected' or answer['result']['state'] in {'cancelled','interrupted'})
            self.assertFalse(self.b.files.store.path(offer.transfer_id,'part').exists())
            self.assertFalse(self.b.files.store.path(offer.transfer_id,'bin').exists())
            if mode=='permission': self.allow()
        until(lambda: not self.na.status(self.b.local_id)['encrypted'])

    def test_disconnect_cleanup_and_clean_retry(self):
        self.allow(); offer=self.offer();self.channel.file_request(offer.encode())
        self.send_request(offer,'chunk',{'offset':0},b'x')
        self.na.disconnect(self.b.local_id)
        until(lambda: self.b.files.list()[0]['state']=='interrupted')
        self.assertFalse(self.b.files.store.path(offer.transfer_id,'part').exists())
        self.channel=self.na.connect(self.b.local_id,'127.0.0.1',self.nb.port)
        self.assertEqual(self.channel.file_request(offer.encode())['result']['state'],'interrupted')
        fresh = self.send_file()
        self.assertNotEqual(fresh['transfer_id'], offer.transfer_id)
        self.assertEqual(fresh['state'], 'completed', fresh)
        self.assertEqual(len(list(self.b.files.store.directory.glob('*.bin'))),1)

    def test_source_change_and_special_files(self):
        self.allow(); row=self.a.files.prepare(self.b.local_id,self.path)
        self.path.write_bytes(b'changed')
        self.a.files.start(row['transfer_id'])
        until(lambda:self.a.files.list()[0]['state']=='failed')
        self.assertEqual(self.b.files.list(),[])
        with self.assertRaises(ConnectError): self.a.files.prepare(self.b.local_id,self.root)
        if hasattr(os,'mkfifo'):
            fifo=self.root/'fifo';os.mkfifo(fifo)
            with self.assertRaises(ConnectError):self.a.files.prepare(self.b.local_id,fifo)

    def test_third_peer_cannot_hijack(self):
        from dataclasses import replace
        self.allow();offer=self.offer();self.channel.file_request(offer.encode())
        pair(self.c,self.b)
        nc=self.c.enable_network('127.0.0.1',discovery=False)
        channel=nc.connect(self.b.local_id,'127.0.0.1',self.nb.port)
        self.assertEqual(self.b.permission(self.c.local_id,'files.receive').value,'deny')
        off=replace(self.offer(),source_device_id=self.c.local_id)
        self.assertEqual(channel.file_request(off.encode())['error'],'permission_off')
        self.b.set_permission(self.c.local_id,'files.receive','allow')
        spoof=replace(offer,source_device_id=self.c.local_id)
        self.assertEqual(channel.file_request(spoof.encode())['error'],'transfer_owner_mismatch')
        self.assertEqual(self.b.files.list()[0]['state'],'accepted')
        self.na.disconnect(self.b.local_id)
        until(lambda:self.b.files.list()[0]['state']=='interrupted')
        takeover=replace(spoof,request_id=str(uuid.uuid4()),operation='chunk',arguments={'offset':0})
        self.assertEqual(channel.file_request(takeover.encode(b'x'))['error'],'transfer_owner_mismatch')

    def test_quota_and_control_responsiveness(self):
        self.allow()
        with patch('olive.connect.file_store.INBOX_QUOTA', 1):
            self.assertEqual(self.channel.file_request(self.offer().encode())['error'],'inbox_quota_exhausted')
        offer=self.offer();self.channel.file_request(offer.encode())
        self.b.set_permission(self.a.local_id,'connect.ping','allow')
        # Permission changes conservatively interrupt accepted transfers.
        self.assertTrue(self.channel.request(canonical(request(self.a,self.b)))['result']['pong'])

    def test_lost_final_ack_and_restart_keep_one_durable_artifact(self):
        self.allow();offer=self.offer();self.channel.file_request(offer.encode())
        for offset in range(0,len(self.data),CHUNK_SIZE):
            self.send_request(offer,'chunk',{'offset':offset},self.data[offset:offset+CHUNK_SIZE])
        original=self.b.files.receive
        def drop(packet,peer,public):
            answer=original(packet,peer,public)
            self.b.network.channels[peer].close()
            return answer
        with patch.object(self.b.files,'receive',drop),self.assertRaises(ConnectError):
            self.send_request(offer,'complete')
        self.na.disconnect(self.b.local_id)
        keys=self.b.identities.key_store
        self.b.close()
        self.b=DesktopDeviceService(self.root/'1',key_store=keys)
        self.nb=self.b.enable_network('127.0.0.1',discovery=False)
        self.channel=self.na.connect(self.b.local_id,'127.0.0.1',self.nb.port)
        self.assertEqual(self.channel.file_request(offer.encode())['result']['state'],'completed')
        self.assertEqual(len(list(self.b.files.store.directory.glob('*.bin'))),1)
        self.b.files.dismiss(offer.transfer_id)
        self.assertEqual(self.channel.file_request(offer.encode())['result']['state'],'dismissed')
        self.assertEqual(len(list(self.b.files.store.directory.glob('*.bin'))),0)

    def test_empty_oversize_and_slow_sender_cleanup(self):
        from dataclasses import replace
        self.allow();self.path.write_bytes(b'')
        self.assertEqual(self.send_file()['state'],'completed')
        with self.path.open('wb') as stream:stream.truncate(MAX_FILE_SIZE+1)
        with self.assertRaises(ConnectError):self.a.files.prepare(self.b.local_id,self.path)
        offer=self.offer()
        with self.assertRaises(ConnectError):replace(offer,arguments={**offer.arguments,'size':MAX_FILE_SIZE+1}).encode()
        with self.assertRaises(ConnectError):replace(offer,arguments={**offer.arguments,'size':True}).encode()
        self.channel.file_request(offer.encode())
        with self.b.files.lock:self.b.files.activity[offer.transfer_id]=(time.monotonic()-50,time.monotonic()-40)
        until(lambda:self.b.files.list()[0]['state']=='interrupted')
        self.assertFalse(self.b.files.store.path(offer.transfer_id,'part').exists())

    def test_active_multichunk_ping_and_permission_abort(self):
        self.allow();self.b.set_permission(self.a.local_id,'connect.ping','allow')
        self.path.write_bytes(bytes(range(256))*32768)
        row=self.a.files.prepare(self.b.local_id,self.path);self.a.files.start(row['transfer_id'])
        until(lambda:bool(self.b.files.list()) and self.b.files.list()[0]['received_size']>0)
        started=time.monotonic()
        self.assertTrue(self.channel.request(canonical(request(self.a,self.b)))['result']['pong'])
        self.assertLess(time.monotonic()-started,2)
        self.b.set_permission(self.a.local_id,'files.receive','deny')
        until(lambda:self.a.files.list()[0]['state'] in {'failed','interrupted'})
        self.assertFalse(self.b.files.store.path(row['transfer_id'],'bin').exists())
        self.assertFalse(self.b.files.store.path(row['transfer_id'],'part').exists())
        self.assertTrue(self.na.status(self.b.local_id)['encrypted'], self.diagnostics())


    def test_windows_flush_and_closed_exclusive_publication(self):
        self.allow()
        opened = []
        original_open, original_fsync, original_link = Path.open, os.fsync, os.link

        def track(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            if path.suffix in {'.part', '.out'}:
                opened.append(stream)
            return stream

        def windows_flush(fd):
            stream = next((s for s in opened if not s.closed and s.fileno() == fd), None)
            if stream is not None and not stream.writable():
                raise OSError(errno.EBADF, 'synthetic read-only flush')
            return original_fsync(fd)

        def windows_publish(source, destination):
            if any(not s.closed for s in opened):
                raise PermissionError(errno.EACCES, 'synthetic Windows sharing violation')
            return original_link(source, destination)

        with patch.object(Path, 'open', track), patch('os.fsync', windows_flush), patch('os.link', windows_publish):
            self.assertEqual(self.send_file()['state'], 'completed')
        self.assertFalse(self.b.files.io_failures)

    def test_finalization_failure_and_cleanup_remain_file_scoped(self):
        self.allow()
        self.b.set_permission(self.a.local_id, 'connect.ping', 'allow')
        for stage, target in [('flush_failed', 'os.fsync'), ('finalize_failed', 'os.link')]:
            with self.subTest(stage=stage), patch(target, side_effect=OSError(errno.EACCES, 'private synthetic path')):
                row = self.send_file()
                self.assertEqual(row['state'], 'failed', row)
                self.assertEqual(row['error'], 'file_io_failed')
            self.assertIn((stage, errno.EACCES), self.b.files.io_failures)
            self.assertFalse(self.b.files.store.path(row['transfer_id'], 'part').exists())
            self.assertFalse(self.b.files.store.path(row['transfer_id'], 'bin').exists())
            self.assertTrue(self.channel.request(canonical(request(self.a, self.b)))['result']['pong'])
        self.assertEqual(self.send_file()['state'], 'completed')
        self.assertNotIn('private synthetic path', str(self.b.repository.activity()))

    def test_receipt_failure_rolls_back_artifact_without_closing_channel(self):
        import sqlite3
        self.allow()
        self.b.set_permission(self.a.local_id, 'connect.ping', 'allow')
        original = self.b.files.store.put
        def fail_completed(db, row):
            if row['state'] == 'completed':
                raise sqlite3.OperationalError('synthetic receipt failure')
            return original(db, row)
        with patch.object(self.b.files.store, 'put', fail_completed):
            row = self.send_file()
        self.assertEqual(row['state'], 'failed')
        self.assertEqual(self.b.files.list()[0]['state'], 'failed')
        self.assertFalse(self.b.files.store.path(row['transfer_id'], 'bin').exists())
        self.assertFalse(self.b.files.store.path(row['transfer_id'], 'part').exists())
        self.assertIn(('receipt_failed', None), self.b.files.io_failures)
        self.assertTrue(self.channel.request(canonical(request(self.a, self.b)))['result']['pong'])

    def test_failure_receipt_contention_does_not_close_channel(self):
        import sqlite3
        self.allow()
        self.b.set_permission(self.a.local_id, 'connect.ping', 'allow')
        offer = self.offer()
        self.channel.file_request(offer.encode())
        original = self.b.files.store.put
        def fail_receipt(db, row):
            if row['state'] == 'failed':
                raise sqlite3.OperationalError('synthetic busy')
            return original(db, row)
        with patch.object(self.b.files.store, 'put', fail_receipt):
            answer = self.send_request(offer, 'complete')
            self.assertEqual(answer['error'], 'content_integrity_failed')
            self.assertTrue(self.channel.request(canonical(request(self.a, self.b)))['result']['pong'])
        self.b.files._cleanup_pass()
        self.assertEqual(self.b.files.list()[0]['state'], 'failed')
        self.assertFalse(self.b.files.store.path(offer.transfer_id, 'part').exists())
        self.assertFalse(self.b.files.failed_pending)

    def test_cleanup_failure_is_deferred_without_losing_receipt(self):
        self.allow()
        original = Path.unlink
        def held_partial(path, *args, **kwargs):
            if path.suffix == '.part':
                raise PermissionError(errno.EACCES, 'synthetic sharing violation')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', held_partial):
            row = self.send_file()
            self.assertEqual(row['state'], 'completed')
            self.assertTrue(self.b.files.cleanup_pending)
        self.b.files._cleanup_pass()
        self.assertFalse(self.b.files.cleanup_pending)
        self.assertFalse(self.b.files.store.path(row['transfer_id'], 'part').exists())
        self.assertEqual(self.b.files.list()[0]['state'], 'completed')
        self.assertEqual(self.b.files.store.path(row['transfer_id'], 'bin').read_bytes(), self.data)

    def test_finalization_is_exclusive(self):
        self.allow()
        original = os.link
        collisions = []
        def collide(source, destination):
            destination.write_bytes(b'existing artifact')
            collisions.append(destination)
            return original(source, destination)
        with patch('os.link', collide):
            row = self.send_file()
        self.assertEqual(row['state'], 'failed')
        self.assertEqual(collisions[0].read_bytes(), b'existing artifact')
        self.assertFalse(self.b.files.store.path(row['transfer_id'], 'part').exists())

    def test_cleanup_serializes_with_finalization_and_receipt(self):
        self.allow()
        entered, release = threading.Event(), threading.Event()
        original = os.link
        def held_link(source, destination):
            entered.set()
            if not release.wait(4):
                raise AssertionError('publication not released')
            return original(source, destination)
        row = self.a.files.prepare(self.b.local_id, self.path)
        with patch('os.link', held_link), ThreadPoolExecutor(1) as pool:
            self.a.files.start(row['transfer_id'])
            try:
                self.assertTrue(entered.wait(4))
                acquired = self.b.files.lock.acquire(blocking=False)
                if acquired:
                    self.b.files.lock.release()
                self.assertFalse(acquired)
                cleanup = pool.submit(self.b.files.invalidate, self.a.local_id)
            finally:
                release.set()
            cleanup.result(4)
        until(lambda: self.a.files.list()[0]['state'] == 'completed')
        self.assertEqual(self.b.files.list()[0]['state'], 'completed')
        self.assertEqual(self.b.files.store.path(row['transfer_id'], 'bin').read_bytes(), self.data)

    def test_old_channel_cleanup_cannot_interrupt_new_admission(self):
        self.allow()
        offer = self.offer()
        self.channel.file_request(offer.encode())
        entered, release = threading.Event(), threading.Event()
        original = self.b.files.invalidate
        def held_invalidate(*args, **kwargs):
            entered.set()
            if not release.wait(4):
                raise AssertionError('invalidation not released')
            return original(*args, **kwargs)
        with patch.object(self.b.files, 'invalidate', held_invalidate), ThreadPoolExecutor(1) as pool:
            completion = pool.submit(self.na.disconnect, self.b.local_id)
            try:
                self.assertTrue(entered.wait(4))
                self.assertFalse(completion.done(), 'disconnect returned before peer file cleanup')
                acquired = self.b.files.lock.acquire(blocking=False)
                if acquired:
                    self.b.files.lock.release()
                self.assertFalse(acquired, 'old teardown exposed fresh file admission')
            finally:
                release.set()
            completion.result(4)
        self.channel = self.na.connect(self.b.local_id, '127.0.0.1', self.nb.port)
        fresh = self.send_file()
        self.assertNotEqual(fresh['transfer_id'], offer.transfer_id)
        self.assertEqual(fresh['state'], 'completed', fresh)

    def test_file_timeout_late_reply_preserves_channel(self):
        self.allow()
        self.b.set_permission(self.a.local_id, 'connect.ping', 'allow')
        entered, release = threading.Event(), threading.Event()
        original = self.b.files.receive
        def held_receive(*args):
            entered.set()
            if not release.wait(4):
                raise AssertionError('request not released')
            return original(*args)
        with patch.object(self.b.files, 'receive', held_receive), ThreadPoolExecutor(1) as pool:
            with patch('olive.connect.network.REQUEST_TIMEOUT', .1):
                pending = pool.submit(self.channel.file_request, self.offer().encode())
                try:
                    self.assertTrue(entered.wait(3))
                    with self.assertRaisesRegex(ConnectError, 'file_request_timeout'):
                        pending.result(3)
                finally:
                    release.set()
        self.assertTrue(self.channel.request(canonical(request(self.a, self.b)))['result']['pong'])
        self.assertTrue(self.na.status(self.b.local_id)['encrypted'], self.diagnostics())

class FileProtocolTests(unittest.TestCase):
    def test_filename_paths_and_reserved_names(self):
        for name in ('../a','/home/a','C:\\a','\\\\server\\x','file://a','a/b','NUL.txt','COM1','x\x00','x\n','', 'x'*181,'a..b','end.'):
            with self.subTest(name=name),self.assertRaises(ConnectError):filename(name)
        self.assertEqual(filename('RaceDay.pdf'),'RaceDay.pdf')

    def test_binary_bounds_and_malformed(self):
        from olive.connect.network_wire import frame, header, FILE_REQUEST, HEADER
        with self.assertRaises(ConnectError):FileRequest.decode(b'garbage')
        with self.assertRaises(ConnectError):frame(FILE_REQUEST,b'x'*(CHUNK_SIZE+5000))
        with self.assertRaises(ConnectError):header(HEADER.pack(CHUNK_SIZE+5000,1,FILE_REQUEST))

class FileApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncio
        from olive.bridge.host import Host
        from olive.connect.approvals import ConnectApprovals
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.a,self.b=[DesktopDeviceService(self.root/str(i),key_store=DeviceKeyStore(MemoryVault())) for i in range(2)]
        pair(self.a,self.b)
        self.host=Host(lambda _:None);self.host.activity=lambda:None
        self.b.approvals=ConnectApprovals(self.b,self.host.confirm,asyncio.get_running_loop())
        self.a.enable_network('127.0.0.1',discovery=False);self.b.enable_network('127.0.0.1',discovery=False)
        self.channel=await asyncio.to_thread(self.a.network.connect,self.b.local_id,'127.0.0.1',self.b.network.port)
        self.b.set_permission(self.a.local_id,'files.receive','ask')
        now=int(time.time())
        self.offer=FileRequest(str(uuid.uuid4()),PROTOCOL,str(uuid.uuid4()),self.a.local_id,self.b.local_id,
            'offer',dict(name='a.sh',size=1,sha256=hashlib.sha256(b'x').hexdigest(),mime='application/octet-stream'),now,now+120)

    async def asyncTearDown(self):
        import asyncio
        for s in (self.a,self.b):await asyncio.to_thread(s.close)
        self.temp.cleanup()

    async def send(self,req,data=b''):
        import asyncio
        return await asyncio.to_thread(self.channel.file_request,req.encode(data))

    async def pending(self):
        import asyncio
        for _ in range(100):
            if self.host.pending:return next(iter(self.host.pending.values()))[0]
            await asyncio.sleep(.01)
        self.fail('No trusted local prompt')

    async def test_metadata_change_never_reuses_approval_and_cancel_removes_prompt(self):
        import asyncio
        from dataclasses import replace
        self.assertEqual((await self.send(self.offer))['result']['state'],'awaiting_approval')
        pending=await self.pending()
        await self.host.execute('approval.respond',dict(approval_id=pending['id'],fingerprint=pending['fingerprint'],approved=True))
        await asyncio.sleep(.02)
        changed=replace(self.offer,arguments={**self.offer.arguments,'name':'changed.sh'})
        self.assertEqual((await self.send(changed))['error'],'changed_duplicate')
        self.assertEqual((await self.send(self.offer))['result']['state'],'accepted')
        # A chunk cannot carry local approval booleans or substituted offer metadata.
        with self.assertRaises(ConnectError):replace(self.offer,arguments={**self.offer.arguments,'approved':True}).encode()
        self.b.set_permission(self.a.local_id,'files.receive','deny')
        chunk=replace(self.offer,request_id=str(uuid.uuid4()),operation='chunk',arguments={'offset':0})
        self.assertEqual((await self.send(chunk,b'x'))['error'],'permission_off')
        self.b.set_permission(self.a.local_id,'files.receive','ask')
        offer=replace(self.offer,transfer_id=str(uuid.uuid4()),request_id=str(uuid.uuid4()))
        await self.send(offer);await self.pending()
        await asyncio.to_thread(self.b.files.cancel,offer.transfer_id)
        for _ in range(50):
            if not self.host.pending:break
            await asyncio.sleep(.01)
        self.assertFalse(self.host.pending)

    async def test_sending_ask_is_local_and_changed_source_requires_review(self):
        import asyncio
        from olive.connect.approvals import ConnectApprovals
        self.a.approvals=ConnectApprovals(self.a,self.host.confirm,asyncio.get_running_loop())
        self.a.set_permission(self.b.local_id,'files.send','ask')
        self.b.set_permission(self.a.local_id,'files.receive','allow')
        path=self.root/'selected.pdf';path.write_bytes(b'original')
        row=await asyncio.to_thread(self.a.files.prepare,self.b.local_id,path)
        await asyncio.to_thread(self.a.files.start,row['transfer_id'])
        pending=await self.pending()
        self.assertEqual(pending['arguments']['capability'],'files.send')
        self.assertEqual(pending['arguments']['operation'],'local_send')
        path.write_bytes(b'changed')
        await self.host.execute('approval.respond',dict(approval_id=pending['id'],fingerprint=pending['fingerprint'],approved=True))
        for _ in range(200):
            if self.a.files.list()[0]['state']=='failed':break
            await asyncio.sleep(.01)
        self.assertEqual(self.a.files.list()[0]['error'],'source_changed_review_again')
        self.assertEqual(self.b.files.list(),[])
        self.assertEqual(self.a.permission(self.b.local_id,'files.send').value,'ask')
