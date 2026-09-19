"""Opt-in, lazy Linux ComfyUI process using the existing owned-runtime cleanup."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import httpx
from .local_ollama_runtime import LocalOllamaRuntime


class LocalComfyRuntime(LocalOllamaRuntime):
    def __init__(self):
        super().__init__('http://127.0.0.1:8188')
        self.root = os.environ.get('OLIVE_COMFY_ROOT', '')
        self.python = os.environ.get('OLIVE_COMFY_PYTHON', '')
        self.lock = asyncio.Lock()

    def manages(self, url):
        return sys.platform == 'linux' and bool(self.root and self.python) and url.rstrip('/') == self.host

    async def ready(self):
        try:
            async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
                response = await client.get(self.host + '/system_stats')
                return response.status_code == 200 and bool(response.json().get('system', {}).get('comfyui_version'))
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    async def start_for(self, url):
        if not self.manages(url):
            return
        async with self.lock:
            if await self.ready():
                return  # Existing engines remain externally owned.
            if not Path(self.root, 'main.py').is_file() or not Path(self.python).is_file():
                raise ValueError('The configured local ComfyUI runtime is missing')
            import fcntl
            import psutil
            from ..studio_tooling.posix_process import start_owned_process
            fd = os.open(Path(self.root) / '.olive-start.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                for _ in range(600):
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        await asyncio.sleep(.1)
                else:
                    raise TimeoutError('Another ComfyUI startup is still pending')
                if await self.ready():
                    return
                self.process = await start_owned_process([
                    self.python, str(Path(self.root) / 'main.py'), '--listen', '127.0.0.1', '--port', '8188',
                    '--disable-auto-launch', '--disable-all-custom-nodes', '--disable-api-nodes', '--disable-cuda-malloc',
                    '--disable-dynamic-vram', '--cache-none'], cwd=self.root, env=dict(os.environ),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.owner = psutil.Process(self.process.pid)
                for _ in range(600):
                    if await self.ready():
                        return
                    if self.process.returncode is not None:
                        raise RuntimeError('The configured local ComfyUI runtime exited during startup')
                    await asyncio.sleep(.1)
                raise TimeoutError('Local ComfyUI startup timed out')
            except BaseException:
                await self.close()
                raise
            finally:
                os.close(fd)
