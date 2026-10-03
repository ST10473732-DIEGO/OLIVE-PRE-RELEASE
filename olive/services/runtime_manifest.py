"""Read-only API for olive/runtime_manifest/<version>.json (schema olive-runtime-manifest/3).

The manifest is the only source of what first-run setup may download. Whether setup may
OFFER an entry is decided by three separate gates, in order:

1. licence identified      - a licence and provenance source was located (licence.identified);
2. engineering reviewed    - OLIVE release engineering verified the source, integrity, size,
                             destination and licence metadata (licence.engineering_reviewed,
                             plus every pinned field this module checks);
3. release approved        - the owner intentionally allowed exactly these pinned artefacts into
                             the public OLIVE release. Approvals live in a separate owner-edited
                             file, release-approvals-<version>.json, and each one is bound to the
                             entry's release fingerprint (its pinned URLs, digests, sizes and
                             licence). Change any pin and the approval lapses.

Engineering evidence alone never makes anything installable; neither does an approval
without complete evidence. Nothing here is legal advice or legal approval.

Features name the components they need ("ollama-runtime", "model-fast", ...); profiles are
derived from features, so no model or file name is hard-coded outside this file.

A test manifest can replace the shipped one only through OLIVE_RUNTIME_MANIFEST, and
loopback http:// sources are accepted only when that manifest says "fixture": true AND
OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP=1. Only such a fixture manifest may carry its own
inline "release_approvals"; the shipped manifest never does. Nothing here downloads,
installs or contacts the network.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform as host_platform
import re
import sys
from urllib.parse import urlsplit

DIRECTORY = Path(__file__).resolve().parents[1] / 'runtime_manifest'
SCHEMA = 'olive-runtime-manifest/3'
APPROVALS_SCHEMA = 'olive-release-approvals/1'
TARGETS = ('linux-x86_64', 'windows-x86_64', 'macos-arm64')
KINDS = ('archive', 'file', 'ollama-model', 'python-wheels', 'external')
FORMATS = {'archive': {'tar.zst', 'tar.gz', 'tar.xz', 'zip'}, 'file': {'file'}, 'python-wheels': {'wheels'},
           'ollama-model': {'ollama'}}
# Writable roots under the per-user data folder; a manifest can never name anything else.
ROOTS = {'archive': ('runtime', 'components'), 'file': ('models',), 'python-wheels': ('components',)}
PROFILES = ('core', 'creator', 'complete')
RELEASE_STATES = ('unidentified', 'license_identified', 'engineering_reviewed', 'release_approved')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
ID = re.compile(r'^[a-z0-9][a-z0-9._-]{0,79}$')
PRIVATE_TAG = re.compile(r'(^|/)olive-[a-z0-9-]+', re.I)
MAX_DOWNLOAD = 64 * 1024 ** 3
MANIFEST_VARIABLE = 'OLIVE_RUNTIME_MANIFEST'
LOOPBACK_VARIABLE = 'OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP'
AWAITING_APPROVAL = 'Not yet approved for the public OLIVE release'


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


def approvals_path(version='1.0.0') -> Path:
    return DIRECTORY / f'release-approvals-{version}.json'


def load_approvals(version='1.0.0', path=None) -> dict:
    """The owner's release approvals for the shipped manifest ({} when there are none)."""
    path = Path(path) if path is not None else approvals_path(version)
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    problems = validate_approvals(value)
    if problems:
        raise ValueError('Invalid release approvals: ' + '; '.join(problems))
    return {record['id']: record for record in value['approvals']}


def load(version: str = '1.0.0', environ=None, path=None) -> dict:
    path = Path(path) if path is not None else source_path(environ, version)
    value = json.loads(path.read_text(encoding='utf-8'))
    release = path.resolve() == (DIRECTORY / f'{version}.json').resolve()
    problems = validate(value, allow_loopback_http=loopback_allowed(value, environ), release=release)
    if problems:
        raise ValueError('Invalid runtime manifest: ' + '; '.join(problems))
    value['_source'] = 'release' if release else 'test'
    if release:
        value['_approvals'] = load_approvals(version)
    elif value.get('fixture') is True:
        # Fixture manifests are generated by tests and harnesses; they approve their own fixtures.
        value['_approvals'] = {r['id']: r for r in value.get('release_approvals', [])}
    else:
        value['_approvals'] = {}  # A hand-pointed test manifest is never release-approved.
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
    if entry['kind'] in ('python-wheels', 'file') and entry.get('files'):
        files = entry['files']
        return list(files.get(target) or files.get('any') or [])
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
            and isinstance(item.get('name'), str) and safe_relative(item['name']) and '/' not in item['name']
            and ('path' not in item or safe_relative(item['path'])))


def licence_identified(entry: dict) -> bool:
    licence = entry.get('licence') or {}
    return licence.get('identified') is True and bool(licence.get('spdx'))


def complete(entry: dict, target: str | None = None, allow_loopback_http=False) -> bool:
    """Engineering evidence is complete: source, integrity, size, destination, and a licence
    that was identified AND engineering-reviewed. This is NOT release approval."""
    licence = entry.get('licence') or {}
    if not (licence_identified(entry) and licence.get('engineering_reviewed') is True):
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
        placed = [f.get('path') or f['name'] for f in files]
        if kind == 'file' and len(set(placed)) != len(placed):
            return False
    register = install.get('register')
    if register is not None:
        from .runtime_discovery import NAMES
        if register.get('runtime') not in NAMES or not all(safe_relative(v) for v in register.get('paths', {}).values()):
            return False
    return True


def fingerprint(entry: dict) -> str:
    """What a release approval is bound to: every pin that decides which bytes a user receives
    and under which licence. Any change produces a different fingerprint."""
    pinned = {
        'id': entry.get('id'), 'kind': entry.get('kind'), 'provides': entry.get('provides'),
        'version': entry.get('version'), 'platforms': sorted(entry.get('platforms') or []),
        'licence': (entry.get('licence') or {}).get('spdx'),
        'acceptance_required': bool((entry.get('licence') or {}).get('acceptance_required')),
        'ollama': ({'model': entry['ollama'].get('model'), 'digest': entry['ollama'].get('manifest_digest')}
                   if entry.get('ollama') else None),
        'files': {target: sorted([f.get('name'), f.get('path') or f.get('name'), f.get('url'), f.get('sha256'),
                                  f.get('size_bytes')] for f in files_for(entry, target))
                  for target in sorted(entry.get('platforms') or [])},
        'destination': (entry.get('install') or {}).get('destination'),
    }
    return hashlib.sha256(json.dumps(pinned, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def release_approved(entry: dict, manifest: dict | None) -> bool:
    """The owner approved exactly these pins for the public release."""
    record = ((manifest or {}).get('_approvals') or {}).get(entry.get('id'))
    return (isinstance(record, dict) and record.get('scope') == 'public-release'
            and record.get('fingerprint') == fingerprint(entry)
            and record.get('product_version') == (manifest or {}).get('product_version'))


def release_state(entry: dict, manifest: dict | None = None, target: str | None = None, loopback=False) -> str:
    """unidentified | license_identified | engineering_reviewed | release_approved."""
    if not licence_identified(entry):
        return 'unidentified'
    if entry.get('kind') == 'external' or not complete(entry, target, loopback):
        return 'license_identified'
    return 'release_approved' if release_approved(entry, manifest) else 'engineering_reviewed'


def offerable(entry: dict, target: str | None, manifest: dict | None, loopback=False) -> bool:
    """Setup may offer this entry here: enabled, evidence complete AND release-approved."""
    return bool(target and entry.get('enabled') and target in entry.get('platforms', [])
                and complete(entry, target, loopback) and release_approved(entry, manifest))


def validate(value: dict, allow_loopback_http=False, release=False) -> list[str]:
    problems = []
    if value.get('schema') != SCHEMA:
        problems.append('unknown schema')
    if release and ('release_approvals' in value or value.get('fixture')):
        problems.append('the shipped manifest cannot approve itself or be a fixture; approvals live in '
                        'release-approvals-<version>.json')
    if 'release_approvals' in value and value.get('fixture') is not True:
        problems.append('only fixture manifests may carry inline release approvals')
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
        licence = entry.get('licence') or {}
        if 'reviewed' in licence or 'release_approved' in licence or 'release_approved' in entry:
            problems.append(f'{identifier} uses an ambiguous licence flag; use identified and engineering_reviewed, '
                            'and record release approval in the approvals file')
        if licence.get('engineering_reviewed') and not licence.get('identified'):
            problems.append(f'{identifier} is engineering-reviewed without an identified licence')
        if not set(entry.get('platforms', [])) <= set(TARGETS):
            problems.append(f'{identifier} names an unknown platform')
        provided.add(entry.get('provides'))
        if entry.get('enabled') and entry['kind'] == 'external':
            problems.append(f'{identifier} is external and cannot be enabled')
        elif entry.get('enabled') and not complete(entry, allow_loopback_http=allow_loopback_http):
            problems.append(f'{identifier} is enabled without source, checksum, size, destination and an identified, '
                            'engineering-reviewed licence')
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
    if 'release_approvals' in value:
        problems += validate_approvals({'schema': APPROVALS_SCHEMA, 'approvals': value['release_approvals']})
    return problems


def validate_approvals(value: dict) -> list[str]:
    problems = []
    if value.get('schema') != APPROVALS_SCHEMA:
        problems.append('unknown approvals schema')
    seen = set()
    for record in value.get('approvals', []):
        identifier = record.get('id') if isinstance(record, dict) else None
        if not isinstance(identifier, str) or not ID.match(identifier):
            problems.append(f'approval with invalid id {identifier!r}')
            continue
        if identifier in seen:
            problems.append(f'duplicate approval for {identifier}')
        seen.add(identifier)
        if not SHA256.match(str(record.get('fingerprint', ''))):
            problems.append(f'approval for {identifier} has no fingerprint')
        if record.get('scope') != 'public-release':
            problems.append(f'approval for {identifier} has an unknown scope')
        for key in ('approved_by', 'date', 'product_version'):
            if not isinstance(record.get(key), str) or not record[key].strip():
                problems.append(f'approval for {identifier} has no {key}')
    return problems


def installable(platform_target: str, version: str = '1.0.0', manifest: dict | None = None, environ=None) -> list[dict]:
    """Entries setup may offer for this target (enabled, complete evidence, release-approved)."""
    manifest = manifest if manifest is not None else load(version, environ)
    loopback = loopback_allowed(manifest, environ)
    return [entry for entry in manifest['entries'] if offerable(entry, platform_target, manifest, loopback)]


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


def public_entry(entry: dict, target: str | None, loopback=False, manifest: dict | None = None) -> dict:
    """What the renderer may show: no internal evidence beyond plain facts."""
    licence = entry.get('licence') or {}
    state = release_state(entry, manifest, target if target in entry.get('platforms', []) else None, loopback)
    return {
        'id': entry['id'], 'kind': entry['kind'], 'name': entry['name'], 'provides': entry.get('provides'),
        'version': entry.get('version'),
        'installable': offerable(entry, target, manifest, loopback),
        'release_state': state,
        'validated': bool(target and target in entry.get('validated_platforms', [])),
        'download_bytes': download_bytes(entry, target) if target else 0,
        'installed_bytes': int((entry.get('install') or {}).get('installed_bytes') or entry.get('size_bytes') or 0),
        'licence': {'spdx': licence.get('spdx'), 'name': licence.get('name'), 'url': licence.get('url'),
                    'acceptance_required': bool(licence.get('acceptance_required'))},
        'publisher': (entry.get('source') or {}).get('publisher'),
        'link': (entry.get('source') or {}).get('url') if entry['kind'] == 'external' else None,
        'reason': entry.get('reason') or (AWAITING_APPROVAL if entry.get('enabled') and state == 'engineering_reviewed'
                                          else None),
    }
