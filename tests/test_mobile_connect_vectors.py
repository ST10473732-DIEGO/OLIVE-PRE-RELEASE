"""Cross-language public vectors, checked by the actual desktop codecs."""
import json
import unittest
from scripts.mobile_connect_vectors import FIXTURE, check
from olive.connect.contracts import ConnectError, canonical
from olive.connect.inference_protocol import InferenceRequest, response
from olive.connect.network_wire import header
from olive.connect.pairing_wire import decode_offer

class MobileConnectVectorsTests(unittest.TestCase):
    def setUp(self):
        self.v = json.loads(FIXTURE.read_bytes())

    def test_production_vectors(self):
        check(self.v)

    def test_duplicate_and_unknown_fields(self):
        raw = canonical(self.v['start'])
        with self.assertRaises(ConnectError):
            InferenceRequest.decode(b'{"operation":"start",' + raw[1:])
        value = dict(self.v['start'], owner_mode=True)
        with self.assertRaises(ConnectError):
            InferenceRequest.decode(canonical(value))

    def test_invalid_enum_and_input_fingerprint(self):
        for preset in ('deep', 'reimagine', 'AUTO'):
            value = dict(self.v['start'], arguments=dict(self.v['start']['arguments'], preset=preset))
            with self.assertRaises(ConnectError):
                InferenceRequest.decode(canonical(value))
        value = dict(self.v['start'], arguments=dict(self.v['start']['arguments'], input_fingerprint='0'*64))
        with self.assertRaises(ConnectError):
            InferenceRequest.decode(canonical(value))

    def test_bad_frame_headers(self):
        for raw in (bytes.fromhex('000119410109'), bytes.fromhex('000000000204'), bytes.fromhex('000000010104')):
            with self.assertRaises(ConnectError):
                header(raw)
        for size in range(6):
            with self.assertRaises(Exception):
                header(b'\0' * size)

    def test_expired_offer_and_malformed_response(self):
        with self.assertRaises(ConnectError):
            decode_offer(canonical(self.v['offer']), self.v['offer']['expires_at'])
        value = dict(self.v['response'], result=dict(state='invented',events=[],error=None))
        with self.assertRaises(ConnectError):
            response(canonical(value))
