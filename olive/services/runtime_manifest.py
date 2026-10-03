"""Read-only API boundary for olive/runtime_manifest/<version>.json.

A future setup step asks `installable()` what it may offer. An entry qualifies only
when it is enabled AND has a source URL, SHA-256, size and a reviewed licence.
Nothing here downloads, installs or contacts the network.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[1] / 'runtime_manifest'
SCHEMA = 'olive-runtime-manifest/1'
SHA256 = re.compile(r'^[0-9a-f]{64}$')
PRIVATE_TAG = re.compile(r'\bolive-[a-z0-9-]+', re.I)


def load(version: str = '1.0.0') -> dict:
    value = json.loads((DIRECTORY / f'{version}.json').read_text(encoding='utf-8'))
    problems = validate(value)
    if problems:
        raise ValueError('Invalid runtime manifest: ' + '; '.join(problems))
    return value


def complete(entry: dict) -> bool:
    """Source, checksum, size and a reviewed licence are all recorded."""
    return bool(entry['source'].get('url') and isinstance(entry.get('sha256'), str) and SHA256.match(entry['sha256'])
                and isinstance(entry.get('size_bytes'), int) and entry['size_bytes'] > 0
                and entry['licence'].get('spdx') and entry['licence'].get('reviewed') is True)


def validate(value: dict) -> list[str]:
    problems = []
    if value.get('schema') != SCHEMA:
        problems.append('unknown schema')
    ids = set()
    for entry in value.get('entries', []):
        identifier = entry.get('id', '?')
        if identifier in ids:
            problems.append(f'duplicate id {identifier}')
        ids.add(identifier)
        if entry.get('enabled') and not complete(entry):
            problems.append(f'{identifier} is enabled without source, checksum, size and reviewed licence')
        if entry.get('sha256') is not None and not SHA256.match(str(entry['sha256'])):
            problems.append(f'{identifier} has a malformed sha256')
        if entry.get('kind') == 'ollama-model' and PRIVATE_TAG.search(str(entry.get('install', {}).get('relative_path', ''))):
            problems.append(f'{identifier} names a private olive-* Ollama tag')
    for name, members in value.get('profiles', {}).items():
        for member in members:
            if member not in ids:
                problems.append(f'profile {name} references unknown entry {member}')
    return problems


def installable(platform_target: str, version: str = '1.0.0') -> list[dict]:
    """Entries a setup step may offer for this target (none in OLIVE 1.0 PASS 2B)."""
    return [entry for entry in load(version)['entries']
            if entry['enabled'] and complete(entry) and platform_target in entry['platforms']]
