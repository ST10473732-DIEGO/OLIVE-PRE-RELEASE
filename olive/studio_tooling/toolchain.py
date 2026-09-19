"""Locate installed developer toolchains without installing anything."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY / ".toolchains" / "studio"
PINNED = {
    "omnisharp": {"version": "1.39.15", "executable": TOOLS / "omnisharp" / "OmniSharp.exe", "licence": "MIT"},
    "netcoredbg": {"version": "3.2.0-1092", "executable": TOOLS / "netcoredbg" / "netcoredbg" / "netcoredbg.exe", "licence": "MIT"},
}


def dotnet_executable() -> str | None:
    return shutil.which("dotnet")


def python_executable(root: str | Path | None = None) -> str:
    from ..services.build_test_service import BuildAndTestService
    return BuildAndTestService.python_executable(Path(root) if root else REPOSITORY)


_MODULE_CACHE: dict[tuple[str, str], bool] = {}


def module_available(python: str, module: str) -> bool:
    # Cached: the interpreter's installed modules do not change within a
    # session, and repeated blocking probes would stall the event loop while
    # language servers and debuggers are starting.
    cache_key = (str(python), module)
    if cache_key in _MODULE_CACHE:
        return _MODULE_CACHE[cache_key]
    try:
        # find_spec avoids executing the (heavy) package on import; a fresh
        # interpreter under load imports parso/jedi slowly, so keep this light.
        completed = subprocess.run(
            [python, "-c", f"import importlib.util,sys; sys.exit(0 if importlib.util.find_spec({module!r}) else 3)"],
            capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        _MODULE_CACHE[cache_key] = completed.returncode == 0
        return _MODULE_CACHE[cache_key]
    except (OSError, subprocess.SubprocessError):
        return False


async def dotnet_info() -> dict:
    """SDK and runtime inventory from the installed CLI; empty when absent."""
    executable = dotnet_executable()
    if not executable:
        return {"available": False, "sdks": [], "runtimes": []}
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")

    async def run(*arguments):
        process = await asyncio.create_subprocess_exec(
            executable, *arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            out, _ = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            return ""
        return out.decode("utf-8", "replace")

    sdks = [line.split(" [")[0].strip() for line in (await run("--list-sdks")).splitlines() if line.strip()]
    runtimes = [line.split(" [")[0].strip() for line in (await run("--list-runtimes")).splitlines() if line.strip()]
    version = (await run("--version")).strip()
    return {"available": True, "executable": executable, "version": version, "sdks": sdks, "runtimes": runtimes}


def inventory(root: str | Path | None = None) -> dict:
    """What Studio can honestly offer on this machine; never claims a stub as available."""
    python = python_executable(root)
    tools = {}
    for name, item in PINNED.items():
        executable = item["executable"]
        tools[name] = {"version": item["version"], "licence": item["licence"], "path": str(executable),
                       "available": executable.is_file()}
    return {
        "dotnet": {"available": dotnet_executable() is not None, "executable": dotnet_executable()},
        "python": {"executable": python, "version": sys.version.split()[0]},
        "csharp_language_server": tools["omnisharp"],
        "dotnet_debugger": tools["netcoredbg"],
        "python_debugger": {"available": module_available(python, "debugpy"), "provider": "debugpy"},
        "python_language_server": {"available": module_available(python, "pylsp"), "provider": "python-lsp-server"},
        "terminal": {"available": module_available(sys.executable, "winpty"), "provider": "pywinpty (ConPTY)"},
    }


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
