"""Optional app-owned Ollama lifecycle; existing servers remain external.

Linux is the validated platform. Windows and macOS use the same flow through
olive.runtime.processes and are reported as unvalidated until accepted there.
The executable comes from runtime discovery (an OLIVE-owned runtime, a persisted
choice or a system installation), never from a launcher script's PATH alone.
"""
import asyncio
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

import httpx


class LocalOllamaRuntime:
    def __init__(self, host, executable=None, models=None):
        self.host = host
        self.process = None
        self.owner = None
        # A discovered executable (str) or a callable returning one; PATH is the fallback.
        self.executable = executable
        self.models = models  # Persisted OLLAMA_MODELS for an owned server, if any.

    def resolve_executable(self):
        value = self.executable() if callable(self.executable) else self.executable
        return value or shutil.which('ollama')

    async def ready(self):
        try:
            async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
                response = await client.get(self.host.rstrip('/') + '/api/version')
                return response.status_code == 200 and isinstance(response.json().get('version'), str)
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    async def start(self):
        from ..runtime.processes import supported
        if not supported() or os.environ.get('OLIVE_START_OLLAMA') != '1':
            return
        endpoint = urlsplit(self.host)
        # Only the ordinary local endpoint is auto-started. Explicit alternate
        # endpoints, remote hosts and test providers remain user-managed.
        if endpoint.scheme != 'http' or endpoint.hostname not in {'localhost', '127.0.0.1'} or endpoint.port != 11434:
            return
        if await self.ready():
            return
        executable = self.resolve_executable()
        if not executable:
            return
        from .. import app_paths
        from ..runtime.processes import StartLock, start_owned_process
        directory = Path(app_paths.lock_directory())
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = StartLock(directory / 'olive-ollama-start.lock').open()
        try:
            await lock.acquire(300, 'Another local Ollama startup is still pending')
            if await self.ready():
                return
            env = dict(os.environ, OLLAMA_HOST='127.0.0.1:11434', OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_NO_CLOUD='1', OLLAMA_NOPRUNE='1')
            if self.models and not env.get('OLLAMA_MODELS'):
                env['OLLAMA_MODELS'] = str(self.models)
            import psutil
            self.process = await start_owned_process(
                [executable, 'serve'], env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.owner = psutil.Process(self.process.pid)
            for _ in range(150):
                if await self.ready():
                    return
                if self.process.returncode is not None:
                    raise RuntimeError('The local Ollama server exited during startup')
                await asyncio.sleep(.1)
            raise TimeoutError('Local Ollama startup timed out')
        except BaseException:
            await self.close()
            raise
        finally:
            lock.close()

    async def close(self):
        process = self.process
        if process is None:
            return  # Never stop an existing system/user service.
        self.process = None
        owner, self.owner = self.owner, None
        import psutil
        try:
            descendants = owner.children(recursive=True) if owner and owner.is_running() else []
        except psutil.NoSuchProcess:
            descendants = []
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        for child in descendants:
            try:
                if child.is_running():
                    child.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = await asyncio.to_thread(psutil.wait_procs, descendants, timeout=2)
        for child in alive:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        if alive:
            await asyncio.to_thread(psutil.wait_procs, alive, timeout=2)
