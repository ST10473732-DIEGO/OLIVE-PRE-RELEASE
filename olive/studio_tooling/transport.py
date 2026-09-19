"""Content-Length framed JSON message transport over a child process (LSP and DAP)."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys

MAX_MESSAGE = 16 * 1024 * 1024


class ProcessTransport:
    """Owns one child process and frames JSON messages on its stdio.

    The caller supplies `on_message(dict)`; `on_exit(code)` fires once when the
    process ends for any reason. Writes are serialised; reads run in a task.
    """

    def __init__(self, command: list[str], cwd: str, env: dict[str, str] | None, on_message, on_exit):
        self.command = command
        self.cwd = cwd
        self.env = env
        self.on_message = on_message
        self.on_exit = on_exit
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()
        self.stderr_tail: list[str] = []
        self.exited = asyncio.Event()
        self.exit_code: int | None = None

    async def start(self):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        options = dict(cwd=self.cwd, env=self.env, stdin=asyncio.subprocess.PIPE,
                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=MAX_MESSAGE)
        if sys.platform == "linux":
            from .posix_process import start_owned_process
            self.process = await start_owned_process(self.command, **options)
        else:
            self.process = await asyncio.create_subprocess_exec(*self.command, creationflags=flags, **options)
        self._reader_task = asyncio.create_task(self._read())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    @property
    def alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def send(self, message: dict):
        if not self.alive:
            raise ConnectionError("The tooling process is not running")
        data = json.dumps(message, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(data) > MAX_MESSAGE:
            raise ValueError("Message exceeds the supported size")
        async with self._write_lock:
            assert self.process and self.process.stdin
            self.process.stdin.write(b"Content-Length: %d\r\n\r\n" % len(data) + data)
            await self.process.stdin.drain()

    async def _read(self):
        assert self.process and self.process.stdout
        stream = self.process.stdout
        try:
            while True:
                length = None
                while True:
                    line = await stream.readline()
                    if not line:
                        return
                    if line in (b"\r\n", b"\n"):
                        break
                    name, _, value = line.decode("ascii", "replace").partition(":")
                    if name.strip().lower() == "content-length":
                        length = int(value.strip())
                if length is None or length < 0 or length > MAX_MESSAGE:
                    return
                body = await stream.readexactly(length)
                try:
                    message = json.loads(body.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if isinstance(message, dict):
                    try:
                        result = self.on_message(message)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:  # A handler fault must not kill the reader.
                        pass
        except (asyncio.IncompleteReadError, ConnectionError, ValueError):
            return
        finally:
            await self._finish()

    async def _read_stderr(self):
        assert self.process and self.process.stderr
        try:
            while line := await self.process.stderr.readline():
                text = line.decode("utf-8", "replace").rstrip()
                if text:
                    self.stderr_tail.append(text[:500])
                    del self.stderr_tail[:-40]
        except (ConnectionError, ValueError):
            return

    async def _finish(self):
        if self.exited.is_set():
            return
        if self.process is not None:
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            self.exit_code = self.process.returncode
        self.exited.set()
        try:
            result = self.on_exit(self.exit_code)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def stop(self, grace: float = 3.0):
        if self.process is None:
            return
        if self.process.returncode is None:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.process.wait(), timeout=grace)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self._reader_task:
            try:
                await asyncio.wait_for(self._reader_task, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._reader_task.cancel()
        await self._finish()
