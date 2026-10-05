"""<profile>/setup.json: first-run setup progress (ordinary status only, never credentials).

Persisted states:
    not_started  a new profile; setup has not been opened yet
    in_progress  the wizard is open or was left part-way (step and package are kept)
    complete     verification passed for the chosen package
    skipped      the person chose to set up later
    existing     the profile held OLIVE data before setup existed; nothing is forced

"Requires repair" is derived at read time (olive.services.first_run), never stored.
An unreadable file is reported and never silently replaced.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .json_store import JsonStore

SCHEMA = 'olive-setup/1'
FILENAME = 'setup.json'
STATES = ('not_started', 'in_progress', 'complete', 'skipped', 'existing')
STEPS = ('welcome', 'name', 'system', 'package', 'runtimes', 'models', 'verify', 'connect', 'world', 'complete')
PROFILES = ('core', 'creator', 'complete')
ENTRY = re.compile(r'^[a-z0-9][a-z0-9._-]{0,79}$')
# Files whose presence before setup existed marks a profile that is already in use.
USER_DATA = ('settings.json', 'chats.json', 'memories.json', 'rag.sqlite3', 'runtimes.json', 'chats',
             'notes.sqlite3', 'drawings.sqlite3', 'connect')


VERIFIED = ('python', 'torch', 'torch_cuda', 'cuda_available', 'cudnn', 'device', 'comfyui', 'core_nodes')


def _clean_installed(value) -> dict:
    result = {}
    if not isinstance(value, dict):
        return result
    for key, record in value.items():
        if not isinstance(key, str) or not ENTRY.match(key) or not isinstance(record, dict):
            continue
        result[key] = {k: v for k, v in record.items()
                       if k in {'kind', 'version', 'path', 'sha256', 'digest', 'model', 'installed_at', 'installed_by_olive',
                                'runtime'}
                       and isinstance(v, (str, int, float, bool))}
        # Model sets (kind "file") record each placed file; additive, older readers ignore it.
        files = record.get('files')
        if isinstance(files, list):
            result[key]['files'] = [{'path': f['path'], 'sha256': f['sha256'], 'size_bytes': f['size_bytes']}
                                    for f in files[:64] if isinstance(f, dict) and isinstance(f.get('path'), str)
                                    and isinstance(f.get('sha256'), str) and type(f.get('size_bytes')) is int]
        # A runtime with direct-download wheels (Creator) records each wheel and its runtime check.
        wheels = record.get('direct_wheels')
        if isinstance(wheels, list):
            result[key]['direct_wheels'] = [{'name': w['name'], 'sha256': w['sha256']} for w in wheels[:64]
                                            if isinstance(w, dict) and isinstance(w.get('name'), str)
                                            and isinstance(w.get('sha256'), str)]
        verified = record.get('verified')
        if isinstance(verified, dict):
            result[key]['verified'] = {k: v for k, v in verified.items() if isinstance(k, str) and k in VERIFIED
                                       and (v is None or isinstance(v, (str, int, float, bool)))}
    return result


class SetupStateRepository:
    def __init__(self, profile: Path):
        self.profile = Path(profile)
        self.path = self.profile / FILENAME

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> tuple[dict[str, Any], bool]:
        """(state, readable)."""
        if not self.path.exists():
            return self.default('not_started'), True
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return self.default('not_started'), False
        if not isinstance(value, dict) or value.get('schema') != SCHEMA or value.get('state') not in STATES:
            return self.default('not_started'), False
        state = self.default(value['state'])
        state['step'] = value.get('step') if value.get('step') in STEPS else 'welcome'
        state['profile'] = value.get('profile') if value.get('profile') in PROFILES else None
        state['optional'] = [v for v in value.get('optional', []) if isinstance(v, str) and ENTRY.match(v)][:32]
        for key in ('started_at', 'updated_at', 'completed_at'):
            state[key] = value.get(key) if isinstance(value.get(key), (int, float)) else None
        state['origin'] = value.get('origin') if value.get('origin') in {'new', 'existing-profile'} else 'new'
        state['verified_features'] = [v for v in value.get('verified_features', []) if isinstance(v, str)][:64]
        state['installed'] = _clean_installed(value.get('installed'))
        state['product_version'] = str(value.get('product_version', ''))[:32]
        return state, True

    @staticmethod
    def default(state='not_started') -> dict[str, Any]:
        return {'schema': SCHEMA, 'state': state, 'step': 'welcome', 'profile': None, 'optional': [],
                'started_at': None, 'updated_at': None, 'completed_at': None, 'origin': 'new',
                'verified_features': [], 'installed': {}, 'product_version': ''}

    def save(self, state: dict[str, Any]) -> None:
        if state.get('state') not in STATES:
            raise ValueError('Unknown setup state')
        clean = self.default(state['state'])
        clean.update({k: state[k] for k in clean if k in state and k != 'schema'})
        clean['installed'] = _clean_installed(state.get('installed'))
        JsonStore(self.path).write(clean)

    def set_aside(self, suffix: str) -> Path | None:
        """Keep an unreadable file next to the new one instead of overwriting it."""
        if not self.path.exists():
            return None
        target = self.path.with_name(f'{FILENAME}.unreadable-{suffix}')
        self.path.replace(target)
        return target

    @staticmethod
    def profile_in_use(profile: Path) -> bool:
        profile = Path(profile)
        return any((profile / name).exists() for name in USER_DATA)
