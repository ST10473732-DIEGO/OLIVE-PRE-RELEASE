"""User-driven first-run installer for manifest-pinned runtimes, models and optional components.

This is setup infrastructure for the person at the keyboard, reached only through the
desktop bridge's runtime.install_* operations. It is not a model tool: the assistant
cannot download or install anything through it.

What it will do, and nothing else:

* offer only entries runtime_manifest marks offerable for this platform: enabled, with
  complete engineering evidence AND an owner release approval bound to their pins;
* check free space before starting, per filesystem (the download folder, each install
  destination and the Ollama model store may live on different volumes or bind mounts);
* download through secure_download (HTTPS to manifest hosts, pinned size and SHA-256,
  resumable partials under <user data>/temp);
* unpack through safe_archive into a private staging folder beside the destination (so the
  final rename never crosses a filesystem), then move it into <user data>/<destination>
  with one rename, never over an existing folder;
* place verified model files (kind "file") beside their destination and rename them into
  place, never over an existing file;
* pull Ollama models through the local Ollama API after checking that the registry
  still serves the pinned manifest digest, and check the digest again afterwards;
* register what it installed in runtimes.json and record it in setup.json;
* uninstall only what it installed itself (an install record plus a marker file).

It never runs a downloaded installer or script, never disables TLS, never accepts a
checksum mismatch, never replaces a folder or model it did not create, and never stops
an Ollama server it does not own.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit
import uuid

import httpx

from .. import app_paths
from . import runtime_manifest as manifests
from . import safe_archive
from .secure_download import Artefact, Cancelled, DownloadError, Downloader
from ..storage.setup_state_repository import SetupStateRepository

log = logging.getLogger(__name__)

MARKER = '.olive-install.json'
MARGIN = 512 * 1024 ** 2
MANIFEST_LIMIT = 1024 * 1024
REGISTRY_ACCEPT = 'application/vnd.docker.distribution.manifest.v2+json'
RUNTIME_SLOTS = {'ollama-runtime': 'ollama', 'image-engine': 'comfy', 'video-engine': 'video_comfy',
                 'audio-engine': 'voicestudio'}
ORDER = {'archive': 0, 'python-wheels': 1, 'file': 2, 'ollama-model': 3}
FINAL = {'done', 'present', 'different_build', 'failed', 'cancelled'}
MOUNTINFO = '/proc/self/mountinfo'


def _unescape_mount(path: str) -> str:
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), path)


def mount_table(text: str | None = None) -> list[tuple[str, str]]:
    """[(mount point, filesystem id)] from Linux mountinfo, longest mount point first.

    The id is the mount's major:minor, which is the filesystem (superblock) device: bind
    mounts and Btrfs subvolumes of one filesystem share it, while stat().st_dev can differ
    per Btrfs subvolume. Empty where mountinfo is unavailable (Windows, macOS)."""
    if text is None:
        try:
            text = Path(MOUNTINFO).read_text(encoding='utf-8', errors='replace')
        except OSError:
            return []
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) > 4:
            rows.append((_unescape_mount(fields[4]), fields[2]))
    return sorted(rows, key=lambda row: len(row[0]), reverse=True)


def filesystem(path, table) -> tuple[Any, Path]:
    """(filesystem key, nearest existing path) for where `path` lives or will live."""
    probe = Path(path)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    real = os.path.realpath(probe)
    for point, device in table:
        if point == '/' or real == point or real.startswith(point.rstrip('/') + '/'):
            return 'fs:' + device, probe
    try:
        return os.stat(probe).st_dev, probe
    except OSError:
        return str(probe), probe


class InstallError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Item:
    id: str
    name: str
    kind: str
    total_bytes: int
    state: str = 'queued'  # queued downloading verifying extracting installing pulling done present different_build failed cancelled
    done_bytes: int = 0
    message: str = ''
    error: str | None = None

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'kind': self.kind, 'state': self.state, 'done_bytes': self.done_bytes,
                'total_bytes': self.total_bytes, 'message': self.message, 'error': self.error}


@dataclass
class Job:
    id: str
    profile: str
    items: list[Item]
    state: str = 'running'  # running done failed cancelled
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    task: asyncio.Task | None = None
    pull: asyncio.Task | None = None

    def to_dict(self):
        return {'job_id': self.id, 'profile': self.profile, 'state': self.state,
                'items': [i.to_dict() for i in self.items],
                'done_bytes': sum(i.done_bytes for i in self.items),
                'total_bytes': sum(i.total_bytes for i in self.items),
                'started_at': self.started_at, 'finished_at': self.finished_at}


def _loopback_host(host: str) -> str:
    parts = urlsplit(host if '://' in host else 'http://' + host)
    if parts.scheme != 'http' or parts.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise InstallError('ollama_not_local', 'Setup only pulls models into an Ollama server on this computer')
    return f'{parts.scheme}://{parts.netloc}'


def _normal_model(name: str) -> str:
    name = name.strip()
    if name.startswith('registry.ollama.ai/'):
        name = name[len('registry.ollama.ai/'):]
    if name.startswith('library/'):
        name = name[len('library/'):]
    return name if ':' in name.rsplit('/', 1)[-1] else name + ':latest'


class RuntimeInstaller:
    def __init__(self, profile, discovery, *, ollama_host: str | Callable[[], str] = 'http://127.0.0.1:11434',
                 environ=None, platform=None, home=None, target=None, manifest=None,
                 client_factory=None, async_client_factory=None, disk_usage=shutil.disk_usage,
                 ensure_ollama: Callable[[], Awaitable[bool]] | None = None,
                 runtime_registered: Callable[[str, Any], Awaitable[None] | None] | None = None,
                 before_uninstall: Callable[[str, Path], Awaitable[None] | None] | None = None,
                 presence: dict[str, Callable[[], bool]] | None = None,
                 on_change: Callable[[dict], None] | None = None, mounts: Callable[[], list] = mount_table):
        self.profile = Path(profile)
        self.discovery = discovery
        self.state = SetupStateRepository(self.profile)
        self.environ = os.environ if environ is None else environ
        self.platform = discovery.platform if platform is None else platform
        self.home = home
        self.target = target if target is not None else manifests.platform_target(self.platform)
        self._manifest = manifest
        self.ollama_host = ollama_host
        self.client_factory = client_factory
        # Loopback Ollama calls ignore proxy settings; the registry check may use them (trust_env=True).
        # TLS verification is never configurable.
        self.async_client_factory = async_client_factory or (
            lambda **kw: httpx.AsyncClient(**{'trust_env': False, **kw, 'follow_redirects': False, 'verify': True}))
        self.disk_usage = disk_usage
        self.mounts = mounts
        self.ensure_ollama = ensure_ollama
        self.runtime_registered = runtime_registered
        self.before_uninstall = before_uninstall
        self.presence = presence or {}
        self.on_change = on_change or (lambda job: None)
        self.jobs: dict[str, Job] = {}
        self.module_available = lambda name: importlib.util.find_spec(name) is not None
        self.data_root = Path(app_paths.user_data_root(self.environ, self.platform, home))
        self.temp = self.data_root / 'temp'

    # ------------------------------------------------------------------ manifest
    def manifest(self) -> dict:
        if self._manifest is None:
            self._manifest = manifests.load(environ=self.environ)
        return self._manifest

    @property
    def loopback(self) -> bool:
        return manifests.loopback_allowed(self.manifest(), self.environ)

    def entry(self, entry_id) -> dict:
        for entry in self.manifest()['entries']:
            if entry['id'] == entry_id:
                return entry
        raise ValueError('Unknown setup component')

    def describe(self) -> dict:
        """The manifest as the renderer may see it (no internal evidence fields)."""
        manifest, target = self.manifest(), self.target
        return {
            'target': target, 'source': manifest.get('_source', 'release'),
            'manifest_version': manifest.get('manifest_version'),
            'profiles': [{'id': key, 'label': value['label'], 'summary': value.get('summary', ''),
                          'includes': value.get('includes', [])} for key, value in manifest['profiles'].items()],
            'features': [{k: f.get(k) for k in ('id', 'label', 'profile', 'requires', 'optional', 'note', 'optional_component')}
                         for f in manifest['features']],
            'entries': [manifests.public_entry(e, target, self.loopback, manifest) for e in manifest['entries']
                        if target is None or target in e['platforms']],
        }

    # ------------------------------------------------------------------ inventory
    async def model_tags(self) -> dict[str, str] | None:
        """{model: manifest digest} from the local Ollama, or None when it does not answer."""
        try:
            host = _loopback_host(self.ollama_host() if callable(self.ollama_host) else self.ollama_host)
        except InstallError:
            return None
        try:
            async with self.async_client_factory(timeout=httpx.Timeout(5)) as client:
                response = await client.get(host + '/api/tags')
                if response.status_code != 200:
                    return None
                tags = {}
                for model in response.json().get('models', []):
                    digest = str(model.get('digest', ''))
                    digest = digest.split(':', 1)[1] if digest.startswith('sha256:') else digest
                    for key in (model.get('name'), model.get('model')):
                        if isinstance(key, str) and key:
                            tags[_normal_model(key)] = digest
                return tags
        except (httpx.HTTPError, ValueError, AttributeError):
            return None

    def installed_records(self) -> dict:
        state, _ = self.state.load()
        return state['installed']

    def _owned(self, destination: Path, entry_id: str) -> bool:
        try:
            marker = json.loads((destination / MARKER).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return False
        return isinstance(marker, dict) and marker.get('id') == entry_id and not destination.is_symlink()

    def _destination(self, relative: str) -> Path:
        if not manifests.safe_relative(relative):
            raise InstallError('bad_destination', 'The manifest names an unsafe destination')
        destination = self.data_root.joinpath(*relative.split('/'))
        app_paths.require_writable_location(destination)
        self.data_root.mkdir(parents=True, exist_ok=True)
        root = self.data_root.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            # A link planted inside the data folder must not redirect the install elsewhere.
            destination.parent.resolve().relative_to(root)
        except ValueError:
            raise InstallError('bad_destination', 'The destination resolves outside the OLIVE data folder') from None
        return destination

    def _slot(self, slot, located, tags) -> dict:
        """What setup can do about one component slot on this computer."""
        target = self.target
        manifest = self.manifest()
        candidates = manifests.providers(manifest, slot, target)
        installable = [e for e in candidates if manifests.offerable(e, target, manifest, self.loopback)]
        # Complete engineering evidence but no owner release approval: shown, never offered.
        awaiting = [e for e in candidates if target and e['enabled'] and not manifests.release_approved(e, manifest)
                    and manifests.complete(e, target, self.loopback)]
        external = [e for e in candidates if e['kind'] == 'external']
        offer = installable[0] if installable else None
        shown = offer or (awaiting[0] if awaiting else None) or (candidates[0] if candidates else
                                                                  {'id': slot, 'kind': 'external', 'name': slot,
                                                                   'platforms': [], 'source': {}, 'licence': {}})
        result = {'slot': slot, 'entry': manifests.public_entry(shown, target, self.loopback, manifest),
                  'action': 'unavailable', 'detail': ''}
        if slot in RUNTIME_SLOTS:
            found = located.get(RUNTIME_SLOTS[slot])
            if found is not None and found.found:
                return {**result, 'action': 'present', 'detail': f'Found ({found.origin or found.source})'}
            if found is not None and found.reason in ('conflict', 'invalid_override', 'unreadable_settings'):
                return {**result, 'action': 'choose', 'detail': found.reason}
        elif any(e.get('ollama') for e in candidates):
            # Any model this slot names counts when it is already installed, even one setup cannot offer.
            for each in candidates:
                if not each.get('ollama') or tags is None:
                    continue
                digest = tags.get(_normal_model(each['ollama']['model']))
                if digest == each['ollama']['manifest_digest']:
                    return {**result, 'action': 'present', 'detail': 'Installed'}
                if digest is not None:
                    return {**result, 'action': 'different_build',
                            'detail': 'A different build of this model is installed; it is kept as it is'}
        elif slot == 'playwright':
            record = self.installed_records().get(offer['id']) if offer else None
            if record and self._owned(self.data_root / offer['install']['destination'], offer['id']):
                return {**result, 'action': 'present', 'detail': 'Installed by OLIVE setup'}
            if self.module_available('playwright'):
                return {**result, 'action': 'present', 'detail': 'Provided by this Python environment'}
        elif slot == 'ffmpeg':
            if shutil.which('ffmpeg') and shutil.which('ffprobe'):
                return {**result, 'action': 'present', 'detail': 'Found on this computer'}
        for each in candidates:
            if each['kind'] == 'file' and target in each['platforms'] and self._files_present(each):
                return {**result, 'entry': manifests.public_entry(each, target, self.loopback, manifest),
                        'action': 'present', 'detail': 'Model files found'}
        detector = self.presence.get(slot)
        if detector is not None:
            try:
                if detector():
                    return {**result, 'action': 'present', 'detail': 'Found on this computer'}
            except Exception:
                log.exception('Presence check for %s failed', slot)
        if offer is not None:
            if offer['kind'] == 'ollama-model' and tags is None:
                return {**result, 'action': 'install', 'detail': 'Installs once the local AI engine is running'}
            if offer['kind'] == 'archive':
                destination = self.data_root.joinpath(*offer['install']['destination'].split('/'))
                if (destination.exists() or destination.is_symlink()) and not self._owned(destination, offer['id']):
                    return {**result, 'action': 'choose',
                            'detail': 'A folder already exists where OLIVE would install this; choose it instead'}
            return {**result, 'action': 'install'}
        if external:
            return {**result, 'action': 'external', 'detail': external[0].get('reason') or ''}
        if awaiting:
            return {**result, 'action': 'unavailable', 'detail': manifests.AWAITING_APPROVAL}
        reasons = [e.get('reason') for e in candidates if e.get('reason')]
        return {**result, 'action': 'unavailable',
                'detail': reasons[0] if reasons else 'Not available for this computer in this build'}

    async def plan(self, profile: str, selected: list[str] | None = None) -> dict:
        manifest = self.manifest()
        features = manifests.profile_features(manifest, profile)
        located = await asyncio.to_thread(self.discovery.resolve)
        tags = await self.model_tags()
        slots: dict[str, dict] = {}
        for feature in features:
            for slot in feature.get('requires', []) + feature.get('optional', []):
                if slot not in slots:
                    slots[slot] = self._slot(slot, located, tags)
        # Optional components (browser automation) are offered but never selected by default;
        # a feature's optional extras (the embedding model) are selected by default.
        required = {s for f in features if not f.get('optional_component') for s in f.get('requires', [])}
        extras = {s for f in features for s in f.get('optional', [])} - required
        components = {s for f in features if f.get('optional_component') for s in f.get('requires', [])} - required
        feature_rows = []
        for feature in features:
            needed = [slots[s] for s in feature.get('requires', [])]
            actions = {s['action'] for s in needed}
            if not needed or actions <= {'present', 'different_build'}:
                state = 'ready'
            elif 'unavailable' in actions:
                state = 'not_in_build'
            elif 'external' in actions:
                state = 'external'
            elif 'choose' in actions:
                state = 'choose'
            else:
                state = 'installable'
            feature_rows.append({'id': feature['id'], 'label': feature['label'], 'profile': feature['profile'],
                                 'state': state, 'note': feature.get('note'),
                                 'optional_component': bool(feature.get('optional_component')),
                                 'missing': [s['slot'] for s in needed if s['action'] not in ('present', 'different_build')]})
        items = [{**row, 'optional': slot in extras or slot in components} for slot, row in slots.items()]
        # A slot is chosen by default only when some feature that needs it can actually become
        # ready here: a model is never downloaded for an engine this build cannot install.
        declared = {f['id']: f for f in features}
        usable = {s for row in feature_rows if row['state'] != 'not_in_build'
                  for s in declared[row['id']].get('requires', []) + declared[row['id']].get('optional', [])}
        default = [row['entry']['id'] for row in items if row['action'] == 'install' and row['slot'] not in components
                   and row['slot'] in usable]
        offered = [row['entry']['id'] for row in items if row['action'] == 'install']
        chosen = default if selected is None else [i for i in selected if i in offered]
        return {'profile': profile, 'target': self.target, 'source': manifest.get('_source', 'release'),
                'features': feature_rows, 'items': items, 'default': default, 'offered': offered, 'selected': chosen,
                'some_unavailable': any(f['state'] == 'not_in_build' for f in feature_rows),
                'totals': self.space(chosen)}

    # ------------------------------------------------------------------ disk
    def models_directory(self) -> Path:
        located = self.discovery.last.get('ollama') if self.discovery.last else None
        configured = (located.paths.get('models') if located is not None and located.found else '') or self.environ.get('OLLAMA_MODELS', '')
        home = Path(self.home) if self.home is not None else Path.home()
        return Path(configured) if configured else home / '.ollama' / 'models'

    def _volume(self, path: Path, table=None):
        return filesystem(path, self.mounts() if table is None else table)

    @staticmethod
    def _role(entry) -> str:
        root = entry['install']['destination'].split('/')[0]
        return {'runtime': 'OLIVE runtimes', 'components': 'Optional components', 'models': 'Creator models'}.get(root, 'OLIVE data')

    def space(self, entry_ids) -> dict:
        """Free space per filesystem. Each byte is charged to the filesystem it will occupy: downloads
        to the temp folder's, unpacked runtimes and model files to their destination's, Ollama
        models to the model store's. Bind mounts and Btrfs subvolumes of one filesystem are one
        volume; separate filesystems are checked separately, never against the root filesystem."""
        target = self.target
        table = self.mounts()
        volumes: dict[Any, dict] = {}
        download = installed = 0

        def need(path: Path, label: str, amount: int):
            key, probe = self._volume(path, table)
            volume = volumes.setdefault(key, {'labels': [], 'path': str(path), 'probe': probe, 'required_bytes': MARGIN})
            if label not in volume['labels']:
                volume['labels'].append(label)
            volume['required_bytes'] += amount

        for entry_id in entry_ids:
            entry = self.entry(entry_id)
            size = manifests.download_bytes(entry, target)
            download += size
            if entry['kind'] == 'ollama-model':
                installed += size
                need(self.models_directory(), 'Ollama models', size)
                continue
            final = int(entry['install'].get('installed_bytes') or size)
            installed += final
            destination = self.data_root.joinpath(*entry['install']['destination'].split('/'))
            same = self._volume(self.temp, table)[0] == self._volume(destination, table)[0]
            if entry['kind'] == 'file' and same:
                need(destination, self._role(entry), final)  # Renamed into place: the bytes exist once.
                continue
            # An archive and its unpacked copy coexist until the archive is deleted; a model file
            # downloaded to another filesystem is copied once before the download is removed.
            need(self.temp, 'Downloads', size)
            need(destination, self._role(entry), final)
        rows = []
        for volume in volumes.values():
            try:
                free = int(self.disk_usage(volume['probe']).free)
            except OSError:
                free = None
            labels = volume['labels']
            rows.append({'label': labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + ' and ' + labels[-1],
                         'path': volume['path'],
                         'required_bytes': volume['required_bytes'], 'free_bytes': free,
                         'enough': free is not None and free >= volume['required_bytes']})
        return {'download_bytes': download, 'installed_bytes': installed, 'volumes': rows,
                'enough_space': all(r['enough'] for r in rows)}

    # ------------------------------------------------------------------ jobs
    def running(self) -> Job | None:
        return next((j for j in self.jobs.values() if j.state == 'running'), None)

    async def start(self, profile: str, entry_ids: list[str]) -> dict:
        if self.running():
            raise InstallError('busy', 'Setup is already installing; wait for it or cancel it first')
        plan = await self.plan(profile, entry_ids)
        unknown = [i for i in entry_ids if i not in plan['offered']]
        if unknown:
            raise InstallError('not_installable', 'These components cannot be installed here: ' + ', '.join(unknown))
        if not entry_ids:
            raise InstallError('nothing_selected', 'Choose at least one component to install')
        if not plan['totals']['enough_space']:
            short = [v for v in plan['totals']['volumes'] if not v['enough']]
            raise InstallError('insufficient_space', 'Not enough free space: ' + '; '.join(
                f"{v['label']} needs {v['required_bytes']} bytes, {v['free_bytes']} free" for v in short))
        entries = sorted((self.entry(i) for i in dict.fromkeys(entry_ids)), key=lambda e: ORDER[e['kind']])
        job = Job(uuid.uuid4().hex, profile, [Item(e['id'], e['name'], e['kind'],
                                                   manifests.download_bytes(e, self.target)) for e in entries])
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job))
        return job.to_dict()

    def progress(self, job_id: str | None = None) -> dict:
        job = self.jobs.get(job_id) if job_id else (self.running() or (list(self.jobs.values())[-1] if self.jobs else None))
        if job is None:
            if job_id:
                raise ValueError('Unknown setup job')
            return {'job_id': None, 'state': 'idle', 'items': [], 'done_bytes': 0, 'total_bytes': 0}
        return job.to_dict()

    def cancel(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise ValueError('Unknown setup job')
        job.cancel.set()
        if job.pull is not None and not job.pull.done():
            job.pull.cancel()
        return job.to_dict()

    async def retry(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise ValueError('Unknown setup job')
        if job.state == 'running':
            raise InstallError('busy', 'This setup job is still running')
        if self.running():
            raise InstallError('busy', 'Another setup job is running')
        retry = [i for i in job.items if i.state in ('failed', 'cancelled', 'queued')]
        if not retry:
            return job.to_dict()
        entries = [i.id for i in retry]
        space = self.space(entries)
        if not space['enough_space']:
            raise InstallError('insufficient_space', 'Not enough free space to retry')
        for item in retry:
            item.state, item.error, item.message = 'queued', None, ''
        job.state, job.finished_at, job.cancel = 'running', None, threading.Event()
        job.task = asyncio.create_task(self._run(job))
        return job.to_dict()

    def _changed(self, job):
        try:
            self.on_change(job.to_dict())
        except Exception:
            log.exception('Install progress listener failed')

    async def _run(self, job: Job):
        try:
            for item in job.items:
                if item.state in FINAL and item.state not in ('failed', 'cancelled'):
                    continue
                if job.cancel.is_set():
                    item.state = 'cancelled'
                    continue
                entry = self.entry(item.id)
                try:
                    await self._install(job, item, entry)
                except Cancelled:
                    item.state, item.message = 'cancelled', 'Cancelled; downloaded bytes are kept so a retry resumes'
                except asyncio.CancelledError:
                    if not job.cancel.is_set():
                        raise
                    item.state, item.message = 'cancelled', 'Cancelled; Ollama keeps what it downloaded so a retry resumes'
                except (InstallError, DownloadError) as error:
                    item.state, item.error, item.message = 'failed', error.code, str(error)
                except safe_archive.ArchiveError as error:
                    item.state, item.error, item.message = 'failed', 'unsafe_archive', str(error)
                except Exception as error:
                    log.exception('Installing %s failed', item.id)
                    item.state, item.error, item.message = 'failed', 'unexpected', f'{type(error).__name__}'
                self._changed(job)
        finally:
            states = {i.state for i in job.items}
            job.state = ('cancelled' if job.cancel.is_set() and 'cancelled' in states else
                         'failed' if states & {'failed', 'cancelled', 'queued'} else 'done')
            job.finished_at = time.time()
            job.pull = None
            self._changed(job)

    async def _install(self, job: Job, item: Item, entry: dict):
        if entry['kind'] == 'ollama-model':
            job.pull = asyncio.create_task(self._pull(entry, item, job.cancel))
            try:
                record = await job.pull
            finally:
                job.pull = None
        elif entry['kind'] == 'file':
            record = await asyncio.to_thread(self._install_model_files, entry, item, job.cancel)
        elif entry['kind'] in ('archive', 'python-wheels'):
            destination, record = await asyncio.to_thread(self._install_files, entry, item, job.cancel)
            register = entry['install'].get('register')
            if register:
                item.state = 'installing'
                paths = {k: str(destination.joinpath(*v.split('/'))) for k, v in register['paths'].items()}
                located = await asyncio.to_thread(self.discovery.register, register['runtime'], paths)
                record['runtime'] = register['runtime']
                if self.runtime_registered is not None:
                    outcome = self.runtime_registered(register['runtime'], located)
                    if asyncio.iscoroutine(outcome):
                        await outcome
            if entry['kind'] == 'python-wheels':
                from .optional_components import activate_path
                activate_path(destination)
        else:
            raise InstallError('not_installable', 'This component is installed outside OLIVE setup')
        if record is not None:
            self._record(entry['id'], record)
        if item.state not in ('present', 'different_build'):
            item.state, item.done_bytes = 'done', item.total_bytes

    def _record(self, entry_id, record):
        state, readable = self.state.load()
        if not readable:
            log.warning('setup.json is unreadable; the install of %s is not recorded', entry_id)
            return
        state['installed'][entry_id] = {**record, 'installed_at': time.time()}
        self.state.save(state)

    # ------------------------------------------------------------------ files
    def _download(self, entry, files, item: Item, cancel) -> list[Path]:
        downloader = Downloader(self.temp / 'downloads', allow_loopback_http=self.loopback,
                                **({'client_factory': self.client_factory} if self.client_factory else {}))
        hosts = tuple(entry['source'].get('hosts') or ())
        paths, before = [], 0
        item.state = 'downloading'
        for each in files:
            artefact = Artefact(each['url'], each['sha256'], each['size_bytes'], hosts, each['name'])
            offset = before

            def progress(done, total, offset=offset):
                item.done_bytes = offset + done
            paths.append(downloader.fetch(artefact, cancel=cancel, progress=progress))
            before += each['size_bytes']
        item.state = 'verifying'
        return paths

    def _install_files(self, entry, item: Item, cancel) -> tuple[Path, dict | None]:
        install = entry['install']
        destination = self._destination(install['destination'])
        if self._owned(destination, entry['id']):
            item.state, item.message = 'present', 'Already installed by OLIVE setup'
            return destination, None
        if destination.exists() or destination.is_symlink():
            raise InstallError('destination_exists', f'{destination} already exists. OLIVE does not replace an '
                                                     'installation it did not create; choose it under Runtimes instead')
        files = manifests.files_for(entry, self.target)
        downloaded = self._download(entry, files, item, cancel)
        item.state = 'extracting'
        # Staged beside the destination so the final rename stays on one filesystem (the runtime
        # folder may be a bind mount or another volume than the temp folder).
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".{destination.name}.olive-staging-{uuid.uuid4().hex[:8]}"
        expected = int(install.get('installed_bytes') or sum(f['size_bytes'] for f in files) * 4)
        limit = int(expected * 1.25) + 64 * 1024 ** 2
        executables = install.get('executables', [])
        try:
            if entry['kind'] == 'archive':
                safe_archive.extract(downloaded[0], install['format'], staging, max_bytes=limit,
                                     executables=executables, cancel=cancel)
            else:
                safe_archive.extract(downloaded[0], 'wheel', staging, max_bytes=limit, cancel=cancel)
                for path in downloaded[1:]:
                    safe_archive.extract_more(path, 'wheel', staging, max_bytes=limit, cancel=cancel)
                safe_archive.require_executables(staging, executables)
            safe_archive.normalise_modes(staging, executables)
            (staging / MARKER).write_text(json.dumps({
                'schema': 'olive-install/1', 'id': entry['id'], 'version': entry.get('version'),
                'files': [{'name': f['name'], 'sha256': f['sha256']} for f in files]}, indent=2), encoding='utf-8')
            item.state = 'installing'
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                raise InstallError('destination_exists', f'{destination} appeared during installation; it was left untouched')
            os.rename(staging, destination)  # One rename: the destination is either absent or complete.
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        for path in downloaded:
            path.unlink(missing_ok=True)  # Verified and unpacked; the archive itself is no longer needed.
        return destination, {'kind': entry['kind'], 'version': entry.get('version') or '', 'path': str(destination),
                             'sha256': files[0]['sha256'] if len(files) == 1 else ''}

    # ------------------------------------------------------------------ model files
    def _file_targets(self, entry, prepare=True) -> list[tuple[dict, Path]]:
        relative = entry['install']['destination']
        if not manifests.safe_relative(relative):
            raise InstallError('bad_destination', 'The manifest names an unsafe destination')
        # prepare=False only computes paths (plan and presence checks never create folders).
        base = self._destination(relative) if prepare else self.data_root.joinpath(*relative.split('/'))
        return [(item, base.joinpath(*(item.get('path') or item['name']).split('/')))
                for item in manifests.files_for(entry, self.target)]

    def _files_present(self, entry) -> bool:
        """Every file of a model set is already in place with its pinned size (cheap; no hashing)."""
        try:
            targets = self._file_targets(entry, prepare=False)
        except (InstallError, OSError):
            return False
        return bool(targets) and all(path.is_file() and not path.is_symlink() and path.stat().st_size == item['size_bytes']
                                     for item, path in targets)

    @staticmethod
    def _same_file(path: Path, item: dict) -> bool:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != item['size_bytes']:
            return False
        with open(path, 'rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256']

    def _install_model_files(self, entry, item: Item, cancel) -> dict | None:
        """Download each pinned model file, verify it, and rename it into place. A file already
        there with the pinned SHA-256 is kept; any other existing file stops the install."""
        targets = self._file_targets(entry)
        root = self.data_root.resolve()
        for each, path in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.parent.resolve().relative_to(root)
            except ValueError:
                raise InstallError('bad_destination', 'A model folder resolves outside the OLIVE data folder') from None
            if (path.exists() or path.is_symlink()) and not self._same_file(path, each):
                raise InstallError('destination_exists', f'{path} already exists and is not the pinned file; '
                                                         'OLIVE does not replace files it did not install')
        missing = [(each, path) for each, path in targets if not path.exists()]
        if not missing:
            item.state, item.message = 'present', 'Already installed'
            return None
        downloaded = self._download(entry, [each for each, _ in missing], item, cancel)
        item.state = 'installing'
        placed = []
        try:
            for (each, path), source in zip(missing, downloaded):
                if path.exists() or path.is_symlink():
                    raise InstallError('destination_exists', f'{path} appeared during installation; it was left untouched')
                staging = path.parent / f'.{path.name}.olive-staging-{uuid.uuid4().hex[:8]}'
                try:
                    os.rename(source, staging)
                except OSError:
                    shutil.copyfile(source, staging)  # Different filesystem: copy, then verify the copy.
                    if not self._same_file(staging, each):
                        staging.unlink(missing_ok=True)
                        raise InstallError('checksum_mismatch', f'The copy of {each["name"]} did not verify')
                    source.unlink(missing_ok=True)
                os.chmod(staging, 0o644)
                os.rename(staging, path)
                placed.append(path)
        except BaseException:
            for path in placed:
                path.unlink(missing_ok=True)
            raise
        return {'kind': 'file', 'version': entry.get('version') or '',
                'files': [{'path': str(path), 'sha256': each['sha256'], 'size_bytes': each['size_bytes']}
                          for each, path in missing]}

    # ------------------------------------------------------------------ Ollama
    def _host(self) -> str:
        return _loopback_host(self.ollama_host() if callable(self.ollama_host) else self.ollama_host)

    async def _check_registry(self, entry):
        url = entry['source']['url']
        if not manifests.url_allowed(url, entry['source'].get('hosts') or [], self.loopback):
            raise InstallError('source_not_allowed', 'The model registry address is not allowed')
        async with self.async_client_factory(timeout=httpx.Timeout(30), trust_env=True) as client:
            async with client.stream('GET', url, headers={'Accept': REGISTRY_ACCEPT}) as response:
                if response.status_code != 200:
                    raise InstallError('registry_unavailable', f'The model registry answered HTTP {response.status_code}')
                body = b''
                async for block in response.aiter_bytes():
                    body += block
                    if len(body) > MANIFEST_LIMIT:
                        raise InstallError('registry_unavailable', 'The model registry sent an oversized manifest')
        if hashlib.sha256(body).hexdigest() != entry['ollama']['manifest_digest']:
            raise InstallError('registry_changed', 'The registry now serves a different build of this model than '
                                                   'this OLIVE release verified, so it was not installed')

    async def _pull(self, entry, item: Item, cancel: threading.Event) -> dict | None:
        model, pinned = entry['ollama']['model'], entry['ollama']['manifest_digest']
        host = self._host()
        tags = await self.model_tags()
        if tags is None and self.ensure_ollama is not None:
            item.message = 'Starting the local AI engine'
            if await self.ensure_ollama():
                tags = await self.model_tags()
        if tags is None:
            raise InstallError('ollama_unavailable', 'The local AI engine (Ollama) is not running; install or start it first')
        before = tags.get(_normal_model(model))
        if before == pinned:
            item.state, item.message = 'present', 'Already installed'
            return None
        if before is not None:
            item.state, item.message = 'different_build', 'A different build is installed; it was kept as it is'
            return None
        item.state, item.message = 'verifying', 'Checking the registry digest'
        await self._check_registry(entry)
        item.state, item.message = 'pulling', 'Downloading'
        layers: dict[str, tuple[int, int]] = {}
        succeeded = False
        async with self.async_client_factory(timeout=httpx.Timeout(None, connect=10)) as client:
            async with client.stream('POST', host + '/api/pull', json={'model': model, 'stream': True}) as response:
                if response.status_code != 200:
                    raise InstallError('pull_failed', f'Ollama answered HTTP {response.status_code}')
                async for line in response.aiter_lines():
                    if cancel.is_set():
                        raise Cancelled()
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get('error'):
                        raise InstallError('pull_failed', 'Ollama: ' + str(event['error'])[:300])
                    digest, total = event.get('digest'), event.get('total')
                    if isinstance(digest, str) and isinstance(total, int) and total > 0:
                        layers[digest] = (min(int(event.get('completed') or 0), total), total)
                        item.done_bytes = sum(done for done, _ in layers.values())
                    item.message = str(event.get('status', ''))[:120]
                    if event.get('status') == 'success':
                        succeeded = True
                        break
        if not succeeded:
            raise InstallError('pull_incomplete', 'The model download ended before Ollama reported success')
        after = (await self.model_tags() or {}).get(_normal_model(model))
        if after != pinned:
            try:
                async with self.async_client_factory(timeout=httpx.Timeout(30)) as client:
                    await client.request('DELETE', host + '/api/delete', json={'model': model})
            except httpx.HTTPError:
                log.warning('Could not remove the mismatched pull of %s', model)
            raise InstallError('digest_mismatch', 'The installed model does not match its pinned digest; it was removed')
        return {'kind': 'ollama-model', 'model': model, 'digest': pinned, 'installed_by_olive': True,
                'version': entry.get('version') or ''}

    # ------------------------------------------------------------------ uninstall
    async def uninstall(self, entry_id: str) -> dict:
        if self.running():
            raise InstallError('busy', 'Wait for setup to finish installing first')
        entry = self.entry(entry_id)
        state, readable = self.state.load()
        record = state['installed'].get(entry_id) if readable else None
        if not record:
            raise InstallError('not_installed_by_olive', 'OLIVE setup did not install this, so it will not remove it')
        if entry['kind'] == 'ollama-model':
            if not record.get('installed_by_olive'):
                raise InstallError('not_installed_by_olive', 'OLIVE setup did not install this model')
            async with self.async_client_factory(timeout=httpx.Timeout(60)) as client:
                response = await client.request('DELETE', self._host() + '/api/delete', json={'model': entry['ollama']['model']})
                if response.status_code not in (200, 404):
                    raise InstallError('uninstall_failed', f'Ollama answered HTTP {response.status_code}')
        elif entry['kind'] == 'file':
            # Only files setup recorded, and only while they still have the recorded bytes
            # (hashing multi-GB files happens off the event loop).
            def remove_recorded():
                for each in record.get('files', []):
                    path = Path(each['path'])
                    if self._same_file(path, each):
                        path.unlink()
            await asyncio.to_thread(remove_recorded)
        else:
            destination = self._destination(entry['install']['destination'])
            if not self._owned(destination, entry_id):
                raise InstallError('not_installed_by_olive', 'The folder no longer carries OLIVE setup\'s install record; '
                                                             'it was left untouched')
            register = entry['install'].get('register')
            if register:
                if self.before_uninstall is not None:
                    outcome = self.before_uninstall(register['runtime'], destination)
                    if asyncio.iscoroutine(outcome):
                        await outcome
                located = (await asyncio.to_thread(self.discovery.resolve))[register['runtime']]
                if any(app_paths.inside_installation(v, destination) for v in located.paths.values() if v and '://' not in v):
                    await asyncio.to_thread(self.discovery.forget, register['runtime'])
            await asyncio.to_thread(shutil.rmtree, destination)
            if entry['kind'] == 'python-wheels':
                from .optional_components import deactivate_path
                deactivate_path(destination)
        state, readable = self.state.load()
        if readable:
            state['installed'].pop(entry_id, None)
            self.state.save(state)
        return {'removed': entry_id}

    async def close(self):
        for job in self.jobs.values():
            if job.state == 'running':
                job.cancel.set()
                if job.pull is not None:
                    job.pull.cancel()
        tasks = [j.task for j in self.jobs.values() if j.task is not None and not j.task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
