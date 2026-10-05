"""Interactive sessions through Windows ConPTY or a native Linux PTY.

A terminal session is a trusted native shell started for an approved workspace
after the terminal tool's permission and audit path. It runs with the user's
real operating-system permissions; the working directory is a convenience,
not a sandbox. Output is streamed as `terminal.data` events with coalescing
so a chatty program cannot flood the bridge. Closing the view does not end
the process; `close` (kill) does.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

MAX_CHUNK = 16 * 1024
FLUSH_INTERVAL = 0.02
MAX_INPUT = 64 * 1024
SHELLS = {
    "powershell": ["powershell.exe", "-NoLogo", "-NoProfile"],
    "cmd": ["cmd.exe"],
}


def shell_command(shell: str) -> tuple[str, str]:
    if shell not in SHELLS:
        raise ValueError("Unsupported shell")
    parts = SHELLS[shell]
    executable = shutil.which(parts[0]) or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", parts[0])
    return executable, " ".join(parts[1:])


class TerminalSession:
    def __init__(self, session_id: str, workspace_id: str, cwd: str, shell: str, title: str, loop: asyncio.AbstractEventLoop, publish):
        self.id = session_id
        self.workspace_id = workspace_id
        self.cwd = cwd
        self.shell = shell
        self.title = title
        self.loop = loop
        self.publish = publish
        self.pty = None
        self.pid: int | None = None
        self.state = "starting"
        self.exit_code: int | None = None
        self.created_at = time.time()
        self.columns, self.rows = 100, 30
        self.bytes_out = 0
        self._reader: threading.Thread | None = None
        self._closing = False
        self._pending = []
        self._pending_lock = threading.Lock()
        self._flush_handle = None

    def start(self, environment: dict[str, str], command=None):
        if sys.platform == 'linux':
            from .posix_pty import PosixPTY
            self.pty = PosixPTY(self.columns, self.rows, self.cwd, environment, self.shell, command)
            self.pid = self.pty.pid
            self.state = "running"
            self._reader = threading.Thread(target=self._read_loop, name=f"olive-pty-{self.id[:8]}", daemon=True)
            self._reader.start()
            return
        from ..platform_support import PlatformUnavailable, unavailable_message
        if sys.platform != 'win32':
            raise PlatformUnavailable(unavailable_message('Studio interactive terminal'))  # macOS: not yet.
        import importlib.util
        if importlib.util.find_spec("winpty") is None:
            # pywinpty is a core Windows dependency (packaged backends include it); a source
            # environment installed without requirements.txt can still lack it.
            raise PlatformUnavailable("The Studio terminal on Windows needs pywinpty, which is missing from this "
                                      "Python environment. Install OLIVE's requirements.txt.")
        import winpty
        if command:
            executable = shutil.which(command[0], path=environment.get('PATH')) or command[0]
            arguments = subprocess.list2cmdline(command[1:])
        else:
            executable, arguments = shell_command(self.shell)
        env_block = "\0".join(f"{key}={value}" for key, value in environment.items()) + "\0"
        self.pty = winpty.PTY(self.columns, self.rows, backend=winpty.Backend.ConPTY)
        if not self.pty.spawn(executable, arguments or None, self.cwd, env_block):
            raise RuntimeError("The terminal process could not be started")
        self.pid = self.pty.pid
        self.state = "running"
        self._reader = threading.Thread(target=self._read_loop, name=f"olive-pty-{self.id[:8]}", daemon=True)
        self._reader.start()

    def _read_loop(self):
        while not self._closing:
            try:
                alive = self.pty.isalive()
                data = self.pty.read(blocking=False)
            except Exception:
                break
            if data:
                with self._pending_lock:
                    self._pending.append(data)
                if not self._closing and not self.loop.is_closed():
                    self.loop.call_soon_threadsafe(self._schedule_flush)
            elif not alive:
                break
            else:
                time.sleep(0.01)
        try:
            self.exit_code = self.pty.get_exitstatus()
        except Exception:
            self.exit_code = None
        if not self._closing and not self.loop.is_closed():
            self.state = "exited"
            self.loop.call_soon_threadsafe(self._flush)
            self.loop.call_soon_threadsafe(self.publish, "terminal.state", self.status())

    def _schedule_flush(self):
        if self._flush_handle is None:
            self._flush_handle = self.loop.call_later(FLUSH_INTERVAL, self._flush)

    def _flush(self):
        self._flush_handle = None
        with self._pending_lock:
            if not self._pending:
                return
            text = "".join(self._pending)
            self._pending.clear()
        # Coalesced but bounded: a flood is split into chunks the renderer can paint.
        for start in range(0, len(text), MAX_CHUNK):
            chunk = text[start:start + MAX_CHUNK]
            self.bytes_out += len(chunk)
            self.publish("terminal.data", {"session_id": self.id, "workspace_id": self.workspace_id, "data": chunk})

    def write(self, data: str):
        if self.state != "running" or not self.pty:
            raise ValueError("The terminal is not running")
        if len(data) > MAX_INPUT:
            raise ValueError("Input exceeds the supported size")
        self.pty.write(data)

    def resize(self, columns: int, rows: int):
        columns = max(20, min(500, int(columns)))
        rows = max(5, min(200, int(rows)))
        self.columns, self.rows = columns, rows
        if self.pty and self.state == "running":
            self.pty.set_size(columns, rows)

    def kill(self):
        self._closing = True
        if self.pty and self.state == "running" and sys.platform == "linux":
            self.pty.terminate()
            self.exit_code = self.pty.process.returncode
        elif self.pty and self.state == "running":
            # Capture only descendants of this owned PTY process. psutil retains
            # creation identity and refuses to signal a subsequently reused PID.
            import psutil
            try:
                children = psutil.Process(self.pid).children(recursive=True)
            except psutil.Error:
                children = []
            for child in reversed(children):
                try:
                    child.kill()
                except psutil.Error:
                    pass
            try:
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.OpenProcess(0x100001, False, int(self.pid))
                if handle:
                    try:
                        kernel.TerminateProcess(handle, 1)
                        # Termination is asynchronous; retain the handle until the
                        # shell releases its working directory before close returns.
                        kernel.WaitForSingleObject(handle, 2000)
                    finally:
                        kernel.CloseHandle(handle)
            except Exception:
                pass
            psutil.wait_procs(children, timeout=2)
            try:
                self.pty.cancel_io()
            except Exception:
                pass
        self.state = "closed"
        if self._reader and self._reader is not threading.current_thread():
            self._reader.join(timeout=1)
        if self._flush_handle:
            self._flush_handle.cancel()
            self._flush_handle = None

    def status(self) -> dict:
        return {"platform": sys.platform, "session_id": self.id, "workspace_id": self.workspace_id, "title": self.title, "shell": self.shell, "cwd": self.cwd,
                "state": self.state, "pid": self.pid, "exit_code": self.exit_code, "columns": self.columns, "rows": self.rows,
                "trust": "native", "created_at": self.created_at}


class TerminalServices:
    def __init__(self, publish):
        self.publish = publish
        self.sessions: dict[str, TerminalSession] = {}

    def create(self, workspace_id: str, root: str, shell: str, environment: dict[str, str], title: str = "", command=None, publish=None) -> TerminalSession:
        if sum(1 for s in self.sessions.values() if s.workspace_id == workspace_id and s.state == "running") >= 6:
            raise ValueError("Close a terminal before opening more (limit 6 per workspace)")
        cwd = str(Path(root).resolve())
        number = sum(1 for s in self.sessions.values() if s.workspace_id == workspace_id) + 1
        session = TerminalSession(uuid.uuid4().hex, workspace_id, cwd, shell, title or f"Terminal {number}", asyncio.get_running_loop(), publish or self.publish)
        session.start(environment, command)
        self.sessions[session.id] = session
        self.publish("terminal.state", session.status())
        return session

    def require(self, session_id: str) -> TerminalSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError("Unknown terminal session")
        return session

    def close(self, session_id: str):
        session = self.require(session_id)
        session.kill()
        session._flush()
        session.publish("terminal.state", session.status())
        self.sessions.pop(session_id, None)

    def close_all(self):
        for session_id in list(self.sessions):
            try:
                self.close(session_id)
            except Exception:
                pass

    def list(self, workspace_id: str) -> list[dict]:
        return [s.status() for s in self.sessions.values() if s.workspace_id == workspace_id]


class ProgramProcess:
    """Adapt the existing terminal to RunService's observed process lifecycle."""

    def __init__(self, terminals, workspace_id, cwd, command, environment):
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_eof()  # A PTY has one combined output stream.
        self.returncode = None
        self._done = asyncio.Event()
        self.stdin = self

        def publish(topic, value):
            terminals.publish(topic, value)
            if topic == 'terminal.data':
                self.stdout.feed_data(value['data'].encode('utf-8'))
            elif topic == 'terminal.state' and value['state'] != 'running':
                self._finish(value['exit_code'])

        self.terminal = terminals.create(workspace_id, cwd, 'program', environment,
                                         'Run program', command=command, publish=publish)
        self.pid = self.terminal.pid

    def _finish(self, code):
        if not self._done.is_set():
            self.returncode = code if code is not None else 1
            self.stdout.feed_eof()
            self._done.set()

    async def wait(self):
        await self._done.wait()
        return self.returncode

    def kill(self):
        self.terminal.kill()
        self.terminal._flush()
        self.terminal.publish('terminal.state', self.terminal.status())

    def is_closing(self):
        return self.terminal.state != 'running'

    def write(self, data):
        self.terminal.write(data.decode('utf-8').replace('\r\n', '\r').replace('\n', '\r'))

    async def drain(self):
        await asyncio.sleep(0)

    def close(self):
        self.terminal.write('\x04' if sys.platform == 'linux' else '\x1a\r')
