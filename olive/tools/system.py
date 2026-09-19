from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import shutil
import subprocess

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition


@dataclass(frozen=True, slots=True)
class ApplicationTarget:
    path: Path
    arguments: tuple[str, ...] = ()


class WindowsApplicationResolver:
    _start_apps_cache: list[dict[str, str]] | None = None
    def __init__(self, *, local_app_data: Path | None = None, roaming_app_data: Path | None = None,
                 program_data: Path | None = None):
        self.local_app_data = local_app_data or Path(os.getenv("LOCALAPPDATA", ""))
        self.roaming_app_data = roaming_app_data or Path(os.getenv("APPDATA", ""))
        self.program_data = program_data or Path(os.getenv("ProgramData", "C:/ProgramData"))

    def resolve(self, application: str) -> ApplicationTarget | None:
        name = application.strip().strip('"')
        direct = Path(name).expanduser()
        if direct.is_file(): return ApplicationTarget(direct.resolve())
        executable = shutil.which(name) or (shutil.which(f"{name}.exe") if not name.lower().endswith(".exe") else None)
        if executable: return ApplicationTarget(Path(executable).resolve())
        normalized = name.removesuffix(".exe").casefold()
        registered = self._registered_app_paths()
        if normalized in registered: return ApplicationTarget(registered[normalized])
        for root in (self.roaming_app_data / "Microsoft/Windows/Start Menu/Programs",
                     self.program_data / "Microsoft/Windows/Start Menu/Programs"):
            if root.is_dir():
                matches = sorted((path for path in root.rglob("*.lnk") if path.stem.casefold() == normalized),
                                 key=lambda path: len(str(path)))
                if matches: return ApplicationTarget(matches[0].resolve())
        # Squirrel-based per-user applications such as Discord are launched via Update.exe.
        app_root = self.local_app_data / name.removesuffix(".exe")
        updater = app_root / "Update.exe"
        if updater.is_file(): return ApplicationTarget(updater.resolve(), ("--processStart", f"{name.removesuffix('.exe')}.exe"))
        versioned = sorted(app_root.glob(f"app-*\\{name.removesuffix('.exe')}.exe"), reverse=True)
        if versioned: return ApplicationTarget(versioned[0].resolve())
        start_app = self._match_start_app(name)
        if start_app:
            explorer = Path(os.getenv("WINDIR", "C:/Windows")) / "explorer.exe"
            return ApplicationTarget(explorer, (f"shell:AppsFolder\\{start_app['AppID']}",))
        return None

    @staticmethod
    def _registered_app_paths() -> dict[str, Path]:
        try:
            import winreg
        except ImportError:
            return {}
        results = {}
        locations = (
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
        )
        for hive, location in locations:
            try:
                with winreg.OpenKey(hive, location) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        key_name = winreg.EnumKey(root, index)
                        try:
                            with winreg.OpenKey(root, key_name) as entry:
                                raw = str(winreg.QueryValue(entry, None)).strip()
                            path_text = raw.split('"')[1] if raw.startswith('"') and '"' in raw[1:] else raw
                            path = Path(os.path.expandvars(path_text))
                            if path.is_file(): results[key_name.removesuffix(".exe").casefold()] = path.resolve()
                        except (OSError, IndexError):
                            continue
            except OSError:
                continue
        return results

    @classmethod
    def _start_apps(cls) -> list[dict[str, str]]:
        if cls._start_apps_cache is not None: return cls._start_apps_cache
        command = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
        try:
            result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=20,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            value = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else []
            if isinstance(value, dict): value = [value]
            cls._start_apps_cache = [item for item in value if isinstance(item, dict) and item.get("Name") and item.get("AppID")]
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            cls._start_apps_cache = []
        return cls._start_apps_cache

    def _match_start_app(self, requested: str) -> dict[str, str] | None:
        wanted = _normalize_app_name(requested)
        candidates = []
        for app in self._start_apps():
            candidate = _normalize_app_name(app["Name"])
            if candidate == wanted: score = 1.0
            elif candidate.startswith(wanted + " ") or wanted.startswith(candidate + " "): score = .92
            elif wanted in candidate: score = .86
            else: score = SequenceMatcher(None, wanted, candidate).ratio()
            if score >= .72: candidates.append((score, len(candidate), candidate, app))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        if not candidates: return None
        if len(candidates) > 1 and candidates[0][0] < 1.0 and candidates[0][0] - candidates[1][0] < .08:
            return None
        return candidates[0][3]

    @staticmethod
    def launch(target: ApplicationTarget) -> None:
        if target.path.suffix.casefold() == ".lnk" and not target.arguments:
            os.startfile(str(target.path))
        else:
            subprocess.Popen([str(target.path), *target.arguments], shell=False,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class SystemTool:
    def __init__(self, action):
        self.action = action
        self.definition = ToolDefinition(f"system.{action}", action.replace("_"," ").title(), "system",
            {"type":"object", "required": (["path"] if action == "open_path" else ["application"] if action in {"open_application","close_application","terminate_application"} else [])},
            risk_level="critical" if action == "terminate_application" else "high" if action == "close_application" else "medium",
            required_permissions=((f"system.{action}",) if action in {"close_application","terminate_application"} else
                                  ("system.open_application",) if action != "list_running_applications" else ()),
            confirmation_required=action != "list_running_applications")
    async def execute(self, arguments, context): return await asyncio.to_thread(self._execute, arguments)
    def _execute(self, arguments):
        if self.action == "open_path":
            path = Path(arguments["path"]).expanduser().resolve(strict=False)
            if not path.exists(): raise FileNotFoundError(path)
            from ..platform_support import open_path
            open_path(path)
            return ToolResult(True, f"Requested opening {path}")
        from ..platform_support import require_windows
        require_windows('Native application control')
        if self.action == "open_application":
            application = str(arguments["application"]).strip()
            if not application or any(char in application for char in "&|><\n\r"): raise ValueError("Invalid application name")
            resolver = WindowsApplicationResolver()
            target = resolver.resolve(application)
            if not target: return ToolResult.failure(f"Could not find an installed application named {application}", "ApplicationNotFound")
            resolver.launch(target)
            return ToolResult(True, f"Opened {application}", {"resolved_target": str(target.path)})
        if self.action in {"close_application", "terminate_application"}:
            application = str(arguments["application"]).strip()
            if not application or any(char in application for char in "&|><\n\r"): raise ValueError("Invalid application name")
            matches = _find_matching_processes(application)
            if not matches: return ToolResult.failure(f"No running application matched {application}", "ApplicationNotRunning")
            protected = {"system", "registry", "smss", "csrss", "wininit", "services", "lsass", "winlogon",
                         "dwm", "explorer", "python", "pythonw", "flet"}
            unsafe = [process for process in matches if _normalize_app_name(process["name"]) in protected]
            if unsafe: return ToolResult.failure("OLIVE will not close protected Windows or OLIVE processes", "ProtectedProcess")
            terminated = self.action == "terminate_application"
            command = ["taskkill.exe"]
            for process in matches:
                command.extend(["/PID", str(process["pid"])])
            if terminated: command.extend(["/T", "/F"])
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=15, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            closed = matches if result.returncode == 0 else []
            failures = [] if result.returncode == 0 else matches
            if not closed:
                operation = "terminate" if terminated else "close"
                return ToolResult.failure(f"Windows could not {operation} {application}", "TerminateFailed" if terminated else "CloseFailed", failures=failures)
            verb = "Terminated" if terminated else "Closed"
            return ToolResult(True, f"{verb} {application}", {"closed_processes":closed,"failed_processes":failures,
                                                               "forced":terminated})
        result = subprocess.run(["tasklist.exe","/fo","csv","/nh"],capture_output=True,text=True,timeout=15,
                                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        names = sorted({line.split('","')[0].strip('"') for line in result.stdout.splitlines() if line.startswith('"')})
        return ToolResult(result.returncode==0, f"Found {len(names)} running applications", {"applications":names})


def system_tools(): return [SystemTool("open_application"), SystemTool("close_application"), SystemTool("terminate_application"),
                            SystemTool("open_path"), SystemTool("list_running_applications")]


def _normalize_app_name(value: str) -> str:
    cleaned = value.casefold().replace("®", "").replace("™", "")
    for suffix in (".exe", " application", " app"):
        if cleaned.endswith(suffix): cleaned = cleaned[:-len(suffix)]
    return " ".join("".join(character if character.isalnum() else " " for character in cleaned).split())


def _running_processes(include_window_titles: bool = False) -> list[dict]:
    command = ["tasklist.exe"]
    if include_window_titles:
        command.append("/v")
    command.extend(["/fo", "csv", "/nh"])
    result = subprocess.run(command, capture_output=True, text=True, timeout=15,
                            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if result.returncode != 0: raise RuntimeError("Windows could not list running applications")
    processes = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) < 2: continue
        try: processes.append({"name":row[0], "pid":int(row[1]), "window_title":row[-1] if len(row) > 2 else ""})
        except ValueError: continue
    return processes


def _find_matching_processes(requested: str) -> list[dict]:
    """Use the quick executable-name scan, adding expensive titles only as a fallback."""
    matches = _matching_processes(requested, _running_processes())
    if matches:
        return matches
    return _matching_processes(requested, _running_processes(include_window_titles=True))


def _matching_processes(requested: str, processes: list[dict]) -> list[dict]:
    wanted = _normalize_app_name(requested)
    scored = []
    for process in processes:
        candidate = _normalize_app_name(process["name"])
        title = _normalize_app_name(process.get("window_title", ""))
        score = 1.0 if candidate == wanted else .94 if title == wanted else \
                .92 if candidate.startswith(wanted) or wanted.startswith(candidate) else \
                .84 if wanted and wanted in title else 0
        if score: scored.append((score,candidate,process))
    if not scored: return []
    best = max(item[0] for item in scored)
    names = {candidate for score,candidate,_ in scored if score == best}
    if len(names) != 1: return []
    return [process for score,candidate,process in scored if score == best]
