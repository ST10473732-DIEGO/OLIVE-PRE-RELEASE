from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import asyncio,shutil,subprocess,time,sys

TRUST_LEVELS={"trusted","approved","untrusted"}

@dataclass(frozen=True,slots=True)
class SandboxLimits:
    cpus:float=1.0
    memory_mb:int=512
    process_limit:int=128
    network_enabled:bool=False
    read_only_workspace:bool=False

class NativeExecutionProvider:
    name="native"
    def available(self):return True
    async def start(self,command,cwd,environment,limits,interactive=False,owned_children=False):
        if sys.platform == "linux":
            from ..studio_tooling.posix_process import start_owned_process
            return await start_owned_process(command, cwd=str(cwd), env=environment,
                stdin=asyncio.subprocess.PIPE if interactive else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        if sys.platform == "win32" and owned_children:
            from ..studio_tooling.windows_process import start_owned_process
            return await start_owned_process(command, cwd=str(cwd), env=environment,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return await asyncio.create_subprocess_exec(*command,cwd=str(cwd),env=environment,stdin=asyncio.subprocess.PIPE if interactive else asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)|getattr(subprocess,"CREATE_NO_WINDOW",0))

class DockerExecutionProvider:
    name="docker"
    def __init__(self,executable=None,image="python:3.12-slim"):self.executable=executable or shutil.which("docker");self.image=image;self._availability=None;self._checked_at=0.0
    def available(self):
        if time.monotonic()-self._checked_at<5 and self._availability is not None:return self._availability
        if not self.executable:return False
        try:self._availability=subprocess.run([self.executable,"info"],capture_output=True,timeout=5,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)).returncode==0
        except (OSError,subprocess.SubprocessError):self._availability=False
        self._checked_at=time.monotonic();return self._availability
    def build_command(self,command,cwd,environment,limits:SandboxLimits):
        root=str(Path(cwd).resolve(strict=True));mount=f"{root}:/workspace"+(":ro" if limits.read_only_workspace else "")
        args=[self.executable or "docker","run","--rm","--init","--user","65534:65534","--cpus",str(limits.cpus),"--memory",f"{limits.memory_mb}m","--pids-limit",str(limits.process_limit),"--mount",f"type=bind,source={mount.split(':/workspace')[0]},target=/workspace"+(",readonly" if limits.read_only_workspace else ""),"--workdir","/workspace","--tmpfs","/tmp:rw,noexec,nosuid,size=64m"]
        if not limits.network_enabled:args+=["--network","none"]
        for key,value in environment.items():
            if key in {"PYTHONIOENCODING","DOTNET_CLI_TELEMETRY_OPTOUT"}:args+=["--env",f"{key}={value}"]
        return args+[self.image,*command]
    async def start(self,command,cwd,environment,limits):
        if not self.available():raise RuntimeError("Docker Desktop is unavailable")
        return await asyncio.create_subprocess_exec(*self.build_command(command,cwd,environment,limits),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))

class ExecutionProviderRegistry:
    def __init__(self,native=None,docker=None):self.native=native or NativeExecutionProvider();self.docker=docker or DockerExecutionProvider()
    def select(self,trust_level):
        if trust_level not in TRUST_LEVELS:raise ValueError("Invalid execution trust level")
        if trust_level=="untrusted":
            if not self.docker.available():raise PermissionError("Untrusted execution requires Docker isolation")
            return self.docker
        return self.native
