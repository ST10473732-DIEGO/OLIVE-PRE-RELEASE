"""C5 two/three-process acceptance over authenticated real loopback TLS."""
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.personal.store import PersonalStore
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import pair
from tests.connect_sync_process_fixture import worker


class SyncProcessTests(unittest.TestCase):
    def test_offline_resolution_calendar_reminder_selected_chat_tombstone_and_revoke(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as root:
            vaults = [MemoryVault() for _ in range(3)]
            services = [DesktopDeviceService(Path(root) / str(i), key_store=DeviceKeyStore(v)) for i,v in enumerate(vaults)]
            ids = [s.local_id for s in services]
            for a, b in ((0,1),(1,2),(0,2)):
                pair(services[a],services[b])
                for left,right in ((a,b),(b,a)):
                    for domain in ('tasks','calendar','reminders','chat'):
                        services[left].set_permission(ids[right], 'sync.' + domain, 'allow')
            for service in services: service.close()
            children, pipes, ports = [], [], []
            def call(index, *args):
                pipes[index].send(args)
                self.assertTrue(pipes[index].poll(20), 'synthetic worker timeout')
                result = pipes[index].recv()
                self.assertFalse(isinstance(result, dict) and 'fixture_error' in result, result)
                return result
            def sync(a,b):
                result = call(a, 'sync', ids[b])
                self.assertEqual(result['state'], 'completed', result)
            try:
                for i in range(3):
                    parent, child = context.Pipe()
                    process = context.Process(target=worker,args=(child,str(Path(root)/str(i)),vaults[i].values))
                    process.start(); child.close(); children.append(process); pipes.append(parent)
                    self.assertTrue(parent.poll(10)); ports.append(parent.recv())
                call(0,'connect',ids[1],ports[1]); call(1,'connect',ids[2],ports[2])
                task = call(0,'save','task',{'title':'Assignment'})
                sync(0,1)
                first = call(0,'revision',task['id'])
                self.assertEqual(call(1,'revision',task['id']),first)
                second = call(1,'get','task',task['id'])
                call(1,'save','task',{**PersonalStore.body(second),'due':'2026-09-21'},task['id'],second['revision'])
                sync(1,0); sync(1,2)
                self.assertEqual(call(0,'revision',task['id']),call(2,'revision',task['id']))
                call(0,'disconnect',ids[1])
                for i,title in ((0,'Tonight'),(1,'Tomorrow')):
                    item=call(i,'get','task',task['id'])
                    call(i,'save','task',{**PersonalStore.body(item),'title':title},item['id'],item['revision'])
                call(0,'connect',ids[1],ports[1]); sync(1,0)
                conflict=call(0,'conflicts')[0]
                self.assertEqual(call(0,'resolve',conflict['id'],'local')['state'],'resolved')
                sync(0,1)
                self.assertEqual(call(1,'get','task',task['id'])['title'],'Tonight')
                # Independent descendants on B/C still conflict after relaying.
                ctask=call(2,'get','task',task['id'])
                call(2,'save','task',{**PersonalStore.body(ctask),'title':'Third device offline'},task['id'],ctask['revision'])
                sync(1,2)
                self.assertTrue(call(2,'conflicts'))
                calendar=call(0,'search','calendar')['items'][0]
                event=call(0,'save','event',{'calendar_id':calendar['id'],'title':'Study','start':'2026-11-01T01:30:00-04:00','end':'2026-11-01T02:30:00-05:00','timezone':'America/New_York','recurrence':'FREQ=WEEKLY;COUNT=3'})
                reminder=call(0,'save','reminder',{'target_kind':'event','target_id':event['id'],'offset_minutes':15,'timezone':'America/New_York'})
                shared=call(0,'chat','Selected'); private=call(0,'chat','Private')
                call(0,'select',ids[1],shared['id'],True)
                sync(0,1)
                self.assertEqual(call(1,'get','event',event['id'])['recurrence'],'FREQ=WEEKLY;COUNT=3')
                self.assertEqual(call(1,'get','reminder',reminder['id'])['target_id'],event['id'])
                chats=call(1,'chats'); self.assertNotIn(private['id'],chats)
                self.assertEqual([m['id'] for m in chats[shared['id']]['messages']],[m['id'] for m in shared['messages']])
                message=call(1,'append',shared['id'],'Continue here')
                sync(1,0); sync(1,0)
                self.assertEqual(sum(m['id']==message['id'] for m in call(0,'chats')[shared['id']]['messages']),1)
                item=call(0,'get','task',task['id']); call(0,'delete','task',task['id'],item['revision'])
                sync(0,1)
                self.assertTrue(call(1,'revision',task['id'])['deleted'])
                call(0,'revoke',ids[1])
                time.sleep(.1)
                self.assertEqual(call(1,'sync',ids[0])['state'],'partial')
            finally:
                for pipe, process in zip(pipes,children):
                    if process.is_alive():
                        pipe.send(('stop',))
                        if pipe.poll(10): pipe.recv()
                    process.join(10)
                    if process.is_alive(): process.terminate(); process.join(5)
                    pipe.close()
                    self.assertEqual(process.exitcode,0)
