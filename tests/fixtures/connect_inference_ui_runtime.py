"""Electron-only engine fixture and independent paired backend. No product hook."""
import asyncio
import json
import multiprocessing
import os
from pathlib import Path

from olive.bridge.host import Host
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import pair
from tests.connect_inference_fixture import Engine
from tests.connect_inference_process_fixture import worker

original_start = Host.start


async def start(self, directory):
    await original_start(self, directory)
    await self.initialization
    s = self.services
    service = s.connect
    vault = MemoryVault()
    service.identities.key_store = DeviceKeyStore(vault)
    live = os.environ.get('OLIVE_C7_LIVE') == '1'
    engine = Engine()
    if not live:
        s.ollama.client = engine
    await s.model_registry.refresh()
    s.model_infos = await s.ollama.list_models()
    profile = Path(directory)
    peer_vault = MemoryVault()
    peer_service = DesktopDeviceService(profile / 'peer', key_store=DeviceKeyStore(peer_vault))
    peer_service.rename(peer_service.local_id, 'C7 paired desktop')
    pair(service, peer_service)
    peer_id = peer_service.local_id
    service.rename(peer_id, 'C7 paired desktop')
    peer_service.close()
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=worker, args=(child, str(profile / 'peer'), peer_vault.values, live))
    process.start(); child.close()
    port = await asyncio.to_thread(parent.recv)
    async def rpc(*args):
        parent.send(args)
        result = await asyncio.to_thread(parent.recv)
        if isinstance(result, dict) and 'fixture_error' in result:
            raise RuntimeError(result['fixture_error'])
        return result
    original_close = service.close
    def close():
        if process.is_alive():
            parent.send(('stop',))
            if parent.poll(10):
                parent.recv()
            process.join(10)
        if process.is_alive():
            process.terminate(); process.join(3)
        parent.close()
        original_close()
    service.close = close
    async def monitor():
        last = None
        while not service.closed:
            try:
                path = profile / 'fixture-command.json'
                if path.exists():
                    command = json.loads(path.read_text())
                    if command['id'] != last:
                        last = command['id']
                        action = command['action']
                        if action == 'connect':
                            await asyncio.to_thread(service.network.connect, peer_id, '127.0.0.1', port)
                            result = peer_id
                        elif action == 'incoming':
                            result = await rpc('send', service.local_id, 'fast', 'Give me code for a loop.')
                        elif action == 'incoming_done':
                            result = await rpc('wait_chat')
                        elif action == 'permission':
                            result = await rpc('permission', service.local_id, command['value'])
                        elif action == 'mode':
                            result = await rpc('mode', command['value'])
                        elif action == 'local_mode' and not live:
                            engine.mode = command['value']; result = True
                        elif action == 'counts':
                            result = {'local': len(engine.calls), 'peer': await rpc('counts')}
                        elif action == 'disconnect':
                            result = await asyncio.to_thread(service.network.disconnect, peer_id)
                        else:
                            raise ValueError('fixture action')
                        staging = profile / 'fixture-result.tmp'
                        staging.write_text(json.dumps({'id': last, 'result': result}))
                        staging.replace(profile / 'fixture-result.json')
            except Exception as error:
                (profile / 'fixture-error.txt').write_text(type(error).__name__ + ': ' + str(error))
            await asyncio.sleep(.05)
    self.connect_fixture_task = asyncio.create_task(monitor())


Host.start = start
