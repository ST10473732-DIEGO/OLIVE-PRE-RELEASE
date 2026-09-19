"""Per-workspace run configurations: startup project, configuration, arguments,
working directory, safe environment overrides, interpreter and launch profile.
Secrets never belong here; secret-looking names are rejected."""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import re

from ..storage.json_store import JsonStore

SECRET_NAME = re.compile(r"(?i)(key|token|secret|password|credential|cookie|auth)")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
DEFAULT = {"startup_project": "", "configuration": "Debug", "arguments": [], "working_directory": "", "environment": {},
           "interpreter": "", "launch_profile": "", "program": "", "stop_at_entry": False}


def sanitize(value: dict, root: Path) -> dict:
    result = deepcopy(DEFAULT)
    if not isinstance(value, dict):
        return result
    startup = str(value.get("startup_project", ""))[:1000]
    if startup:
        resolved = Path(startup)
        if not resolved.is_absolute():
            resolved = root / startup
        if not resolved.resolve().is_relative_to(root):
            raise ValueError("The startup project must be inside the workspace")
        result["startup_project"] = str(resolved.resolve())
    configuration = str(value.get("configuration", "Debug"))
    if configuration not in {"Debug", "Release"}:
        raise ValueError("Configuration must be Debug or Release")
    result["configuration"] = configuration
    arguments = value.get("arguments", [])
    if not isinstance(arguments, list) or len(arguments) > 64 or any(not isinstance(a, str) or len(a) > 2000 or "\0" in a for a in arguments):
        raise ValueError("Arguments must be up to 64 short strings")
    result["arguments"] = list(arguments)
    working = str(value.get("working_directory", ""))[:1000]
    if working:
        resolved = (root / working) if not Path(working).is_absolute() else Path(working)
        if not resolved.resolve().is_relative_to(root):
            raise ValueError("The working directory must be inside the workspace")
        result["working_directory"] = str(resolved.resolve())
    environment = value.get("environment", {})
    if not isinstance(environment, dict) or len(environment) > 32:
        raise ValueError("Too many environment overrides")
    for key, item in environment.items():
        if not NAME.fullmatch(str(key)) or SECRET_NAME.search(str(key)):
            raise ValueError(f"Environment override {key!r} is not allowed here; use the credential vault for secrets")
        if not isinstance(item, str) or len(item) > 2000 or "\0" in item:
            raise ValueError("Environment values must be short strings")
        result["environment"][str(key)] = item
    interpreter = str(value.get("interpreter", ""))[:1000]
    result["interpreter"] = interpreter
    result["launch_profile"] = str(value.get("launch_profile", ""))[:100]
    program = str(value.get("program", ""))[:1000]
    if program:
        resolved = (root / program) if not Path(program).is_absolute() else Path(program)
        if not resolved.resolve().is_relative_to(root):
            raise ValueError("The program must be inside the workspace")
        result["program"] = str(resolved.resolve())
    result["stop_at_entry"] = bool(value.get("stop_at_entry", False))
    return result


class RunConfigurations:
    def __init__(self, path: Path):
        self.store = JsonStore(path)

    def _all(self) -> dict:
        value = self.store.read({"schema_version": 1, "workspaces": {}})
        if not isinstance(value, dict) or not isinstance(value.get("workspaces"), dict):
            return {"schema_version": 1, "workspaces": {}}
        return value

    def get(self, workspace_id: str, root: Path) -> dict:
        stored = self._all()["workspaces"].get(workspace_id, {})
        try:
            return sanitize(stored, root)
        except ValueError:
            return deepcopy(DEFAULT)

    def save(self, workspace_id: str, root: Path, value: dict) -> dict:
        clean = sanitize(value, root)
        data = self._all()
        data["workspaces"][workspace_id] = clean
        self.store.write(data)
        return clean
