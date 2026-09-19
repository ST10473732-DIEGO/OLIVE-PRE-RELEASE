"""Opt-in real OS vault acceptance with two temporary synthetic device profiles."""
from pathlib import Path
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.connect.identity import KEY_REFERENCE
from olive.connect.service import DesktopDeviceService
from olive.services.credential_vault import CredentialVault


def main():
    with tempfile.TemporaryDirectory(prefix='olive-c2-vault-') as directory:
        roots = [Path(directory) / name for name in ('laptop', 'synthetic-peer')]
        vaults = [CredentialVault(root) for root in roots]
        devices = []
        try:
            devices = [DesktopDeviceService(root) for root in roots]
            a, b = devices
            first = a.cryptographic_identity()
            assert first == a.cryptographic_identity()
            a.close()
            a = DesktopDeviceService(roots[0])
            devices[0] = a
            assert a.cryptographic_identity() == first
            offer = a.pairing.create_offer()
            sid = json.loads(offer)['session_id']
            a.pairing.receive_reply(b.pairing.accept_offer(offer))
            def pump():
                pending = b''
                for _ in range(8):
                    pending = a.pairing.exchange(sid, b.pairing.exchange(sid, pending))
            pump()
            # Synthetic humans explicitly compare the two independently derived values.
            left, right = a.pairing.preview(sid), b.pairing.preview(sid)
            assert left['comparison'] == right['comparison']
            a.pairing.confirm(sid, right['comparison'])
            b.pairing.confirm(sid, left['comparison'])
            pump()
            peer = a.pairing.complete(sid)
            b.pairing.complete(sid)
            assert peer['permissions'] == []
            a.revoke(peer['device_id'])
            for vault, root in zip(vaults, roots):
                secret = vault.read_for_provider(KEY_REFERENCE)
                assert secret.encode() not in (root / 'connect' / 'devices.sqlite3').read_bytes()
            print('Real vault: identity creation, restart, mutual TLS pairing and revocation passed.')
        finally:
            for device in devices:
                device.close()
            for vault in vaults:
                vault.remove(KEY_REFERENCE)
                assert not vault.contains(KEY_REFERENCE)
            print('Synthetic identity slots removed; no personal credentials used.')


if __name__ == '__main__':
    main()
