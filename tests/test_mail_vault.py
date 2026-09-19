"""Dummy current-user vault entries scoped to newly created temporary profiles."""
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
from olive.services.credential_vault import CredentialVault


@unittest.skipUnless(sys.platform=='win32','Windows Credential Manager is Windows-only')
class MailVaultTests(unittest.TestCase):
    def test_dummy_store_provider_read_cross_profile_and_delete(self):
        with tempfile.TemporaryDirectory() as one,tempfile.TemporaryDirectory() as two:
            first=CredentialVault(Path(one));second=CredentialVault(Path(two));reference='mail-'+uuid.uuid4().hex
            try:
                first.put(reference,'OLIVE dummy fixture credential')
                self.assertEqual(first.read_for_provider(reference),'OLIVE dummy fixture credential')
                with self.assertRaises(Exception):second.read_for_provider(reference)
                self.assertFalse(any(Path(one).iterdir()))
            finally:first.remove(reference)
            with self.assertRaises(Exception):first.read_for_provider(reference)

    def test_vault_failure_has_no_plaintext_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            vault=CredentialVault(Path(directory));reference='mail-'+uuid.uuid4().hex
            with patch('win32cred.CredWrite',side_effect=OSError('controlled vault failure')):
                with self.assertRaises(OSError):vault.put(reference,'dummy secret')
            self.assertEqual(list(Path(directory).iterdir()),[])
            with self.assertRaises(ValueError):vault._target('../unrelated')
