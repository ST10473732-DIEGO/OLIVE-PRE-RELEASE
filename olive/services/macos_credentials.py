"""macOS Keychain adapter. No files, no plaintext fallback, no cryptography of our own.

Uses keyring's macOS backend, which calls the Security framework
(SecItemAdd / SecItemCopyMatching / SecItemDelete) on the user's default
keychain. Items are generic passwords: service "OLIVE", account = the namespaced
credential reference. The backend is selected explicitly, so another installed
keyring backend can never be picked instead.
"""
from ..platform_support import PlatformUnavailable

UNAVAILABLE = ('Secure credential storage is unavailable or locked. Unlock the macOS login keychain '
               'and retry. No plaintext fallback was used.')
SERVICE = 'OLIVE'


def backend():
    try:
        from keyring.backends import macOS
        macOS.Keyring.priority  # Raises unless this is macOS with the Security API.
        return macOS.Keyring()
    except Exception:
        raise PlatformUnavailable(UNAVAILABLE) from None


def available():
    try:
        backend()
        return True
    except PlatformUnavailable:
        return False


def operate(action, target, secret=None):
    keychain = backend()
    try:
        if action == 'put':
            keychain.set_password(SERVICE, target, secret)
            return None
        current = keychain.get_password(SERVICE, target)
        if action == 'contains':
            return current is not None
        if action == 'remove':
            if current is not None:
                keychain.delete_password(SERVICE, target)
            return None
        if current is None:
            raise PlatformUnavailable(UNAVAILABLE)
        return current
    except PlatformUnavailable:
        raise
    except Exception:
        # Locked or denied keychains and Security errors never leak provider text.
        raise PlatformUnavailable(UNAVAILABLE) from None
