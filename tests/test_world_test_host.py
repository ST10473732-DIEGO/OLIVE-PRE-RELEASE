"""The Mac physical-iPhone TEST HOST with --world: provision over Direct, then force World.

A Python phone-role peer stands in for the iPhone here; on the Mac the real
phone runs the same steps (see mobile/ios/README.md, OLIVE Connect World).
"""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from olive.connect.contracts import canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from olive.connect.world_peer import WorldPeer, provision
from tests.test_connect_network import pair, request, until
from tests.test_connect_pairing import MemoryVault


class WorldTestHostTests(unittest.TestCase):
    def setUp(self):
        from tests.fixtures.draw_phone_test_host import Host, lan_address
        try:
            address = lan_address()
        except OSError:
            self.skipTest('No LAN address on this machine')
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.host = Host(root / 'host', chat=True, world=True, world_port=0)
        self.phone = DesktopDeviceService(root / 'phone', key_store=DeviceKeyStore(MemoryVault()))
        pair(self.phone, self.host.service)
        self.phone.enable_network(address, discovery=False)
        self.peer = WorldPeer(self.phone, self.host.service.local_id, test_lan=True)

    def tearDown(self):
        if hasattr(self, 'peer'):
            self.peer.close()
            self.phone.close()
            self.host.network_off()
            self.host.service.close()
            self.host.notes.close()
            self.host.relay.stop()
            self.temp.cleanup()

    def test_provision_over_direct_then_force_world(self):
        host = self.host
        direct = self.phone.network.connect(host.service.local_id, host.network.interface.address, host.network.port)
        self.peer.store(provision(direct, self.phone, host.service.local_id))
        self.assertTrue(self.peer.credentials['relay_url'].startswith('ws://'))
        until(lambda: host.world()['world']['relay'] == 'connected', 8)
        # The phone leaves Wi-Fi (its Direct intent ends) while the host also blocks Direct.
        dropper = threading.Thread(target=host.handle, args=({'cmd': 'drop_direct', 'args': {'seconds': 1.5}},))
        dropper.start()
        self.phone.network.disconnect(host.service.local_id, wait=False)
        until(lambda: direct.stop.is_set(), 4)
        dropper.join()
        channel = self.peer.connect(wait=10)
        host.service.set_permission(self.phone.local_id, 'connect.ping', 'allow')
        self.assertTrue(channel.request(canonical(request(self.phone, host.service)))['result']['pong'])
        self.assertEqual(host.handle({'cmd': 'world'})['path'], 'world')
        self.assertNotIn('route_secret', repr(host.handle({'cmd': 'world'})))
        host.handle({'cmd': 'relay_restart', 'args': {'seconds': .2}})
        until(lambda: channel.stop.is_set(), 6)
        until(lambda: host.world()['world']['peers'][self.phone.local_id]['route'] == 'registered', 20)
        channel = self.peer.connect(wait=10)
        self.assertEqual(channel.path, 'world')


if __name__ == '__main__':
    unittest.main()
