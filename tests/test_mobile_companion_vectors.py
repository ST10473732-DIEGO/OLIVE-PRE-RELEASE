"""Public mobile fixture contracts; no device, profile or private keys."""
import base64
import json
import unittest
from dataclasses import asdict
from scripts.mobile_companion_vectors import FIXTURE, check
from olive.connect.contracts import canonical, ConnectError
from olive.connect.file_protocol import FileRequest, MAX_FILE_SIZE
from olive.connect.studio_protocol import StudioRequest

class MobileCompanionVectorsTests(unittest.TestCase):
    def test_public_fixture_production_decoders(self):
        check(json.loads(FIXTURE.read_bytes()))

    def test_oversize_and_no_offset_resume(self):
        value = json.loads(FIXTURE.read_bytes())
        offer, _ = FileRequest.decode(base64.b64decode(value['files']['offer']))
        raw = asdict(offer)
        raw['arguments']['size'] = MAX_FILE_SIZE + 1
        metadata = canonical(raw)
        with self.assertRaises(ConnectError):
            FileRequest.decode(len(metadata).to_bytes(4, 'big') + metadata)
        raw['operation'] = 'resume'; raw['arguments'] = {'offset': 64}
        metadata = canonical(raw)
        with self.assertRaises(ConnectError):
            FileRequest.decode(len(metadata).to_bytes(4, 'big') + metadata)

    def test_studio_rejects_extra_authority_and_unknown_version(self):
        value = json.loads(FIXTURE.read_bytes())['studio']['run']
        for operation in ('terminal', 'pty', 'debug', 'install'):
            with self.assertRaises(ConnectError):
                StudioRequest.decode(canonical(dict(value, operation=operation)))
        with self.assertRaises(ConnectError):
            StudioRequest.decode(canonical(dict(value, arguments={'command': 'echo fixture'})))
        with self.assertRaises(ConnectError):
            StudioRequest.decode(canonical(dict(value, protocol_version='olive-studio/99')))
