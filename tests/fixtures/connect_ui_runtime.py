"""Test-only startup shim. Real C2/C3 services; synthetic memory vaults and peer pipe.

Control files belong exclusively to an isolated test profile. No product route
can import this harness, inject discovery, exchange TLS bytes or access keys.
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from olive.bridge.host import Host
from olive.connect.identity import DeviceKeyStore
from tests.test_connect_pairing import MemoryVault

original_start = Host.start

async def start(self, directory):
    await original_start(self, directory)
    service = self.services.connect
    service.identities.key_store = DeviceKeyStore(MemoryVault())
    profile = Path(directory)
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    peer = subprocess.Popen([sys.executable, '-u', str(Path(__file__).with_name('connect_peer.py')), str(profile/'peer')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
    original_close = service.close
    def close():
        try:
            peer.stdin.write('{"command":"close"}\n'); peer.stdin.flush()
            peer.wait(timeout=8)
        finally:
            if peer.poll() is None:
                peer.terminate(); peer.wait(timeout=4)
            peer.stdin.close(); peer.stdout.close(); peer.stderr.close()
            original_close()
    service.close = close
    async def rpc(command, **args):
        peer.stdin.write(json.dumps(dict(command=command,**args))+'\n'); peer.stdin.flush()
        result=json.loads(await asyncio.to_thread(peer.stdout.readline))
        if not result['ok']:raise RuntimeError(result['error'])
        return result['value']
    async def monitor():
        last=None
        sid=None
        while not service.closed:
            try:
                path=profile/'fixture-command.json'
                if path.exists():
                    command=json.loads(path.read_text())
                    if command['id']!=last:
                        last=command['id']
                        action=command['action']
                        if action in ('responder_offer', 'responder_unreachable'):
                            result=await rpc('create')
                            sid=result['session_id']
                            if action=='responder_unreachable':
                                await rpc('cancel',sid=sid)
                        elif action=='listener':
                            result=service.pairing_transport.listener is not None
                        elif action=='comparison':
                            result=dict(comparison=await rpc('preview',sid=sid))
                        elif action=='pair':
                            offer=self.devices_workspace.offer
                            sid=offer['session_id']
                            await rpc('accept',offer=offer['offer'])
                            for _ in range(100):
                                if self.devices_workspace.pairing_status(sid).get('comparison'):
                                    break
                                await asyncio.sleep(.05)
                            result=dict(comparison=await rpc('preview',sid=sid))
                        elif action=='expire':
                            sid=self.devices_workspace.offer['session_id']
                            with service.pairing._lock:
                                service.pairing._sessions[sid]['deadline']=0
                            service.pairing.expire()
                            result=True
                        elif action=='finish_pair':
                            await rpc('confirm',sid=sid,comparison=service.pairing.preview(sid)['comparison'])
                            result=await rpc('complete',sid=sid)
                        elif action=='connect':
                            result=await rpc('connect',peer=service.local_id,port=service.network.port)
                        elif action=='sync_setup':
                            result=await rpc('sync_setup',peer=service.local_id)
                        elif action=='sync_conflict':
                            await rpc('sync_edit')
                            personal=self.services.personal.records
                            task=personal.search('task')['items'][0]
                            result=personal.save('task',{**personal.store.body(task),'title':'This device changed task'},task['id'],task['revision'])
                        elif action=='peer_status':
                            result=await rpc('status',peer=service.local_id)
                        elif action=='stop_reconnect':
                            result=await rpc('stop_reconnect')
                        elif action=='request':
                            result=await rpc('request',key=command['key'],peer=service.local_id)
                        elif action=='nearby':
                            # Controlled visual-only discovery provider; grants no trust.
                            class Directory:
                                def nearby(self):return [dict(instance='synthetic._olive-connect._tcp.local.',address='127.0.0.1',port=45678,state='discovered')]
                                def close(self):pass
                            service.network.discovery=Directory()
                            result=True
                        else:raise ValueError('Unknown fixture action')
                        target=profile/'fixture-result.json'
                        staging=profile/'fixture-result.tmp'
                        staging.write_text(json.dumps(dict(id=last,result=result)))
                        staging.replace(target)
            except Exception as error:
                (profile/'fixture-error.txt').write_text(type(error).__name__+': '+str(error))
            await asyncio.sleep(.05)
    self.connect_fixture_task=asyncio.create_task(monitor())
Host.start=start
