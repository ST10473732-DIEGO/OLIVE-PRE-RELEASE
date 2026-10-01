"""TEST-ONLY startup shim for the OLIVE Connect World desktop UI check.

Real desktop backend (bridge Host, Connect, WorldService presence), a real local
development relay (loopback ws://) and a phone-role Python peer that is paired,
provisioned over Direct once, then connected through World only (forced World).
Synthetic memory vaults; isolated test profile. No product route imports this.
"""
import asyncio
import json
from pathlib import Path

from olive.bridge.host import Host
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.connect.world import WorldKeyStore
from olive.connect.world_peer import WorldPeer, provision
from tests.test_connect_network import pair, until
from tests.test_connect_pairing import MemoryVault
from tests.world_fixture import RelayThread

original_start = Host.start


async def start(self, directory):
    await original_start(self, directory)
    service = self.services.connect
    vault = MemoryVault()
    service.identities.key_store = DeviceKeyStore(vault)
    service.world.keys = WorldKeyStore(vault)
    service.world.dev = True                      # Loopback development relay only.
    profile = Path(directory)
    relay = RelayThread().start()
    state = {}

    def world_peer():
        phone = DesktopDeviceService(profile / 'phone', key_store=DeviceKeyStore(MemoryVault()))
        phone.rename(phone.local_id, 'World test iPhone')
        pair(phone, service)
        service.rename(phone.local_id, 'World test iPhone')
        phone.enable_network('127.0.0.1', discovery=False)
        direct = phone.network.connect(service.local_id, '127.0.0.1', service.network.port)
        peer = WorldPeer(phone, service.local_id, dev=True)
        peer.store(provision(direct, phone, service.local_id))      # One-time enrolment on the LAN.
        phone.network.disconnect(service.local_id)                  # Then the phone "leaves Wi-Fi".
        until(lambda: service.world.status()['peers'][phone.local_id]['route'] == 'registered', 10)
        channel = None
        for _ in range(40):
            try:
                channel = peer.connect(wait=3)                       # Forced World: no Direct attempt.
                break
            except Exception:
                import time
                time.sleep(.25)
        state.update(phone=phone, peer=peer, channel=channel)
        return dict(phone_id=phone.local_id, path=channel.path if channel else None)

    original_close = service.close

    def close():
        if 'peer' in state:
            state['peer'].close()
            state['phone'].close()
        original_close()
        relay.stop()
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
                        if action == 'relay_url':
                            result = relay.url
                        elif action == 'world_peer':
                            result = await asyncio.to_thread(world_peer)
                        elif action == 'world_status':
                            result = service.world.status()
                        elif action == 'relay_frames':
                            result = 'n/a'
                        else:
                            raise ValueError('Unknown fixture action')
                        staging = profile / 'fixture-result.tmp'
                        staging.write_text(json.dumps(dict(id=last, result=result)))
                        staging.replace(profile / 'fixture-result.json')
            except Exception as error:
                (profile / 'fixture-error.txt').write_text(type(error).__name__ + ': ' + str(error))
            await asyncio.sleep(.05)
    self.connect_fixture_task = asyncio.create_task(monitor())


Host.start = start
