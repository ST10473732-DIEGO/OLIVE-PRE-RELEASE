"""Debug Adapter Protocol client sessions (netcoredbg for .NET, debugpy for Python).

Every adapter is an owned child process; the debuggee is launched by the adapter
under the workspace's execution policy environment. Adapter events are forwarded
verbatim as `dap.event` bridge events so the renderer renders actual debugger
state. Suspended-state references (frames, variables) are only valid between a
`stopped` event and the next resume; the renderer discards them on `continued`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import time
import sys
import uuid

from .toolchain import PINNED, python_executable, module_available
from .transport import ProcessTransport

REQUEST_TIMEOUT = 60.0
FORWARDED_REQUESTS = {
    "setBreakpoints", "setFunctionBreakpoints", "setExceptionBreakpoints", "threads", "stackTrace", "scopes", "variables",
    "evaluate", "next", "stepIn", "stepOut", "continue", "pause", "setVariable", "exceptionInfo", "source",
}


class DebugSession:
    def __init__(self, session_id: str, workspace_id: str, root: str, adapter: str, command: list[str], env: dict[str, str],
                 launch: dict, publish):
        self.id = session_id
        self.workspace_id = workspace_id
        self.root = root
        self.adapter = adapter
        self.command = command
        self.env = env
        self.launch_arguments = launch
        self.publish = publish
        self.transport: ProcessTransport | None = None
        self.state = "starting"
        self.detail = ""
        self.started_at = time.time()
        self.capabilities: dict = {}
        self.suspended = False
        self.stopped_thread: int | None = None
        self.generation = 0  # bumps on every resume so stale variable references can be rejected
        self.breakpoints: dict[str, list[dict]] = {}
        self.output: list[dict] = []
        self._seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._initialized = asyncio.Event()
        self.exit_code: int | None = None

    # ---- lifecycle -----------------------------------------------------
    async def start(self):
        self.transport = ProcessTransport(self.command, self.root, self.env, self._on_message, self._on_exit)
        await self.transport.start()
        response = await self.request("initialize", {
            "clientID": "olive", "clientName": "OLIVE Studio", "adapterID": self.adapter, "locale": "en",
            "linesStartAt1": True, "columnsStartAt1": True, "pathFormat": "path",
            "supportsVariableType": True, "supportsVariablePaging": False, "supportsRunInTerminalRequest": False,
            "supportsProgressReporting": False,
        })
        self.capabilities = response.get("body") or {}
        launch_future = asyncio.create_task(self.request("launch", self.launch_arguments, timeout=180))
        try:
            await asyncio.wait_for(self._initialized.wait(), timeout=60)
        except asyncio.TimeoutError:
            launch_future.cancel()
            raise TimeoutError("The debug adapter did not report initialized")
        for path, items in self.breakpoints.items():
            await self.set_breakpoints(path, items)
        try:
            await self.request("setExceptionBreakpoints", {"filters": ["user-unhandled"]})
        except Exception:
            pass
        if self.capabilities.get("supportsConfigurationDoneRequest", True):
            await self.request("configurationDone", {})
        launch = await launch_future
        if not launch.get("success", False):
            self.state = "failed"
            self.detail = str(launch.get("message", "Launch failed"))[:400]
            self._publish_state()
            raise RuntimeError(self.detail)
        self.state = "running"
        self._publish_state()

    async def stop(self, terminate: bool = True):
        if self.transport and self.transport.alive:
            if self.state not in ("terminated", "stopped"):
                try:
                    await asyncio.wait_for(self.request("disconnect", {"terminateDebuggee": terminate}, timeout=10), timeout=12)
                except Exception:
                    pass
            await self.transport.stop()
        self.state = "stopped"
        self.suspended = False
        self._publish_state()

    async def _on_exit(self, code):
        if self.state not in ("stopped",):
            self.state = "terminated" if self.state in ("running", "suspended", "terminated") else "failed"
            if code not in (0, None) and self.state == "failed":
                self.detail = f"Debug adapter exited with code {code}"
        self.suspended = False
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Debug adapter exited"))
        self._pending.clear()
        self._publish_state()

    def _publish_state(self):
        self.publish("dap.state", self.status())

    def status(self) -> dict:
        return {"session_id": self.id, "workspace_id": self.workspace_id, "adapter": self.adapter, "state": self.state,
                "detail": self.detail, "suspended": self.suspended, "thread_id": self.stopped_thread,
                "generation": self.generation, "exit_code": self.exit_code, "provider": Path(self.command[0]).name,
                "capabilities": {k: v for k, v in self.capabilities.items() if isinstance(v, bool) and v},
                "exception_filters": [{"filter": str(f.get("filter", "")), "label": str(f.get("label", "")), "default": bool(f.get("default"))}
                                      for f in (self.capabilities.get("exceptionBreakpointFilters") or []) if isinstance(f, dict)][:20]}

    # ---- messaging -----------------------------------------------------
    async def request(self, command: str, arguments: dict | None = None, timeout: float = REQUEST_TIMEOUT) -> dict:
        if not self.transport or not self.transport.alive:
            raise ConnectionError("The debug adapter is not running")
        self._seq += 1
        seq = self._seq
        future = asyncio.get_running_loop().create_future()
        self._pending[seq] = future
        await self.transport.send({"seq": seq, "type": "request", "command": command, "arguments": arguments or {}})
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(seq, None)
            raise TimeoutError(f"Debugger request {command} timed out")

    async def _on_message(self, message: dict):
        kind = message.get("type")
        if kind == "response":
            future = self._pending.pop(message.get("request_seq"), None)
            if future and not future.done():
                future.set_result(message)
        elif kind == "event":
            self._event(message.get("event", ""), message.get("body") or {})
        elif kind == "request":
            # Reverse requests (runInTerminal) are not supported; refuse explicitly.
            await self.transport.send({"seq": 0, "type": "response", "request_seq": message.get("seq"), "success": False,
                                       "command": message.get("command"), "message": "Reverse requests are not supported"})

    def _event(self, name: str, body: dict):
        if name == "initialized":
            self._initialized.set()
        elif name == "stopped":
            self.suspended = True
            self.state = "suspended"
            self.stopped_thread = body.get("threadId")
        elif name == "continued":
            self.suspended = False
            self.state = "running"
            self.generation += 1
        elif name == "terminated":
            self.suspended = False
            self.state = "terminated"
            self.generation += 1
        elif name == "exited":
            self.exit_code = body.get("exitCode")
        elif name == "output":
            self.output.append({"category": body.get("category", "console"), "output": str(body.get("output", ""))[:20000]})
            del self.output[:-2000]
        elif name == "breakpoint":
            item = body.get("breakpoint") or {}
            source = (item.get("source") or {}).get("path")
            if source:
                for stored in self.breakpoints.get(str(Path(source).resolve()), []):
                    if stored.get("id") == item.get("id") or stored.get("line") == item.get("line"):
                        stored.update({"verified": item.get("verified", False), "message": item.get("message", ""), "id": item.get("id")})
        self.publish("dap.event", {"session_id": self.id, "workspace_id": self.workspace_id, "event": name, "body": body,
                                   "generation": self.generation, "state": self.state})

    # ---- operations ----------------------------------------------------
    async def set_breakpoints(self, path: str, lines: list[dict]) -> list[dict]:
        path = str(Path(path).resolve())
        wanted = [{"line": int(item["line"]), **({"condition": str(item["condition"])} if item.get("condition") else {})} for item in lines[:200]]
        self.breakpoints[path] = [dict(item, verified=False) for item in wanted]
        if not (self.transport and self.transport.alive):
            return self.breakpoints[path]
        response = await self.request("setBreakpoints", {"source": {"path": path, "name": Path(path).name}, "breakpoints": wanted,
                                                          "lines": [item["line"] for item in wanted], "sourceModified": False})
        result = (response.get("body") or {}).get("breakpoints") or []
        merged = []
        for index, item in enumerate(wanted):
            actual = result[index] if index < len(result) else {}
            merged.append({"line": actual.get("line", item["line"]), "requested_line": item["line"], "verified": bool(actual.get("verified")),
                           "message": actual.get("message", ""), "id": actual.get("id"), "condition": item.get("condition", "")})
        self.breakpoints[path] = merged
        return merged

    async def forward(self, command: str, arguments: dict, generation: int | None = None) -> dict:
        if command not in FORWARDED_REQUESTS:
            raise ValueError("Unsupported debugger request")
        if command in ("stackTrace", "scopes", "variables", "evaluate", "setVariable") and generation is not None and generation != self.generation:
            raise ValueError("Stale debugger state: execution resumed since this view was captured")
        if command in ("evaluate", "setVariable") and not self.suspended:
            raise ValueError("Evaluation is only possible while the program is paused")
        response = await self.request(command, arguments)
        if not response.get("success", False):
            raise RuntimeError(str(response.get("message") or f"{command} failed")[:400])
        return response.get("body") or {}


def dotnet_launch(program: str, cwd: str, args: list[str], env: dict[str, str], stop_at_entry: bool = False) -> dict:
    return {"type": "coreclr", "request": "launch", "name": "OLIVE .NET debug", "program": program, "args": args, "cwd": cwd,
            "env": env, "stopAtEntry": stop_at_entry, "console": "internalConsole", "justMyCode": True,
            "internalConsoleOptions": "neverOpen"}


def python_launch(program: str, cwd: str, args: list[str], env: dict[str, str], python: str, stop_at_entry: bool = False) -> dict:
    return {"type": "python", "request": "launch", "name": "OLIVE Python debug", "program": program, "args": args, "cwd": cwd,
            "env": env, "python": python, "stopOnEntry": stop_at_entry, "console": "internalConsole", "justMyCode": True,
            "redirectOutput": True}


class DebugServices:
    def __init__(self, publish):
        self.publish = publish
        self.sessions: dict[str, DebugSession] = {}
        self.workspace_breakpoints: dict[str, dict[str, list[dict]]] = {}

    def active(self, workspace_id: str) -> DebugSession | None:
        for session in self.sessions.values():
            if session.workspace_id == workspace_id and session.state in ("starting", "running", "suspended"):
                return session
        return None

    async def launch(self, workspace_id: str, root: str, adapter: str, launch: dict, env: dict[str, str]) -> DebugSession:
        if self.active(workspace_id):
            raise ValueError("A debug session is already running in this workspace")
        if adapter == "coreclr":
            executable = PINNED["netcoredbg"]["executable"]
            if not executable.is_file():
                raise FileNotFoundError("netcoredbg is not provisioned. Run scripts/provision_studio_tooling.py.")
            command = [str(executable), "--interpreter=vscode"]
        elif adapter == "python":
            python = launch.get("python") or python_executable(root)
            adapter_python = python if module_available(python, "debugpy") else sys.executable
            if not module_available(adapter_python, "debugpy"):
                raise FileNotFoundError("debugpy is not installed. Run scripts/provision_studio_tooling.py.")
            launch = dict(launch, python=python)
            command = [adapter_python, "-m", "debugpy.adapter"]
        else:
            raise ValueError("Unsupported debug adapter")
        session = DebugSession(uuid.uuid4().hex, workspace_id, root, adapter, command, env, launch, self.publish)
        for path, items in self.workspace_breakpoints.get(workspace_id, {}).items():
            session.breakpoints[path] = [dict(item) for item in items]
        self.sessions[session.id] = session
        try:
            await session.start()
        except Exception:
            await session.stop()
            raise
        return session

    async def stop(self, session_id: str, terminate: bool = True):
        session = self.sessions.get(session_id)
        if session:
            await session.stop(terminate)

    async def stop_all(self):
        # Application exit: every debug session at once, not one after another.
        sessions = list(self.sessions.values())
        if not sessions:
            return
        await asyncio.gather(*(session.stop() for session in sessions), return_exceptions=True)

    def remember_breakpoints(self, workspace_id: str, path: str, lines: list[dict]):
        self.workspace_breakpoints.setdefault(workspace_id, {})[str(Path(path).resolve())] = [
            {"line": int(item["line"]), "condition": str(item.get("condition", ""))} for item in lines[:200]]
