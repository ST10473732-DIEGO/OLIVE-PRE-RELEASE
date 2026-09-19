"""Opt-in synthetic Secret Service/Mail acceptance; never contacts real providers."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.services.credential_vault import CredentialVault
from olive.mail.connections import Connections
from olive.mail.store import MailStore
from olive.mail.google_auth import GoogleAuth, CLIENT_REF
from tests.test_mail_google import GoogleAuthTests


class TrackedVault(CredentialVault):
    def __init__(self, profile):
        super().__init__(profile)
        self.refs = set()

    def put(self, reference, secret):
        self.refs.add(reference)
        return super().put(reference, secret)

    def cleanup(self):
        for reference in self.refs:
            self.remove(reference)


class NativeGoogleTests(GoogleAuthTests):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-l3-google-')
        self.root = Path(self.temp.name)
        self.vault = TrackedVault(self.root)
        self.store = MailStore(self.root / 'mail.sqlite3')
        self.connections = Connections(self.store, self.vault)
        self.auth = GoogleAuth(self.connections)
        self.connections.google = self.auth
        self.vault.put(CLIENT_REF, json.dumps({
            'client_id': 'fixture.apps.googleusercontent.com', 'client_secret': 'synthetic-client'}))

    def tearDown(self):
        self.auth.close()
        try:
            self.vault.cleanup()
        finally:
            super().tearDown()


def main():
    if sys.platform != 'linux':
        raise SystemExit('This opt-in acceptance script requires Linux Secret Service.')
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(NativeGoogleTests))
    with tempfile.TemporaryDirectory(prefix='olive-l3-mail-vault-') as directory:
        vault = TrackedVault(directory)
        connections = Connections(MailStore(Path(directory) / 'mail.sqlite3'), vault)
        try:
            for name, host in [('IMAP', '127.0.0.1'), ('SMTP', '127.0.0.1'),
                               ('iCloud app password', 'imap.mail.me.com')]:
                row = connections.save({'name': name, 'username': 'synthetic@example.invalid',
                    'imap': {'host': host, 'port': 993, 'tls': 'tls'},
                    'smtp': {'host': '127.0.0.1', 'port': 465, 'tls': 'tls'}})
                row = connections.store_secret(row['id'], row['revision'], 'synthetic-L3-app-password')
                assert connections.secret(row) == 'synthetic-L3-app-password'
                assert not row['enabled'] and row['state'] == 'disconnected'
            assert b'synthetic-L3-app-password' not in (Path(directory) / 'mail.sqlite3').read_bytes()
            print('Generic IMAP/SMTP and iCloud synthetic credential readiness passed; no provider contacted')
        finally:
            vault.cleanup()
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
