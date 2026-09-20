"""Two independent ordinary backends, real TLS bytes and real local Ask registry."""
import hashlib
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import pair
from tests.connect_files_process_fixture import worker


class FileProcessTests(unittest.TestCase):
    def test_off_ask_deny_allow_once_multichunk_and_save(self):
        ctx=multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);vaults=[MemoryVault(),MemoryVault()]
            services=[DesktopDeviceService(root/str(i),key_store=DeviceKeyStore(v)) for i,v in enumerate(vaults)]
            pair(*services); ids=[s.local_id for s in services]
            for s in services:s.close()
            children=[];pipes=[];ports=[]
            def call(i,*args):
                pipes[i].send(args);self.assertTrue(pipes[i].poll(15),'child timeout')
                value=pipes[i].recv()
                self.assertFalse(isinstance(value,dict) and 'fixture_error' in value,value)
                return value
            def wait(i,op,predicate):
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    value=call(i,op)
                    if predicate(value):return value
                    time.sleep(.025)
                self.fail(f'timed out: {op}: {value}; file I/O categories: {call(i, "diagnostics")}')
            try:
                for i in range(2):
                    parent,child=ctx.Pipe();p=ctx.Process(target=worker,args=(child,str(root/str(i)),vaults[i].values))
                    p.start();child.close();pipes.append(parent);children.append(p)
                    self.assertTrue(parent.poll(10));ports.append(parent.recv())
                call(0,'connect',ids[1],ports[1]);call(0,'permission',ids[1],'files.send','allow')
                data=bytes(range(256))*4097;source=root/'RaceDay.pdf';source.write_bytes(data)
                def send():
                    row=call(0,'prepare',ids[1],str(source));call(0,'start',row['transfer_id']);return row
                send();wait(0,'list',lambda r:r[0]['state']=='failed')
                self.assertEqual(call(1,'list'),[])
                call(1,'permission',ids[0],'files.receive','ask')
                send();pending=wait(1,'pending',bool)[0]
                self.assertEqual(pending['arguments']['file']['sha256'],hashlib.sha256(data).hexdigest())
                self.assertEqual(pending['arguments']['file']['size'],len(data))
                self.assertNotIn(str(source),str(pending))
                call(1,'approve',False)
                wait(0,'list',lambda r:r[0]['state']=='failed')
                self.assertEqual(call(1,'list')[0]['state'],'declined')
                row=send();wait(1,'pending',bool);call(1,'approve',True)
                incoming=wait(1,'list',lambda r:r[0]['state']=='completed')[0]
                wait(0,'list',lambda r:r[0]['state']=='completed')
                self.assertEqual(call(1,'policy',ids[0],'files.receive'),'ask')
                artifact=root/'1'/'quarantine'/'connect-inbox'/(row['transfer_id']+'.bin')
                self.assertEqual(artifact.read_bytes(),data)
                self.assertEqual(incoming['received_size'],len(data))
                self.assertNotIn(str(source),str(incoming))
                destination=root/'saved.pdf';call(1,'export',row['transfer_id'],str(destination))
                self.assertEqual(destination.read_bytes(),data)
                self.assertEqual(len(list(artifact.parent.glob('*.bin'))),1)
                # Interruption and revocation while actual child-process chunks flow.
                call(1,'permission',ids[0],'files.receive','allow')
                source.write_bytes(bytes(range(256))*32768)
                partial=send()
                wait(1,'list',lambda r:r[0]['transfer_id']==partial['transfer_id'] and r[0]['received_size']>0)
                call(0,'disconnect',ids[1])
                wait(1,'list',lambda r:r[0]['transfer_id']==partial['transfer_id'] and r[0]['state']=='interrupted')
                self.assertFalse((artifact.parent/(partial['transfer_id']+'.bin')).exists())
                self.assertFalse((artifact.parent/(partial['transfer_id']+'.part')).exists())
                call(0,'connect',ids[1],ports[1])
                source.write_bytes(data)
                retry=send()
                self.assertNotEqual(retry['transfer_id'], partial['transfer_id'])
                wait(1,'list',lambda r:r[0]['transfer_id']==retry['transfer_id'] and r[0]['state']=='completed')
                wait(0,'list',lambda r:r[0]['state']=='completed')
                self.assertEqual((artifact.parent/(retry['transfer_id']+'.bin')).read_bytes(),data)
                self.assertEqual(len(list(artifact.parent.glob('*.bin'))),2)
                source.write_bytes(bytes(range(256))*32768)
                revoked=send()
                wait(1,'list',lambda r:r[0]['transfer_id']==revoked['transfer_id'] and r[0]['received_size']>0)
                call(1,'revoke',ids[0])
                wait(0,'list',lambda r:r[0]['state'] in {'failed','interrupted'})
                self.assertFalse((artifact.parent/(revoked['transfer_id']+'.bin')).exists())
                self.assertFalse((artifact.parent/(revoked['transfer_id']+'.part')).exists())
                pipes[0].send(('connect',ids[1],ports[1]))
                self.assertTrue(pipes[0].poll(12))
                self.assertIn('fixture_error',pipes[0].recv())
                self.assertEqual(artifact.read_bytes(),data)

            finally:
                for pipe,p in zip(pipes,children):
                    if p.is_alive():
                        pipe.send(('stop',))
                        if pipe.poll(10):pipe.recv()
                        p.join(10)
                    if p.is_alive():p.terminate();p.join(3)
                    pipe.close()
                for p in children:self.assertEqual(p.exitcode,0)
            self.assertFalse(list(root.rglob('*.part')))
            self.assertFalse(list(root.rglob('*.out')))
