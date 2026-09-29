from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
import sys
import re
import time
import uuid

from ..models import now_iso
from ..workspace import Workspace
from .execution_provider import ExecutionProviderRegistry,SandboxLimits

SECRET_NAME=re.compile(r"(?i)(key|token|secret|password|credential|cookie|auth)")
URL_PATTERN=re.compile(r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?(?:/\S*)?")
SAFE_ENV={"PATH","PATHEXT","SYSTEMROOT","WINDIR","TEMP","TMP","COMSPEC","PYTHONIOENCODING","DOTNET_CLI_TELEMETRY_OPTOUT"}
RUN_STATES={"created","starting","running","completed","failed","stopped","timed_out"}
WEB_KINDS={"aspnet_web","static_web"}


def free_loopback_port() -> int:
    """A currently free 127.0.0.1 port. A process that loses the race fails visibly; nothing is killed."""
    import socket
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1",0))
        return probe.getsockname()[1]


@dataclass(frozen=True,slots=True)
class ExecutionPolicy:
    trust_level:str="approved"
    max_runtime_seconds:float=120
    allow_network:bool=False
    allow_child_processes:bool=False
    inherit_environment:tuple[str,...]=tuple(sorted(SAFE_ENV))

    def __post_init__(self):
        if self.trust_level not in {"trusted","approved","ordinary","untrusted"}:raise ValueError("Invalid trust level")
        if self.max_runtime_seconds<=0:raise ValueError("Runtime must be positive")

    def environment(self,extra:dict[str,str]|None=None) -> dict[str,str]:
        allowed=set(self.inherit_environment)&SAFE_ENV
        result={key:value for key,value in os.environ.items() if key.upper() in allowed and not SECRET_NAME.search(key)}
        for key,value in (extra or {}).items():
            if key.upper() in SAFE_ENV and not SECRET_NAME.search(key):result[key]=str(value)
        return result


@dataclass(slots=True)
class RunArtifact:
    path:str
    kind:str="file"
    label:str=""


@dataclass(slots=True)
class RunSession:
    workspace_id:str
    command:list[str]
    application_type:str
    id:str=field(default_factory=lambda:str(uuid.uuid4()))
    process_id:int|None=None
    state:str="created"
    started_at:str|None=None
    ended_at:str|None=None
    stdout:str=""
    stderr:str=""
    exit_code:int|None=None
    local_url:str|None=None
    stop_requested:bool=False
    accepts_input:bool=False
    terminal_session_id:str|None=None
    artifacts:list[RunArtifact]=field(default_factory=list)

    def to_dict(self):return asdict(self)


class RunService:
    MAX_OUTPUT=1_000_000
    terminals = None

    def __init__(self,providers=None):self.sessions:dict[str,RunSession]={};self._processes={};self._tasks={};self.providers=providers or ExecutionProviderRegistry()

    @staticmethod
    def dotnet_environment(root, environment):
        """Supply SDK directory context without inheriting private user settings."""
        root = Path(root).resolve(strict=True)
        home = root/'obj'/'.olive-dotnet'
        if not home.resolve().is_relative_to(root):
            raise PermissionError('.NET working directories must remain inside the workspace')
        roaming, local = home/'AppData'/'Roaming', home/'AppData'/'Local'
        for directory in (home, roaming, local):
            if not directory.resolve().is_relative_to(root):
                raise PermissionError('.NET working directories must remain inside the workspace')
            directory.mkdir(parents=True, exist_ok=True)
        result = dict(environment)
        if sys.platform == "linux":
            # Compilers belong to this run rather than a detached shared daemon.
            result.update(UseSharedCompilation="false", MSBUILDDISABLENODEREUSE="1", DOTNET_CLI_USE_MSBUILD_SERVER="0")
        for key, value in os.environ.items():
            if key.upper() in {'PROGRAMFILES', 'PROGRAMFILES(X86)'}:
                result[key] = value
        result.update(DOTNET_CLI_HOME=str(home), APPDATA=str(roaming), LOCALAPPDATA=str(local),
                      DOTNET_CLI_TELEMETRY_OPTOUT='1',
                      DOTNET_NOLOGO='true',
                      DOTNET_GENERATE_ASPNET_CERTIFICATE='false',
                      DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='true')
        return result

    @staticmethod
    def detect_command(workspace:Workspace) -> tuple[list[str],str]:
        root=Path(workspace.root_path)
        if (root/'Main.java').is_file():
            return ['java', '--class-path', str(root) + os.pathsep + str(root/'lib'/'*'), str(root/'Main.java')], 'java_console'
        if (root/'main.js').is_file():
            return ['node', str(root/'main.js')], 'javascript_console'
        main=root/"main.py"
        if main.is_file():
            from .build_test_service import BuildAndTestService
            python = BuildAndTestService.python_executable(root)
            text=main.read_text(encoding="utf-8",errors="ignore")[:100_000]
            return [str(python),str(main)],("python_gui" if "tkinter" in text or "flet" in text else "python_console")
        solutions=sorted(root.glob("*.sln"));projects=sorted(root.glob("*.csproj"))
        if solutions or projects:
            target=(projects or solutions)[0];text=target.read_text(encoding="utf-8",errors="ignore") if target.suffix==".csproj" else ""
            if "Microsoft.NET.Sdk.Web" in text:
                # Command-line --urls overrides launch-profile URLs: loopback only, never 0.0.0.0.
                return ["dotnet","run","--project",str(target),"--","--urls",f"http://127.0.0.1:{free_loopback_port()}"],"aspnet_web"
            return ["dotnet","run","--project",str(target)],"dotnet_application"
        if (root/"index.html").is_file():
            server=Path(__file__).with_name("static_preview_server.py")
            if not server.is_file():raise ValueError("Static web preview is unavailable in this build")
            from .build_test_service import BuildAndTestService
            return [str(BuildAndTestService.python_executable(root)),"-u",str(server),str(root),str(free_loopback_port())],"static_web"
        raise ValueError("No supported runnable entry point was detected")

    async def start(self,workspace:Workspace,command:list[str],application_type:str="console",
                    policy:ExecutionPolicy|None=None,extra_environment:dict[str,str]|None=None,cwd:str|None=None,interactive:bool=False,
                    configured_environment:dict[str,str]|None=None,owned_children:bool=False) -> RunSession:
        if not command or not str(command[0]).strip():raise ValueError("Executable is required")
        # A working directory may only narrow the workspace, never leave it.
        directory=workspace.root_path
        if cwd:
            candidate=Path(cwd).resolve()
            if not candidate.is_relative_to(Path(workspace.root_path).resolve()) or not candidate.is_dir():raise ValueError("The working directory must be a folder inside the workspace")
            directory=str(candidate)
        policy=policy or ExecutionPolicy();session=RunSession(workspace.id,[str(item) for item in command],application_type,state="starting")
        provider=self.providers.select("approved" if policy.trust_level=="ordinary" else policy.trust_level)
        limits=SandboxLimits(network_enabled=policy.allow_network)
        environment = policy.environment(extra_environment)
        if provider.name == "native":
            from ..studio_tooling.toolchain import developer_environment
            environment = developer_environment(environment)
        if Path(session.command[0]).name.casefold() in {'dotnet', 'dotnet.exe'}:
            environment = self.dotnet_environment(workspace.root_path, environment)
        if configured_environment:
            # Explicit approved Run configuration, distinct from inherited process environment.
            from ..studio_tooling.run_config import sanitize
            environment.update(sanitize({'environment': configured_environment}, Path(workspace.root_path))['environment'])
        if interactive and provider.name != "native":
            raise PermissionError("Interactive program input is currently supported by the native execution provider only")
        if interactive:
            environment["PYTHONUNBUFFERED"] = "1"
        self.sessions[session.id] = session
        try:
            if interactive and self.terminals is not None:
                from ..studio_tooling.pty import ProgramProcess
                process = ProgramProcess(self.terminals, workspace.id, directory, session.command, environment)
                session.terminal_session_id = process.terminal.id
            else:
                process=await provider.start(session.command,directory,environment,limits,**({"interactive": True} if interactive else {}),
                    **({"owned_children": True} if owned_children and provider.name == "native" else {}))
        except Exception:
            session.state = 'failed'
            session.ended_at = now_iso()
            if owned_children:
                self.sessions.pop(session.id, None)
            raise
        session.accepts_input = interactive
        session.process_id=process.pid;session.state="running";session.started_at=now_iso();self._processes[session.id]=process
        self._tasks[session.id]=asyncio.create_task(self._collect(session,process,policy.max_runtime_seconds));return session

    async def _collect(self, session, process, timeout):
        async def drain(stream, field):
            import codecs
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while block := await stream.read(8192):
                value = getattr(session, field) + decoder.decode(block)
                setattr(session, field, value[-self.MAX_OUTPUT:])
                candidates = value
                if session.application_type == 'aspnet_web':
                    candidates = '\n'.join(line.split('Now listening on:', 1)[1] for line in value.splitlines() if 'Now listening on:' in line)
                match = URL_PATTERN.search(candidates)
                if match:
                    session.local_url = match.group(0)
            tail = decoder.decode(b"", final=True)
            setattr(session, field, (getattr(session, field) + tail)[-self.MAX_OUTPUT:])

        readers = [asyncio.create_task(drain(process.stdout, "stdout")),
                   asyncio.create_task(drain(process.stderr, "stderr"))]
        final_state = "failed"
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
            final_state = "completed" if process.returncode == 0 else "failed"
        except asyncio.TimeoutError:
            if process.returncode is None:
                process.kill()
            await process.wait()
            final_state = "timed_out"
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
            await process.wait()
            final_state = "stopped"
        finally:
            try:
                await asyncio.wait_for(asyncio.gather(*readers), timeout=2)
            except asyncio.TimeoutError:
                for reader in readers:
                    reader.cancel()
                await asyncio.gather(*readers, return_exceptions=True)
            session.exit_code = process.returncode
            session.accepts_input = False
            session.ended_at = now_iso()
            self._processes.pop(session.id, None)
            # Publish terminal state only with its exit code and drained output.
            # Remote/local status readers must never see completed + exit_code=None.
            session.state = final_state

    async def wait(self,session_id:str) -> RunSession:
        task=self._tasks.get(session_id)
        if task:
            try:await task
            except asyncio.CancelledError:pass
        return self.sessions[session_id]

    async def input(self, workspace_id, session_id, text, eof=False):
        session = self.sessions.get(session_id)
        process = self._processes.get(session_id)
        if not session or session.workspace_id != workspace_id:
            raise ValueError("The program session does not belong to the selected workspace")
        if not session.accepts_input or session.state != "running" or not process or not process.stdin or process.stdin.is_closing():
            raise ValueError("This program is no longer accepting input")
        if not isinstance(text, str) or len(text) > 4000 or "\0" in text:
            raise ValueError("Program input must be at most 4,000 characters without NUL bytes")
        process.stdin.write(text.encode("utf-8"))
        await asyncio.wait_for(process.stdin.drain(), 5)
        if eof:
            process.stdin.close()
            session.accepts_input = False
        return {"session_id": session_id, "written": len(text), "eof": eof}

    async def wait_cancellable(self, session_id, cancellation):
        if cancellation is None:
            return await self.wait(session_id)
        waiter = asyncio.create_task(self.wait(session_id))
        cancelled = asyncio.create_task(cancellation.wait())
        try:
            done, _ = await asyncio.wait({waiter, cancelled}, return_when=asyncio.FIRST_COMPLETED)
            if cancelled in done:
                return await self.stop(session_id)
            return await waiter
        finally:
            if not waiter.done():
                await self.stop(session_id)
            cancelled.cancel()
            await asyncio.gather(waiter, cancelled, return_exceptions=True)

    async def stop(self,session_id:str) -> RunSession:
        session=self.sessions[session_id];session.stop_requested=True;process=self._processes.get(session_id)
        if process and process.returncode is None:process.kill()
        task=self._tasks.get(session_id)
        if task and not task.done():task.cancel()
        if task:
            try:await task
            except asyncio.CancelledError:pass
        # Cancellation may precede the collector's first coroutine instruction;
        # in that case its finally block never runs. Always reap the owned process.
        if process:
            await process.wait()
            session.exit_code = process.returncode
            self._processes.pop(session_id, None)
        if session.state=="running":session.state="stopped";session.ended_at=now_iso()
        return session

    async def restart(self,session_id:str,workspace:Workspace,policy:ExecutionPolicy|None=None) -> RunSession:
        previous=self.sessions[session_id]
        if previous.state in {"starting","running"}:await self.stop(session_id)
        return await self.start(workspace,previous.command,previous.application_type,policy)

    def add_artifact(self,session_id:str,workspace:Workspace,path:str|Path,kind="file",label="") -> RunArtifact:
        resolved=workspace.resolve(path)
        if not resolved.exists():raise FileNotFoundError(resolved)
        artifact=RunArtifact(str(resolved),kind,label or resolved.name);self.sessions[session_id].artifacts.append(artifact);return artifact
