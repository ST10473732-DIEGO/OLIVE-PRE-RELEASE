"""Full two-sided C4.1 receipts between Swift and desktop over fixture pipes.

Not LAN/device acceptance. Swift fixture executable explicitly opts in; never
used by the app and never linked into the app target.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from olive.connect.contracts import canonical
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault

@unittest.skipUnless(os.environ.get('OLIVE_SWIFT_INTEROP'), 'Run mobile/ios/scripts/check-connect-interop.sh on Mac')
class MobilePairingInteropTests(unittest.TestCase):
    def test_swift_identity_tls_comparison_and_two_sided_receipts(self):
        with tempfile.TemporaryDirectory(prefix='olive-swift-pair-') as tmp:
            service = DesktopDeviceService(Path(tmp),key_store=DeviceKeyStore(MemoryVault()))
            process = subprocess.Popen([os.environ['OLIVE_SWIFT_INTEROP'],'--pair-fixture'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                offer = service.pairing.create_offer(endpoint=dict(address='192.168.1.2',port=54321))
                sid = json.loads(offer)['session_id']
                process.stdin.write(offer.decode()+'\n'); process.stdin.flush()
                reply = json.loads(process.stdout.readline())
                service.pairing.receive_reply(canonical(reply))
                pending = b''; compared = False; peer_plain = b''
                for _ in range(12):
                    process.stdin.write(json.dumps(dict(incoming=base64.b64encode(pending).decode(),confirm=compared))+'\n');process.stdin.flush()
                    received = json.loads(process.stdout.readline())
                    peer_plain += base64.b64decode(received['plain'])
                    pending = service.pairing.exchange(sid,base64.b64decode(received['outgoing']))
                    if received['ready'] and not compared:
                        self.assertEqual(service.pairing.preview(sid)['comparison'],received['comparison'])
                        self.assertEqual(service.paired_devices(),[])
                        service.pairing.confirm(sid,received['comparison'])
                        self.assertEqual(service.paired_devices(),[]) # one side never sufficient
                        compared = True
                    session = service.pairing._sessions[sid]
                    if session.get('receipt_received') and len(peer_plain) == 137:
                        break
                self.assertTrue(compared)
                record = service.pairing.complete_desktop(sid)
                self.assertEqual(record['public_identity'],reply['identity'])
                self.assertEqual(record['permissions'],[])
                self.assertEqual(record['connection_state'],'offline')
                self.assertTrue(peer_plain.startswith(b'OLIVE-CONFIRM/1:'))
                saved = service.pairing.completion.load(sid)
                self.assertEqual(len(saved['receipts']),2)
            finally:
                process.stdin.close()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                process.stdout.close(); process.stderr.close(); service.close()
