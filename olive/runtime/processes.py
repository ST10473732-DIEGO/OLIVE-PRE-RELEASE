"""Platform dispatch for OLIVE-owned runtime processes (Ollama, ComfyUI, VoiceStudio).

Linux   private supervisor (PR_SET_CHILD_SUBREAPER) that reaps the whole subtree.
Windows kill-on-close Job Object; no console window.
macOS   a new session whose process group is signalled on stop. Descendants that
        start their own session are still found through the owner's psutil
        snapshot in LocalOllamaRuntime.close; there is no parent-death signal, so
        an OLIVE crash can leave a runtime running (it is reused, never duplicated,
        on the next start because every runtime probes its port first).
"""
import asyncio
import os
import signal
import sys

from ..platform_support import PlatformUnavailable, unavailable_message

SUPPORTED = ('linux', 'win32', 'darwin')
CREATE_NO_WINDOW = 0x08000000


def supported(platform=None):
    return (sys.platform if platform is None else platform) in SUPPORTED


class SessionProcess:
    """A macOS child owning its own process group."""

    def __init__(self, process):
        self.process = process

    def __getattr__(self, name):
        return getattr(self.process, name)

    def _signal(self, number):
        try:
            os.killpg(self.process.pid, number)
        except (ProcessLookupError, PermissionError):
            pass

    def terminate(self):
        self._signal(signal.SIGTERM)

    def kill(self):
        self._signal(signal.SIGKILL)


async def _start_session(command, **options):
    process = await asyncio.create_subprocess_exec(*command, start_new_session=True, **options)
    return SessionProcess(process)


async def start_owned_process(command, **options):
    if sys.platform == 'linux':
        from ..studio_tooling.posix_process import start_owned_process as start
    elif sys.platform == 'win32':
        from ..studio_tooling.windows_process import start_owned_process as start
        options['creationflags'] = options.get('creationflags', 0) | CREATE_NO_WINDOW
    elif sys.platform == 'darwin':
        start = _start_session
    else:
        raise PlatformUnavailable(unavailable_message('Starting local runtimes'))
    return await start(command, **options)


class StartLock:
    """Non-blocking exclusive file lock shared by every OLIVE process on this machine."""

    def __init__(self, path):
        self.path = path
        self.fd = None

    def open(self):
        flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
        self.fd = os.open(self.path, flags, 0o600)
        return self

    def try_acquire(self):
        if sys.platform == 'win32':
            import msvcrt
            try:
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        import fcntl
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    async def acquire(self, attempts, message):
        for _ in range(attempts):
            if self.try_acquire():
                return
            await asyncio.sleep(.1)
        raise TimeoutError(message)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)  # Closing releases flock/msvcrt locks.
            self.fd = None
