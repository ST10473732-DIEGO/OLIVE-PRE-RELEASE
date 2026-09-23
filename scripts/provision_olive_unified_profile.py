"""Apply/restore this owner's requested setup once, through profile repositories.

Never called at startup. A receipt is exclusive, so revocation cannot be silently
undone by rerunning a launch or by a model tool.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.identity import resolve_profile
from olive.storage.settings_repository import SettingsRepository
from olive.agent.permission_service import PermissionService

FIELDS = dict(enabled=True, trusted_tasks=True, screen_observation=True,
              uia=True, keyboard_policy='allow', mouse_policy='allow')
PERMISSIONS = {'desktop.keyboard_input': 'allow', 'desktop.mouse_input': 'allow'}


def provision(profile, receipt, restore=False):
    settings_repo = SettingsRepository(profile / 'settings.json')
    permissions = PermissionService(profile / 'permissions.json')
    settings, policies = settings_repo.load(), permissions.policies()
    previous = settings.get('desktop_control', {})
    if restore:
        saved = json.loads(receipt.read_text())
        if saved['profile'] != str(profile.resolve()):
            raise ValueError('Receipt belongs to a different profile')
        for current, expected in ((previous, FIELDS), (policies['permissions'], PERMISSIONS)):
            if any(current.get(k) != v for k, v in expected.items()):
                raise ValueError('Scoped settings changed since setup; refusing replacement')
        for current, values in ((previous, saved['settings']), (policies['permissions'], saved['permissions'])):
            for key, value in values.items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = value
    else:
        saved = {'schema': 1, 'authority': 'Owner unified-agent setup request',
                 'profile': str(profile.resolve()),
                 'settings': {key: previous.get(key) for key in FIELDS},
                 'permissions': {key: policies['permissions'].get(key) for key in PERMISSIONS}}
        receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(saved, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        previous.update(FIELDS)
        policies['permissions'].update(PERMISSIONS)
    settings['desktop_control'] = previous
    permissions.save(policies['permissions'], policies['scopes'], policies['trusted_actions'])
    settings_repo.save(settings)
    return {'setup': 'restored' if restore else 'applied', 'schema': 1}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(provision(args.profile or resolve_profile(), args.receipt, args.restore)))
