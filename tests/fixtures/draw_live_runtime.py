"""Test-only startup shim for live OLIVE Draw e2e runs with isolated profiles.

It changes one thing: Connect identity keys live in an in-memory vault instead
of the OS Secret Service, so a test never writes to (or waits on) the person's
real keyring. Everything else — Connect TLS, pairing, Draw sync — is the product.
Loaded only through PYTHONPATH set by the e2e spec; no product route imports it.
"""
from olive.bridge.host import Host
from olive.connect.identity import DeviceKeyStore
from tests.test_connect_pairing import MemoryVault

original_start = Host.start


async def start(self, directory):
    await original_start(self, directory)
    self.services.connect.identities.key_store = DeviceKeyStore(MemoryVault())


Host.start = start
