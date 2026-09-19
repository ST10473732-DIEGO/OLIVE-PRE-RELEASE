"""Windows-owned credentials, separate from portable application data."""
import hashlib
import re
import sys
from pathlib import Path
from ..platform_support import require_windows


class CredentialVault:
    @property
    def available(self):
        return sys.platform == 'win32'

    def __init__(self, profile):
        self.namespace = 'DMDO/' + hashlib.sha256(str(Path(profile).resolve()).casefold().encode()).hexdigest()

    def _target(self, reference):
        if reference not in {'discord-bot'} and not (isinstance(reference, str) and re.fullmatch(r'mail-[a-f0-9]{32}', reference)):
            raise ValueError('Unknown credential reference')
        return self.namespace + '/' + reference

    def put(self, reference, secret):
        require_windows('Secure credential storage')
        import win32cred
        if not isinstance(secret,str) or not secret or '\0' in secret or len(secret.encode('utf-16-le')) > 2500:
            raise ValueError('Invalid credential length')
        win32cred.CredWrite({'Type':win32cred.CRED_TYPE_GENERIC, 'TargetName':self._target(reference),
            'UserName':'OLIVE', 'CredentialBlob':secret, 'Comment':'OLIVE UTF-16LE credential',
            'Persist':win32cred.CRED_PERSIST_LOCAL_MACHINE}, 0)

    def read_for_provider(self, reference):
        require_windows('Secure credential storage')
        import win32cred
        value = win32cred.CredRead(self._target(reference), win32cred.CRED_TYPE_GENERIC, 0)
        blob=value['CredentialBlob']
        if isinstance(blob,str):return blob
        return blob.decode('utf-16-le' if value.get('Comment')=='OLIVE UTF-16LE credential' else 'utf-8')

    def remove(self, reference):
        require_windows('Secure credential storage')
        import win32cred
        try:
            win32cred.CredDelete(self._target(reference), win32cred.CRED_TYPE_GENERIC, 0)
        except Exception as error:
            if getattr(error, 'winerror', None) != 1168:
                raise RuntimeError('Could not remove the stored credential') from None
