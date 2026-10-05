"""Opt-in, lazy ComfyUI processes using the existing owned-runtime cleanup.

One class manages each separately installed runtime (image on 8188, video on
8190). A server already listening is reused and never stopped; only a
process OLIVE itself started is shut down. Locations come from runtime
discovery. Linux is validated; Windows (portable or venv layout) and macOS use
the same launch through olive.runtime.processes and are reported unvalidated.
The video runtime keeps its reviewed GGUF loader on every platform.
"""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
import httpx
from .local_ollama_runtime import LocalOllamaRuntime

# Allocator flags make GPU release measurable through /system_stats.
MEASURED_ALLOCATOR = ('--disable-cuda-malloc', '--disable-dynamic-vram')


class LocalComfyRuntime(LocalOllamaRuntime):
    def __init__(self, host='http://127.0.0.1:8188', root=None, python=None, *, custom_nodes=(),
                 model_paths=None, allocator=MEASURED_ALLOCATOR, label='ComfyUI'):
        super().__init__(host)
        self.root = os.environ.get('OLIVE_COMFY_ROOT', '') if root is None else root
        self.python = os.environ.get('OLIVE_COMFY_PYTHON', '') if python is None else python
        self.custom_nodes = tuple(custom_nodes)
        self.model_paths = model_paths  # Callable returning an extra_model_paths.yaml, or None.
        self.allocator = tuple(allocator)
        self.label = label
        self.lock = asyncio.Lock()
        self.state = 'idle'  # idle | starting | failed; readiness is probed live.

    @property
    def port(self):
        return urlsplit(self.host).port

    def installed(self):
        return bool(self.root and self.python and Path(self.root, 'main.py').is_file() and Path(self.python).is_file())

    def manages(self, url):
        from ..runtime.processes import supported
        return supported() and bool(self.root and self.python) and url.rstrip('/') == self.host

    def owned(self):
        return self.process is not None and self.process.returncode is None

    async def ready(self):
        try:
            async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
                response = await client.get(self.host + '/system_stats')
                return response.status_code == 200 and bool(response.json().get('system', {}).get('comfyui_version'))
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    def arguments(self):
        # The Windows portable build expects its embedded Python without user site-packages.
        windows = ['-s'] if sys.platform == 'win32' else []
        arguments = [self.python, *windows, str(Path(self.root) / 'main.py'), '--listen', '127.0.0.1', '--port', str(self.port),
                     '--disable-auto-launch', '--disable-all-custom-nodes', '--disable-api-nodes', *self.allocator, '--cache-none']
        if sys.platform == 'win32':
            arguments.append('--windows-standalone-build')
        if self.custom_nodes:
            # Only reviewed custom node folders load; everything else stays off.
            arguments += ['--whitelist-custom-nodes', *self.custom_nodes]
        config = self.model_paths() if self.model_paths else None
        if config:
            arguments += ['--extra-model-paths-config', str(config)]
        return arguments

    async def start_for(self, url):
        if not self.manages(url):
            return
        async with self.lock:
            if await self.ready():
                return  # Existing engines remain externally owned.
            if not Path(self.root, 'main.py').is_file() or not Path(self.python).is_file():
                self.state = 'failed'
                raise ValueError('The configured local ComfyUI runtime is missing')
            import psutil
            from ..runtime.processes import StartLock, start_owned_process
            lock = StartLock(Path(self.root) / '.olive-start.lock').open()
            self.state = 'starting'
            try:
                await lock.acquire(600, 'Another ComfyUI startup is still pending')
                if await self.ready():
                    self.state = 'idle'
                    return
                self.process = await start_owned_process(
                    self.arguments(), cwd=self.root, env=dict(os.environ),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.owner = psutil.Process(self.process.pid)
                # Custom-node and model scans on a cold cache take longer than 60 s.
                for _ in range(1800):
                    if await self.ready():
                        self.state = 'idle'
                        return
                    if self.process.returncode is not None:
                        raise RuntimeError('The configured local ComfyUI runtime exited during startup')
                    await asyncio.sleep(.1)
                raise TimeoutError('Local ComfyUI startup timed out')
            except BaseException:
                self.state = 'failed'
                await self.close()
                raise
            finally:
                lock.close()
