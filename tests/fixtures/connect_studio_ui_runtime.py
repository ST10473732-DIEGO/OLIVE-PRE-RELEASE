"""Test-only native UI fixture; all peer traffic uses independent real C3 TLS."""
import asyncio
import json
import multiprocessing
from pathlib import Path
from olive.bridge.host import Host
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.connect.studio_protocol import request
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import pair
from tests.connect_studio_process_fixture import worker

original_start = Host.start


async def start(self, directory):
    await original_start(self, directory)
    await self.initialization
    s = self.services; service = s.connect
    service.identities.key_store = DeviceKeyStore(MemoryVault())
    profile = Path(directory)
    root = profile / 'target-fixture'; root.mkdir()
    (root / 'main.py').write_text('print("target")\n')
    s.data.create_workspace('Target fixture', str(root))
    vault = MemoryVault()
    peer_service = DesktopDeviceService(profile / 'peer', key_store=DeviceKeyStore(vault))
    peer_service.rename(peer_service.local_id, 'C8 paired desktop')
    pair(service, peer_service)
    peer_id = peer_service.local_id
    service.rename(peer_id, 'C8 paired desktop'); peer_service.close()
    context = multiprocessing.get_context('spawn'); parent, child = context.Pipe()
    process = context.Process(target=worker, args=(child, str(profile / 'peer'), vault.values))
    process.start(); child.close()
    info = await asyncio.to_thread(parent.recv)
    async def rpc(*args):
        parent.send(args); result = await asyncio.to_thread(parent.recv)
        if isinstance(result, dict) and 'fixture_error' in result: raise RuntimeError(str(result))
        return result
    share = (await rpc('share', service.local_id))[0]
    for cap in ('view', 'edit', 'build', 'test', 'run'):
        share = (await rpc('permission', service.local_id, share['workspace_id'], 'studio.' + cap, 'allow'))[0]
    original_close = service.close
    def close():
        if process.is_alive():
            parent.send(('stop',))
            if parent.poll(15): parent.recv()
            process.join(10)
        if process.is_alive(): process.terminate(); process.join(3)
        parent.close(); original_close()
    service.close = close
    async def monitor():
        last = None; incoming = None
        while not service.closed:
            try:
                path = profile / 'fixture-command.json'
                if path.exists():
                    command = json.loads(path.read_text())
                    if command['id'] != last:
                        last = command['id']; action = command['action']
                        if action == 'connect':
                            await asyncio.to_thread(service.network.connect, peer_id, '127.0.0.1', info['port'])
                            result = {'peer': peer_id, 'share': share}
                        elif action == 'disconnect':
                            await asyncio.to_thread(service.network.disconnect, peer_id); result = True
                        elif action == 'edit': result = await rpc('edit_local', command['value'].encode())
                        elif action == 'bytes': result = (await rpc('bytes')).decode()
                        elif action == 'counts': result = await rpc('counts')
                        elif action == 'incoming':
                            shared = service.studio.shared(peer_id)[0]
                            incoming = request(peer_id, service.local_id, 'read', shared['workspace_id'], shared['share_revision'], {'path': 'main.py'})
                            result = await rpc('request', service.local_id, incoming)
                        elif action == 'retry': result = await rpc('request', service.local_id, incoming)
                        else: raise ValueError('fixture action')
                        staging = profile / 'fixture-result.tmp'
                        staging.write_text(json.dumps({'id': last, 'result': result})); staging.replace(profile / 'fixture-result.json')
            except Exception as error:
                (profile / 'fixture-error.txt').write_text(type(error).__name__ + ': ' + str(error))
            await asyncio.sleep(.05)
    self.connect_fixture_task = asyncio.create_task(monitor())


Host.start = start
