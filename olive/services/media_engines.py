"""Image and video ComfyUI engines as two separate, loopback-only runtimes.

Discovery is explicit (environment set by run_olive.sh); nothing here
downloads, installs or edits a runtime. Status is cached and cheap so the
preset snapshot never blocks on the network.

Idle lifecycle (image engine): after a generation the engine releases its GPU
memory but its process keeps several GiB of host RAM. When OLIVE itself started
the engine, it is stopped once it has been idle for the model keep-alive period
(the same setting that unloads idle text models; at least IDLE_FLOOR seconds).
It never stops while a job runs, while any OLIVE GPU job holds the shared
residency lock (Chat, Media tools and remote Connect requests all take it),
while ComfyUI reports queued work from another client, or when someone else
started the server. The next request starts it again.
"""
import asyncio
import logging
from pathlib import Path
import re
import time

from .gpu_probe import port_bound
from .local_comfy_runtime import LocalComfyRuntime
from .media_comfy import ComfyWorkflows
from .media_errors import MediaError
from .media_workflows import IMAGE_WORKFLOWS, VIDEO_WORKFLOWS, availability

log = logging.getLogger(__name__)

# /object_info node input -> ComfyUI model folders searched for that input.
FOLDERS = {
    ('UNETLoader', 'unet_name'): ('diffusion_models', 'unet'),
    ('CLIPLoader', 'clip_name'): ('text_encoders', 'clip'),
    ('VAELoader', 'vae_name'): ('vae',),
    ('CheckpointLoaderSimple', 'ckpt_name'): ('checkpoints',),
    ('LTXV23ModelsLoader', 'unet_name'): ('diffusion_models', 'unet'),
    ('LTXV23ModelsLoader', 'text_encoder_name'): ('text_encoders', 'clip'),
    ('LTXV23ModelsLoader', 'projections_name'): ('text_encoders', 'clip'),
    ('LTXV23ModelsLoader', 'video_vae_name'): ('vae',),
    ('LTXV23ModelsLoader', 'audio_vae_name'): ('vae',),
    ('LatentUpscaleModelLoader', 'model_name'): ('latent_upscale_models',),
}
# The persistent image model store keeps FLUX.2 files outside the runtime's
# own models folder; OLIVE points its owned image runtime at them read-only.
IMAGE_EXTRA = {'diffusion_models': ['diffusion_models', 'flux2'],
               'text_encoders': ['text_encoders', 'flux2/split_files/text_encoders'],
               'vae': ['vae', 'flux2/split_files/vae'], 'checkpoints': ['checkpoints']}


class ComfyEngine:
    IDLE_FLOOR = 60      # Never stop an owned engine sooner than this after OLIVE last used it.
    IDLE_DEFAULT = 300   # The model policy's default keep-alive.
    IDLE_RETRY = 30

    def __init__(self, kind, runtime, workflows, *, extra_models=None, idle_stop=False):
        self.kind, self.runtime, self.workflows = kind, runtime, workflows
        self.client = ComfyWorkflows(runtime.host)
        self.extra_models = extra_models  # (models root, folder mapping) or None
        self.inventory = None
        self.state = 'unknown'
        self.error = ''
        self.active = False
        self.used = False          # OLIVE ran work on it in this session.
        self.legacy = lambda: False  # Media tools configured this endpoint.
        self._static = None
        self.idle_stop = idle_stop          # Stop an OLIVE-started engine after an idle period.
        self.idle_seconds = lambda: self.IDLE_DEFAULT
        self.lease = None                   # The asyncio.Lock every OLIVE GPU job holds.
        self.idle_stops = 0
        self._idle_task = None

    # ------------------------------------------------------------------ idle lifecycle
    def grace(self):
        try:
            seconds = float(self.idle_seconds())
        except Exception:
            seconds = self.IDLE_DEFAULT
        return max(self.IDLE_FLOOR, seconds)

    def touch(self):
        """OLIVE just used this engine: restart the idle countdown (only for an engine OLIVE started)."""
        self._cancel_idle()
        if not self.idle_stop or not self.runtime.owned():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._idle_task = loop.create_task(self._idle_watch())

    def _cancel_idle(self):
        task, self._idle_task = self._idle_task, None
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()

    async def _idle_watch(self):
        delay = self.grace()
        while True:
            await asyncio.sleep(delay)
            outcome = await self.stop_if_idle()
            if outcome != 'busy':
                return outcome
            delay = min(self.grace(), self.IDLE_RETRY)  # Text or media work held the lock: look again soon.

    async def stop_if_idle(self):
        """Stop the OLIVE-started engine if nothing uses it: 'stopped', 'busy' or 'not_owned'."""
        if not self.runtime.owned():
            return 'not_owned'  # A server someone else started is never stopped by OLIVE.
        lease = self.lease
        if self.active or (lease is not None and lease.locked()):
            return 'busy'
        if lease is not None:
            await lease.acquire()  # Held until the process is gone: no new job can start meanwhile.
        try:
            if self.active:
                return 'busy'
            if not self.runtime.owned():
                return 'not_owned'
            try:
                if await self.client.busy():
                    return 'busy'  # Work queued by another client on OLIVE's engine.
            except Exception:
                return 'busy'      # Cannot verify it is idle: look again later.
            await asyncio.shield(self.runtime.close())
            self.inventory, self.state = None, 'unknown'
            self.idle_stops += 1
            log.info('Stopped the idle OLIVE-owned %s engine after %s s', self.kind, self.grace())
            return 'stopped'
        finally:
            if lease is not None:
                lease.release()

    @property
    def endpoint(self):
        return self.runtime.host

    def installed(self):
        return self.runtime.installed()

    def configured(self):
        """An OLIVE media engine: discovered, configured in Media tools, or used.
        Anything else on the port is an unrelated application OLIVE leaves alone."""
        return self.installed() or self.used or bool(self.legacy())

    def version(self):
        try:
            text = Path(self.runtime.root, 'comfyui_version.py').read_text(errors='replace')
        except OSError:
            return ''
        match = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', text)
        return match.group(1) if match else ''

    def search_dirs(self, folder):
        dirs = [Path(self.runtime.root, 'models', folder)]
        if self.extra_models:
            root, mapping = self.extra_models
            dirs += [Path(root, sub) for sub in mapping.get(folder, [])]
        return dirs

    def static_inventory(self):
        """Installed files and reviewed custom nodes, without starting the engine."""
        inputs, modules = {}, {}
        for workflow in self.workflows:
            for key, name in workflow.files.items():
                names = inputs.setdefault(key, set())  # Several workflows share loader inputs.
                if any((directory / name).is_file()  # follows the store's symlinks
                       for folder in FOLDERS.get(key, ()) for directory in self.search_dirs(folder)):
                    names.add(name)
            for node, prefixes in workflow.nodes.items():
                if prefixes[0].startswith('custom_nodes.'):
                    folder = prefixes[0].split('.', 1)[1]
                    if Path(self.runtime.root, 'custom_nodes', folder, '__init__.py').is_file():
                        modules[node] = prefixes[0]
                else:
                    modules[node] = prefixes[0].rstrip('.')
        return {'version': self.version(), 'inputs': {k: tuple(v) for k, v in inputs.items()}, 'modules': modules}

    def cached_static_inventory(self):
        # Snapshots list presets often; a few file checks per 15 s are plenty.
        now = time.monotonic()
        if not self._static or now - self._static[0] > 15:
            self._static = (now, self.static_inventory())
        return self._static[1]

    def workflow_states(self, inventory=None):
        inventory = inventory or self.inventory or (self.cached_static_inventory() if self.installed() else None)
        return {w.key: availability(w, inventory) for w in self.workflows}

    def status(self):
        """Cached public state: not installed | available | starting | ready | busy | failed."""
        states = self.workflow_states() if self.installed() or self.inventory else {}
        ready = [key for key, value in states.items() if value == 'ready']
        if self.active:
            state = 'busy'
        elif self.runtime.state == 'starting':
            state = 'starting'
        elif self.state in {'failed', 'busy', 'ready'}:
            state = self.state
        elif self.installed():
            state = 'available'  # Installed; starts when a request needs it.
        else:
            state = 'not installed'
        if state not in {'not installed', 'failed'} and not ready:
            state = 'needs setup'
        return {'state': state, 'owned': self.runtime.owned(), 'workflows': states, 'ready_workflows': ready,
                'error': self.error, 'idle_stop_seconds': self.grace() if self.idle_stop else None,
                'idle_stops': self.idle_stops}

    def model_paths_config(self, directory):
        """Write the owned image runtime's read-only extra model path map."""
        if not self.extra_models:
            return None
        root, mapping = self.extra_models
        lines = ['olive_persistent_models:', f'  base_path: {Path(root).as_posix()}']
        for folder, subdirs in mapping.items():
            lines.append(f'  {folder}: |')
            lines += [f'    {sub}' for sub in subdirs]
        path = Path(directory) / f'{self.kind}-extra-model-paths.yaml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return path

    async def probe(self):
        """Refresh reachability/inventory of an already running engine; never starts it."""
        if not self.configured() or not await self.runtime.ready():
            if self.state not in {'failed'}:
                self.state = 'unknown'
            return self.status()
        try:
            self.inventory = await self.client.inventory(self.workflows)
            self.state = 'busy' if await self.client.busy() else 'ready'
            self.error = ''
        except Exception as error:
            self.state, self.error = 'failed', type(error).__name__
        return self.status()

    async def prepare(self, progress):
        """Start (if OLIVE may) and inspect; raise a specific public error otherwise."""
        if not self.configured():
            # A server nobody configured for OLIVE is someone else's; never borrow it.
            raise MediaError(f'{self.kind}_not_configured')
        if not await self.runtime.ready():
            if not self.installed():
                if port_bound(self.runtime.port):
                    raise MediaError('engine_unreachable', f'{self.kind} port bound but not ComfyUI')
                raise MediaError(f'{self.kind}_not_configured')
            progress(f'Starting {self.kind} engine…')
            try:
                await self.runtime.start_for(self.endpoint)
            except Exception as error:
                self.state, self.error = 'failed', type(error).__name__
                log.warning('%s engine failed to start: %s', self.kind, error)
                raise MediaError('engine_start_failed', str(error)) from None
            self.touch()  # Even if this request fails below, the started engine is not kept forever.
        try:
            self.inventory = await self.client.inventory(self.workflows)
        except Exception as error:
            self.state, self.error = 'failed', type(error).__name__
            raise MediaError('engine_unreachable', str(error)) from None
        if await self.client.busy():
            self.state = 'busy'
            raise MediaError('engine_busy')
        self.state = 'ready'
        self.used = True
        return self.inventory

    async def ensure_released(self):
        """No-op for unconfigured engines or a free port; otherwise require verified release."""
        if not self.configured() or not port_bound(self.runtime.port):
            return
        if not await self.runtime.ready():
            raise MediaError('gpu_release_unverified', f'{self.kind} port bound but unresponsive')
        try:
            await self.client.release_idle()
        except RuntimeError as error:
            raise MediaError('engine_busy' if 'busy' in str(error) else 'gpu_release_unverified', str(error)) from None

    async def close(self):
        self._cancel_idle()
        await self.runtime.close()  # Only an OLIVE-started process is stopped.


class MediaEngines:
    def __init__(self, config_dir, located=None):
        """`located` is runtime discovery's result; without it only environment overrides apply."""
        from .runtime_discovery import from_environment
        self.config_dir = Path(config_dir)
        located = located or from_environment()
        image_models = located['media_models'].get('path')
        image = LocalComfyRuntime(root=located['comfy'].get('root'), python=located['comfy'].get('python'))  # port 8188
        self.image = ComfyEngine('image', image, IMAGE_WORKFLOWS,
                                 extra_models=(image_models, IMAGE_EXTRA) if image_models else None, idle_stop=True)
        image.model_paths = lambda: self.image.model_paths_config(self.config_dir)
        video = LocalComfyRuntime(
            'http://127.0.0.1:8190', located['video_comfy'].get('root'), located['video_comfy'].get('python'),
            # The LTX 2.3 loader lives in this reviewed custom node; all others stay off.
            custom_nodes=('ComfyUI-GGUF-Loader',),
            # Matches the manually validated launch (dynamic VRAM for LTX on 16 GiB);
            # release is then verified from process GPU memory.
            allocator=(), label='Video ComfyUI')
        self.video = ComfyEngine('video', video, VIDEO_WORKFLOWS)

    def all(self):
        return (self.image, self.video)

    def get(self, kind):
        return {'image': self.image, 'video': self.video}[kind]

    def share_lease(self, residency):
        """Every OLIVE GPU job holds the model residency lock; idle stops take it too."""
        if residency is None:
            return
        for engine in self.all():
            engine.lease = residency.lock
            engine.idle_seconds = lambda: residency.policy()['keep_alive']

    async def release_others(self, keep=None):
        for engine in self.all():
            if engine is not keep:
                await engine.ensure_released()

    async def close(self):
        for engine in self.all():
            try:
                await engine.close()
            except Exception:
                log.exception('Media engine shutdown failed')
