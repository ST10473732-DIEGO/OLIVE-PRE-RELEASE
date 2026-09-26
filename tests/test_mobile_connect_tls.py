"""Actual mobile C adapter vs desktop PairingTLS, using disposable keys only."""
import base64
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from olive.connect.identity import public_identity, validate_public
from olive.connect.pairing_wire import PairingTLS

ROOT = Path(__file__).resolve().parents[1]
OPENSSL = Path(os.environ.get('OLIVE_HOST_OPENSSL', '/opt/homebrew/opt/openssl@3'))

@unittest.skipUnless(sys.platform == 'darwin' and (OPENSSL / 'include/openssl/ssl.h').is_file(), 'Mac native adapter harness requires local OpenSSL development headers')
class MobileConnectTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='olive-mobile-tls-')
        library = Path(cls.tmp.name) / 'adapter.dylib'
        subprocess.run(['clang', '-dynamiclib', '-I'+str(OPENSSL/'include'),
                        str(ROOT/'mobile/ios/NativeConnect/OliveTLS.c'), '-L'+str(OPENSSL/'lib'),
                        '-lssl','-lcrypto','-o',str(library)],check=True,capture_output=True)
        cls.lib = ctypes.CDLL(str(library))
        byteptr = ctypes.c_void_p
        cls.lib.olive_certificate_create.argtypes = [byteptr, ctypes.c_char_p, ctypes.c_int64, byteptr, ctypes.c_size_t]
        cls.lib.olive_tls_create.argtypes = [byteptr,byteptr,ctypes.c_size_t,byteptr,ctypes.c_size_t]
        cls.lib.olive_tls_create.restype = ctypes.c_void_p
        for name in ('feed','drain','read','write'):
            getattr(cls.lib,'olive_tls_'+name).argtypes = [byteptr,byteptr,ctypes.c_size_t]
        cls.lib.olive_tls_handshake.argtypes = [byteptr]
        cls.lib.olive_tls_comparison.argtypes = [byteptr,byteptr,byteptr]
        cls.lib.olive_tls_free.argtypes = [byteptr]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def local(self):
        key = Ed25519PrivateKey.generate()
        seed = key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
        device = str(uuid.uuid4()); now = int(time.time())
        buf = ctypes.create_string_buffer(1536)
        size = self.lib.olive_certificate_create(seed,device.encode(),now,buf,len(buf))
        self.assertGreater(size,0)
        der = buf.raw[:size]
        public = dict(device_id=device,algorithm='olive-ed25519-x509/1',key_version=1,created_at=now,certificate=base64.b64encode(der).decode())
        self.assertEqual(validate_public(public).public_key(),key.public_key())
        return seed, public, der

    def handshake(self, wrong_pin=False, same_key=False):
        seed, local, der = self.local()
        key = Ed25519PrivateKey.generate()
        peer = public_identity(str(uuid.uuid4()),key,int(time.time()))
        pin = public_identity(peer['device_id'] if same_key else str(uuid.uuid4()),key if same_key else Ed25519PrivateKey.generate(),int(time.time())) if wrong_pin else peer
        pin_der = base64.b64decode(pin['certificate'])
        client = self.lib.olive_tls_create(seed,der,len(der),pin_der,len(pin_der))
        self.assertTrue(client)
        binding = bytes(range(32))
        server = PairingTLS(key,peer,local,server=True,binding=binding)
        buf = ctypes.create_string_buffer(32768)
        try:
            ready = 0
            for _ in range(20):
                ready = self.lib.olive_tls_handshake(client)
                if ready < 0: break
                n = self.lib.olive_tls_drain(client,buf,len(buf)); self.assertGreaterEqual(n,0)
                out = server.step(buf.raw[:n])
                self.assertEqual(self.lib.olive_tls_feed(client,out,len(out)),len(out))
                if ready and server.ready: break
            if wrong_pin:
                self.assertEqual(ready,-1); return
            self.assertEqual(ready,1); self.assertTrue(server.ready)
            exported = ctypes.create_string_buffer(32)
            self.assertEqual(self.lib.olive_tls_comparison(client,binding,exported),1)
            self.assertEqual(exported.raw.hex(':').upper(),server.comparison())
            message = b'OLIVE-CONFIRM/1:'+binding
            self.assertEqual(self.lib.olive_tls_write(client,message,len(message)),len(message))
            n=self.lib.olive_tls_drain(client,buf,len(buf)); server.step(buf.raw[:n])
            self.assertEqual(server.receive_confirmation(),message)
        finally:
            self.lib.olive_tls_free(client); server.close()

    def test_mutual_tls_exporter_and_confirmation(self):
        self.handshake()

    def test_wrong_certificate_pin_rejected(self):
        self.handshake(wrong_pin=True)

    def test_same_key_different_certificate_rejected(self):
        self.handshake(wrong_pin=True, same_key=True)
