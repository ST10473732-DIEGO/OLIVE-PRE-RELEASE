"""Optional Linux app-owned Ollama lifecycle; existing servers remain external."""
import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

import httpx


class LocalOllamaRuntime:
    def __init__(self, host):
        self.host = host
        self.process = None
        self.owner = None

    async def ready(self):
        try:
            async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
                response = await client.get(self.host.rstrip('/') + '/api/version')
                return response.status_code == 200 and isinstance(response.json().get('version'), str)
        except (httpx.HTTPError, ValueError, AttributeError):
            return False

    async def start(self):
        if sys.platform != 'linux' or os.environ.get('OLIVE_START_OLLAMA') != '1':
            return
        endpoint = urlsplit(self.host)
        # Only the ordinary local endpoint is auto-started. Explicit alternate
        # endpoints, remote hosts and test providers remain user-managed.
        if endpoint.scheme != 'http' or endpoint.hostname not in {'localhost', '127.0.0.1'} or endpoint.port != 11434:
            return
        if await self.ready():
            return
        executable = shutil.which('ollama')
        if not executable:
            return
        import fcntl
        runtime = os.environ.get('XDG_RUNTIME_DIR')
        directory = Path(runtime) if runtime and Path(runtime).is_absolute() else Path.home() / '.cache' / 'olive'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(directory / 'olive-ollama-start.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            for _ in range(300):
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(.1)
            else:
                raise TimeoutError('Another local Ollama startup is still pending')
            if await self.ready():
                return
            env = dict(os.environ, OLLAMA_HOST='127.0.0.1:11434', OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_NO_CLOUD='1', OLLAMA_NOPRUNE='1')
            import psutil
            from ..studio_tooling.posix_process import start_owned_process
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
            os.close(fd)

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
