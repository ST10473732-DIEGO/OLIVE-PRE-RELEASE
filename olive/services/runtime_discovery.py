"""Locate OLIVE-owned runtimes without a launcher script exporting their paths.

Each runtime resolves in this fixed order (docs/architecture/packaging.md):

1. Environment override - developer/admin variables (OLIVE_COMFY_ROOT, ...).
   Authoritative while set; an invalid override is reported, never bypassed.
2. Persisted choice - <profile>/runtimes.json. A stale path reports Needs setup;
   OLIVE does not quietly fall back to another installation.
3. Discovery - OLIVE-owned folders under the per-user runtime root, then (source
   checkouts only) the repository's ignored .toolchains/.media-runtime folders,
   then, for Ollama only, a system installation. The first tier with a match wins;
   two different matches in one tier are a conflict that needs an explicit choice.
   An unambiguous OLIVE-owned match is adopted into runtimes.json in place: nothing
   is moved or copied.
4. Nothing found - Needs setup.

Only paths and provenance are stored. Nothing here starts, downloads or deletes anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Callable

from .. import app_paths
from ..storage.runtime_config_repository import RuntimeConfigRepository

log = logging.getLogger(__name__)

NAMES = ('ollama', 'comfy', 'video_comfy', 'voicestudio', 'media_models')
LABELS = {'ollama': 'Ollama', 'comfy': 'Image engine (ComfyUI)', 'video_comfy': 'Video engine (ComfyUI)',
          'voicestudio': 'Audio engine (VoiceStudio)', 'media_models': 'Image model store'}
ENVIRONMENT = {
    'ollama': {'executable': 'OLIVE_OLLAMA_EXECUTABLE'},
    'comfy': {'root': 'OLIVE_COMFY_ROOT', 'python': 'OLIVE_COMFY_PYTHON'},
    'video_comfy': {'root': 'OLIVE_VIDEO_COMFY_ROOT', 'python': 'OLIVE_VIDEO_COMFY_PYTHON'},
    'voicestudio': {'root': 'OLIVE_VOICESTUDIO_ROOT', 'url': 'OLIVE_VOICESTUDIO_URL'},
    'media_models': {'path': 'OLIVE_MEDIA_MODELS'},
}
VOICESTUDIO_URL = 'http://127.0.0.1:3900'
# Where each runtime's owned lifecycle has been validated end to end. Elsewhere it is
# prepared but reported as unvalidated; nothing claims Creator works on macOS yet.
VALIDATED = {'ollama': {'linux'}, 'comfy': {'linux'}, 'video_comfy': {'linux'}, 'voicestudio': {'linux'},
             'media_models': {'linux'}}
TIERS = ('olive-owned', 'source-checkout', 'system')


@dataclass
class Located:
    name: str
    state: str  # 'found' | 'needs_setup'
    reason: str | None = None  # missing | stale | conflict | invalid_override | unreadable_settings
    source: str | None = None  # environment | settings | discovered
    origin: str | None = None  # olive-owned | source-checkout | system | configured
    paths: dict = field(default_factory=dict)
    also_found: list = field(default_factory=list)
    overrides_settings: bool = False

    @property
    def found(self):
        return self.state == 'found'

    def get(self, key, default=''):
        return self.paths.get(key, default) if self.found else default

    def to_dict(self, platform=None):
        platform = sys.platform if platform is None else platform
        return {'label': LABELS[self.name], 'state': self.state, 'reason': self.reason, 'source': self.source,
                'origin': self.origin, 'paths': dict(self.paths), 'also_found': list(self.also_found),
                'overrides_settings': self.overrides_settings,
                'validated_on_platform': any(platform.startswith(p) for p in VALIDATED[self.name])}


def _exe(name, platform):
    return name + ('.exe' if platform == 'win32' else '')


def _venv_python(root: Path, platform):
    return root / ('Scripts/python.exe' if platform == 'win32' else 'bin/python')


def _executable(path) -> bool:
    path = Path(path)
    return path.is_file() and (sys.platform == 'win32' or os.access(path, os.X_OK))


def valid(name, paths) -> bool:
    """Structural check of a location; it never runs the runtime."""
    try:
        if name == 'ollama':
            return bool(paths.get('executable')) and _executable(paths['executable'])
        if name in ('comfy', 'video_comfy'):
            return (bool(paths.get('root') and paths.get('python')) and Path(paths['root'], 'main.py').is_file()
                    and Path(paths['python']).is_file())
        if name == 'voicestudio':
            if paths.get('root'):
                root = Path(paths['root'])
                return (root / 'backend' / 'main.py').is_file() and (
                    _venv_python(root / '.venv', 'linux').is_file() or _venv_python(root / '.venv', 'win32').is_file())
            return bool(paths.get('url'))  # An externally managed service: OLIVE only calls it.
        if name == 'media_models':
            return bool(paths.get('path')) and Path(paths['path']).is_dir()
    except (OSError, ValueError):
        return False
    return False


class RuntimeDiscovery:
    def __init__(self, profile, environ=None, platform=None, home=None, install_root=None,
                 which: Callable[[str], str | None] = shutil.which):
        self.repository = RuntimeConfigRepository(Path(profile))
        self.environ = os.environ if environ is None else environ
        self.platform = sys.platform if platform is None else platform
        self.home = home
        self.install_root = Path(install_root) if install_root is not None else app_paths.INSTALL_ROOT
        self.which = which
        self.last: dict[str, Located] = {}

    # ----------------------------------------------------------------- candidates
    def candidates(self, name) -> list[tuple[str, dict]]:
        platform = self.platform
        runtime = Path(app_paths.runtime_root(self.environ, platform, self.home))
        models = Path(app_paths.media_models_root(self.environ, platform, self.home))
        legacy = app_paths.source_toolchains(self.install_root)
        media_runtime = None if app_paths.packaged(self.install_root) else self.install_root / '.media-runtime'
        found: list[tuple[str, dict]] = []

        def comfy(origin, base, layouts):
            for root, python in layouts:
                found.append((origin, {'root': str(base / root), 'python': str(base / python)}))

        if name == 'ollama':
            relative = 'ollama/ollama.exe' if platform == 'win32' else 'ollama/bin/ollama'
            found.append(('olive-owned', {'executable': str(runtime / relative)}))
            if legacy is not None:
                found.append(('source-checkout', {'executable': str(legacy / relative)}))
            for path in self._system_ollama():
                found.append(('system', {'executable': path}))
        elif name in ('comfy', 'video_comfy'):
            folder = runtime / ('comfy' if name == 'comfy' else 'video-comfy')
            if platform == 'win32':
                comfy('olive-owned', folder, [('ComfyUI_windows_portable/ComfyUI',
                                               'ComfyUI_windows_portable/python_embeded/python.exe'),
                                              ('ComfyUI', 'comfy-venv/Scripts/python.exe')])
                if name == 'comfy' and media_runtime is not None:
                    comfy('source-checkout', media_runtime, [('ComfyUI_windows_portable/ComfyUI',
                                                             'ComfyUI_windows_portable/python_embeded/python.exe')])
            else:
                comfy('olive-owned', folder, [('ComfyUI', 'comfy-venv/bin/python')])
                if name == 'comfy' and legacy is not None:
                    comfy('source-checkout', legacy, [('ComfyUI', 'comfy-venv/bin/python')])
        elif name == 'voicestudio':
            found.append(('olive-owned', {'root': str(runtime / 'voicestudio'), 'url': VOICESTUDIO_URL}))
        elif name == 'media_models':
            found.append(('olive-owned', {'path': str(models / 'comfy')}))
        return found

    def _system_ollama(self) -> list[str]:
        platform, env = self.platform, self.environ
        paths = []
        if platform == 'win32':
            local = env.get('LOCALAPPDATA', '')
            if local:
                paths.append(str(Path(local) / 'Programs' / 'Ollama' / 'ollama.exe'))
        elif platform == 'darwin':
            # A Finder-launched app has a minimal PATH, so known install locations are checked directly.
            paths += ['/Applications/Ollama.app/Contents/Resources/ollama', '/opt/homebrew/bin/ollama',
                      '/usr/local/bin/ollama']
        located = self.which(_exe('ollama', platform))
        if located:
            paths.append(located)
        unique, seen = [], set()
        for path in paths:
            try:
                key = str(Path(path).resolve()) if Path(path).exists() else path
            except OSError:
                key = path
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return unique

    # ----------------------------------------------------------------- resolution
    def _environment(self, name):
        mapping = ENVIRONMENT[name]
        values = {key: self.environ.get(variable, '') for key, variable in mapping.items()}
        if not any(values.values()):
            return None
        return {k: v for k, v in values.items() if v}

    def _same(self, a, b):
        def normal(paths):
            result = {}
            for key, value in paths.items():
                if key == 'url':
                    result[key] = value.rstrip('/')
                    continue
                try:
                    result[key] = str(Path(value).resolve())
                except OSError:
                    result[key] = value
            return result
        return normal(a) == normal(b)

    def _discover(self, name):
        matches = [(origin, paths) for origin, paths in self.candidates(name) if valid(name, paths)]
        for tier in TIERS:
            tier_matches = []
            for origin, paths in matches:
                if origin == tier and not any(self._same(paths, other) for _, other in tier_matches):
                    tier_matches.append((origin, paths))
            if not tier_matches:
                continue
            others = [{'origin': o, 'paths': p} for o, p in matches if not any(self._same(p, t) for _, t in tier_matches)]
            if len(tier_matches) > 1 and tier != 'system':
                return None, [{'origin': o, 'paths': p} for o, p in tier_matches] + others
            return tier_matches[0], others
        return None, []

    def resolve_one(self, name, stored=None, readable=True) -> Located:
        override = self._environment(name)
        discovered, alternatives = self._discover(name)
        conflict = discovered is None and bool(alternatives)  # _discover only lists matches on a conflict.
        if override is not None:
            if name == 'voicestudio' and override.get('root') and not override.get('url'):
                override['url'] = VOICESTUDIO_URL
            if not valid(name, override):
                return Located(name, 'needs_setup', 'invalid_override', 'environment', 'configured', override)
            differs = stored is not None and not self._same(override, stored['paths'])
            return Located(name, 'found', None, 'environment', 'configured', override, overrides_settings=differs)
        if not readable:
            return Located(name, 'needs_setup', 'unreadable_settings')
        if stored is not None:
            if valid(name, stored['paths']):
                return Located(name, 'found', None, 'settings', stored.get('origin', 'configured'), dict(stored['paths']))
            candidates = [{'origin': o, 'paths': p} for o, p in ([discovered] if discovered else [])] + alternatives
            return Located(name, 'needs_setup', 'stale', 'settings', stored.get('origin', 'configured'),
                           dict(stored['paths']), also_found=candidates)
        if conflict:
            return Located(name, 'needs_setup', 'conflict', 'discovered', None, {}, also_found=alternatives)
        if discovered is None:
            return Located(name, 'needs_setup', 'missing')
        origin, paths = discovered
        return Located(name, 'found', None, 'discovered', origin, dict(paths), also_found=alternatives)

    def resolve(self, adopt=False) -> dict[str, Located]:
        stored, readable = self.repository.load()
        results = {}
        adopted = False
        for name in NAMES:
            located = self.resolve_one(name, stored.get(name), readable)
            # Adopt only an unambiguous OLIVE-owned match; data stays where it is.
            if adopt and readable and located.found and located.source == 'discovered' and located.origin == 'olive-owned':
                stored[name] = {'paths': dict(located.paths), 'origin': 'olive-owned', 'adopted': True}
                located.source = 'settings'
                adopted = True
            results[name] = located
        if adopted:
            try:
                self.repository.save(stored)
            except OSError:
                log.warning('Runtime locations could not be persisted; discovery repeats next start')
        self.last = results
        return results

    def choose(self, name, paths) -> Located:
        """Persist an explicit location (the future setup wizard's entry point)."""
        if name not in NAMES:
            raise ValueError('Unknown runtime')
        paths = {k: str(v) for k, v in paths.items() if v}
        if not valid(name, paths):
            raise ValueError('That location does not contain the expected runtime files')
        stored, readable = self.repository.load()
        if not readable:
            raise ValueError('runtimes.json is unreadable; review it before choosing a runtime')
        stored[name] = {'paths': paths, 'origin': 'configured', 'adopted': False}
        self.repository.save(stored)
        return self.resolve()[name]

    def forget(self, name) -> None:
        stored, readable = self.repository.load()
        if readable and stored.pop(name, None) is not None:
            self.repository.save(stored)

    def snapshot(self) -> dict:
        located = self.last or self.resolve()
        return {'packaged': app_paths.packaged(self.install_root),
                'user_data_root': str(app_paths.user_data_root(self.environ, self.platform, self.home)),
                'runtimes': {name: value.to_dict(self.platform) for name, value in located.items()}}


def from_environment(environ=None) -> dict[str, Located]:
    """Override-only view for callers that run without a profile (tests, tools)."""
    discovery = RuntimeDiscovery.__new__(RuntimeDiscovery)
    discovery.environ = os.environ if environ is None else environ
    discovery.platform = sys.platform
    result = {}
    for name in NAMES:
        override = discovery._environment(name)
        if override is not None and name == 'voicestudio' and override.get('root') and not override.get('url'):
            override['url'] = VOICESTUDIO_URL
        result[name] = (Located(name, 'found', None, 'environment', 'configured', override) if override
                        else Located(name, 'needs_setup', 'missing'))
    return result
