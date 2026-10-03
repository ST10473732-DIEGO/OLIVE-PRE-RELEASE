"""Read-only API for olive/runtime_manifest/<version>.json (schema olive-runtime-manifest/2).

The manifest is the only source of what first-run setup may download. An entry is
installable only when it is enabled AND its source, integrity (SHA-256 or an Ollama
registry manifest digest), size, destination and a reviewed licence are recorded, and
its source URL is HTTPS on a host the entry names. Features name the components they
need ("ollama-runtime", "model-fast", ...); profiles are derived from features, so no
model or file name is hard-coded outside this file.

A test manifest can replace the shipped one only through OLIVE_RUNTIME_MANIFEST, and
loopback http:// sources are accepted only when that manifest says "fixture": true AND
OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP=1. Both are explicit and reported by setup status.
Nothing here downloads, installs or contacts the network.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform as host_platform
import re
import sys
from urllib.parse import urlsplit

DIRECTORY = Path(__file__).resolve().parents[1] / 'runtime_manifest'
SCHEMA = 'olive-runtime-manifest/2'
TARGETS = ('linux-x86_64', 'windows-x86_64', 'macos-arm64')
KINDS = ('archive', 'file', 'ollama-model', 'python-wheels', 'external')
FORMATS = {'archive': {'tar.zst', 'tar.gz', 'tar.xz', 'zip'}, 'file': {'file'}, 'python-wheels': {'wheels'},
           'ollama-model': {'ollama'}}
# Writable roots under the per-user data folder; a manifest can never name anything else.
ROOTS = {'archive': ('runtime', 'components'), 'file': ('models',), 'python-wheels': ('components',)}
PROFILES = ('core', 'creator', 'complete')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
ID = re.compile(r'^[a-z0-9][a-z0-9._-]{0,79}$')
PRIVATE_TAG = re.compile(r'(^|/)olive-[a-z0-9-]+', re.I)
MAX_DOWNLOAD = 64 * 1024 ** 3
MANIFEST_VARIABLE = 'OLIVE_RUNTIME_MANIFEST'
LOOPBACK_VARIABLE = 'OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP'


def platform_target(platform=None, machine=None) -> str | None:
    platform = sys.platform if platform is None else platform
    machine = (host_platform.machine() if machine is None else machine).lower()
    x86 = machine in {'x86_64', 'amd64'}
    if platform.startswith('linux') and x86:
        return 'linux-x86_64'
    if platform == 'win32' and x86:
        return 'windows-x86_64'
    if platform == 'darwin' and machine in {'arm64', 'aarch64'}:
        return 'macos-arm64'
    return None


def source_path(environ=None, version='1.0.0') -> Path:
    env = os.environ if environ is None else environ
    override = env.get(MANIFEST_VARIABLE, '')
    return Path(override) if override else DIRECTORY / f'{version}.json'


def loopback_allowed(manifest: dict, environ=None) -> bool:
    env = os.environ if environ is None else environ
    return manifest.get('fixture') is True and env.get(LOOPBACK_VARIABLE) == '1'


def load(version: str = '1.0.0', environ=None, path=None) -> dict:
    path = Path(path) if path is not None else source_path(environ, version)
    value = json.loads(path.read_text(encoding='utf-8'))
    problems = validate(value, allow_loopback_http=loopback_allowed(value, environ))
    if problems:
        raise ValueError('Invalid runtime manifest: ' + '; '.join(problems))
    value['_source'] = 'test' if path.resolve() != (DIRECTORY / f'{version}.json').resolve() else 'release'
    return value


def url_allowed(url, hosts, allow_loopback_http=False) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.username or parts.password or not parts.hostname:
        return False
    if parts.scheme == 'https':
        return parts.hostname.lower() in {h.lower() for h in hosts}
    if parts.scheme == 'http' and allow_loopback_http:
        try:
            return ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            return False
    return False


def safe_relative(path) -> bool:
    if not isinstance(path, str) or not path or '\\' in path or ':' in path or '\x00' in path:
        return False
    pure = PurePosixPath(path)
    return not pure.is_absolute() and all(part not in {'', '.', '..'} for part in pure.parts)


def files_for(entry: dict, target: str) -> list[dict]:
    """The exact files an entry downloads for one platform target."""
    if entry['kind'] == 'python-wheels':
        return list((entry.get('files') or {}).get(target, []))
    if entry['kind'] in ('archive', 'file') and entry['source'].get('url'):
        name = PurePosixPath(urlsplit(entry['source']['url']).path).name
        return [{'name': name, 'url': entry['source']['url'], 'sha256': entry.get('sha256'),
                 'size_bytes': entry.get('size_bytes')}]
    return []


def download_bytes(entry: dict, target: str) -> int:
    if entry['kind'] == 'ollama-model':
        return int(entry.get('size_bytes') or 0)
    return sum(int(f.get('size_bytes') or 0) for f in files_for(entry, target))


def _file_complete(item, hosts, loopback) -> bool:
    return (isinstance(item, dict) and url_allowed(item.get('url', ''), hosts, loopback)
            and isinstance(item.get('sha256'), str) and bool(SHA256.match(item['sha256']))
            and type(item.get('size_bytes')) is int and 0 < item['size_bytes'] <= MAX_DOWNLOAD
            and isinstance(item.get('name'), str) and safe_relative(item['name']) and '/' not in item['name'])


def complete(entry: dict, target: str | None = None, allow_loopback_http=False) -> bool:
    """Source, integrity, size, destination and a reviewed licence are all recorded."""
    licence = entry.get('licence') or {}
    if not (licence.get('spdx') and licence.get('reviewed') is True):
        return False
    kind, install = entry.get('kind'), entry.get('install') or {}
    if kind not in FORMATS or install.get('format') not in FORMATS[kind]:
        return False
    hosts = (entry.get('source') or {}).get('hosts') or []
    if kind == 'ollama-model':
        ollama = entry.get('ollama') or {}
        return (isinstance(ollama.get('model'), str) and bool(ollama['model'])
                and not PRIVATE_TAG.search(ollama['model'])
                and isinstance(ollama.get('manifest_digest'), str) and bool(SHA256.match(ollama['manifest_digest']))
                and type(entry.get('size_bytes')) is int and entry['size_bytes'] > 0
                and url_allowed((entry.get('source') or {}).get('url', ''), hosts, allow_loopback_http))
    destination = install.get('destination')
    if not safe_relative(destination) or PurePosixPath(destination).parts[0] not in ROOTS[kind]:
        return False
    if not all(safe_relative(e) for e in install.get('executables', [])):
        return False
    targets = [target] if target else entry.get('platforms', [])
    for each in targets:
        files = files_for(entry, each)
        if not files or not all(_file_complete(f, hosts, allow_loopback_http) for f in files):
            return False
    register = install.get('register')
    if register is not None:
        from .runtime_discovery import NAMES
        if register.get('runtime') not in NAMES or not all(safe_relative(v) for v in register.get('paths', {}).values()):
            return False
    return True


def validate(value: dict, allow_loopback_http=False) -> list[str]:
    problems = []
    if value.get('schema') != SCHEMA:
        problems.append('unknown schema')
    ids, provided = set(), set()
    for entry in value.get('entries', []):
        identifier = entry.get('id', '?')
        if not isinstance(identifier, str) or not ID.match(identifier):
            problems.append(f'invalid id {identifier!r}')
        if identifier in ids:
            problems.append(f'duplicate id {identifier}')
        ids.add(identifier)
        if entry.get('kind') not in KINDS:
            problems.append(f'{identifier} has an unknown kind')
            continue
        if not set(entry.get('platforms', [])) <= set(TARGETS):
            problems.append(f'{identifier} names an unknown platform')
        provided.add(entry.get('provides'))
        if entry.get('enabled') and entry['kind'] == 'external':
            problems.append(f'{identifier} is external and cannot be enabled')
        elif entry.get('enabled') and not complete(entry, allow_loopback_http=allow_loopback_http):
            problems.append(f'{identifier} is enabled without source, checksum, size, destination and reviewed licence')
        if entry.get('sha256') is not None and not SHA256.match(str(entry['sha256'])):
            problems.append(f'{identifier} has a malformed sha256')
        if entry['kind'] == 'ollama-model' and PRIVATE_TAG.search(str((entry.get('ollama') or {}).get('model', ''))):
            problems.append(f'{identifier} names a private olive-* Ollama tag')
        if not entry.get('enabled') and not entry.get('reason'):
            problems.append(f'{identifier} is disabled without a reason')
    profiles = value.get('profiles', {})
    if set(profiles) != set(PROFILES):
        problems.append('profiles must be core, creator and complete')
    for name, profile in profiles.items():
        for included in profile.get('includes', []):
            if included not in profiles:
                problems.append(f'profile {name} includes unknown profile {included}')
    for feature in value.get('features', []):
        if feature.get('profile') not in profiles:
            problems.append(f"feature {feature.get('id')} names an unknown profile")
        for slot in feature.get('requires', []) + feature.get('optional', []):
            if slot not in provided:
                problems.append(f"feature {feature.get('id')} needs {slot}, which no entry provides")
    return problems


def installable(platform_target: str, version: str = '1.0.0', manifest: dict | None = None, environ=None) -> list[dict]:
    """Entries setup may offer for this target."""
    manifest = manifest if manifest is not None else load(version, environ)
    loopback = loopback_allowed(manifest, environ)
    return [entry for entry in manifest['entries']
            if entry['enabled'] and platform_target in entry['platforms']
            and complete(entry, platform_target, loopback)]


def profile_chain(manifest: dict, profile: str) -> list[str]:
    """A profile and everything it includes, innermost first (core, creator, complete)."""
    if profile not in manifest['profiles']:
        raise ValueError('Unknown OLIVE package')
    seen: list[str] = []

    def visit(name):
        if name in seen:
            return
        for included in manifest['profiles'][name].get('includes', []):
            visit(included)
        seen.append(name)
    visit(profile)
    return seen


def profile_features(manifest: dict, profile: str) -> list[dict]:
    chain = profile_chain(manifest, profile)
    return [f for f in manifest['features'] if f['profile'] in chain]


def providers(manifest: dict, slot: str, target: str | None) -> list[dict]:
    return [e for e in manifest['entries'] if e.get('provides') == slot and (target is None or target in e['platforms'])]


def public_entry(entry: dict, target: str | None, loopback=False) -> dict:
    """What the renderer may show: no internal evidence beyond plain facts."""
    licence = entry.get('licence') or {}
    return {
        'id': entry['id'], 'kind': entry['kind'], 'name': entry['name'], 'provides': entry.get('provides'),
        'version': entry.get('version'),
        'installable': bool(target and entry['enabled'] and target in entry['platforms']
                            and complete(entry, target, loopback)),
        'validated': bool(target and target in entry.get('validated_platforms', [])),
        'download_bytes': download_bytes(entry, target) if target else 0,
        'installed_bytes': int((entry.get('install') or {}).get('installed_bytes') or entry.get('size_bytes') or 0),
        'licence': {'spdx': licence.get('spdx'), 'name': licence.get('name'), 'url': licence.get('url'),
                    'acceptance_required': bool(licence.get('acceptance_required'))},
        'publisher': (entry.get('source') or {}).get('publisher'),
        'link': (entry.get('source') or {}).get('url') if entry['kind'] == 'external' else None,
        'reason': entry.get('reason'),
    }
