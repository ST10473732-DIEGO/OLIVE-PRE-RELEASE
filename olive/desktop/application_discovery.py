"""Installed application catalog; adapters are optional, never discovery prerequisites."""

import asyncio
import hashlib
from dataclasses import replace
from pathlib import Path

from .application_sessions import ApplicationIdentity


class AmbiguousApplication(ValueError):
    def __init__(self, candidates):
        super().__init__("Several applications match; select the intended application")
        self.candidates = candidates


def normalized(value):
    return " ".join(value.casefold().removesuffix(".exe").split())


def identity(name, mechanism, target):
    key = hashlib.sha256((mechanism + ":" + target.casefold()).encode()).hexdigest()[:24]
    return ApplicationIdentity(key, name,
        executable=target if mechanism == "executable" else "",
        package_identity=target if mechanism == "app_id" else "",
        launch_mechanism=mechanism, launch_target=target)


class ApplicationDiscoveryService:
    def __init__(self, catalog=None, aliases=None):
        self.catalog = catalog or self.windows_catalog
        self.aliases = aliases or (lambda: {})
        self.applications = []

    async def refresh(self):
        values = await asyncio.to_thread(self.catalog)
        unique = {}
        for item in values:
            unique.setdefault(item.id, item)
        self.applications = list(unique.values())
        return self.applications

    def resolve(self, requested):
        wanted = normalized(requested)
        if not wanted:
            raise ValueError("Application name is required")
        alias = self.aliases().get(wanted)
        if alias:
            matches = [item for item in self.applications if item.id == alias]
        else:
            matches = [item for item in self.applications
                       if wanted in {normalized(item.display_name), normalized(Path(item.executable).name)}]
            if not matches:
                matches = [item for item in self.applications if wanted in normalized(item.display_name)]
        if len(matches) > 1:
            raise AmbiguousApplication(matches)
        if not matches:
            raise LookupError("No installed application matched the request")
        return matches[0]

    @staticmethod
    def windows_catalog():
        from ..tools.system import WindowsApplicationResolver
        from .windows_observation import enumerate_windows, require_windows
        require_windows()
        resolver = WindowsApplicationResolver()
        registered = resolver._registered_app_paths()
        values = []
        for app in resolver._start_apps():
            executable = registered.get(normalized(app["AppID"])) or registered.get(normalized(app["Name"]))
            values.append(identity(app["Name"], "executable", str(executable)) if executable else
                          identity(app["Name"], "app_id", app["AppID"]))
        known_names = {normalized(item.display_name) for item in values}
        shortcuts = {}
        for name, path in registered.items():
            if normalized(name) not in known_names:
                values.append(identity(name, "executable", str(path)))
        for root in (resolver.roaming_app_data, resolver.program_data):
            folder = root / "Microsoft/Windows/Start Menu/Programs"
            if folder.is_dir():
                for shortcut in folder.rglob("*.lnk"):
                    shortcuts.setdefault(normalized(shortcut.stem), []).append(shortcut)
                    if normalized(shortcut.stem) not in known_names:
                        values.append(identity(shortcut.stem, "shortcut", str(shortcut)))
        windows = enumerate_windows()
        from .shortcut_identity import shortcut_matches
        for index, app in enumerate(values):
            links = shortcuts.get(normalized(app.display_name), [])
            if app.executable or not links:
                continue
            candidates = {window["executable"] for window in windows if window["executable"]
                          and normalized(window["application"]) == normalized(app.display_name)}
            verified = [path for path in candidates if all(shortcut_matches(link, path) for link in links)]
            if len(verified) == 1:
                values[index] = replace(app, executable=verified[0])
        known_executables = {item.executable.casefold() for item in values if item.executable}
        known_packages = {item.package_identity.casefold() for item in values if item.package_identity}
        for window in windows:
            package = window.get("package_identity", "")
            if package:
                if package.casefold() not in known_packages:
                    values.append(identity(window["application"], "app_id", package))
                    known_packages.add(package.casefold())
                continue
            executable = window["executable"]
            if executable and executable.casefold() not in known_executables:
                values.append(identity(Path(executable).stem, "executable", executable))
                known_executables.add(executable.casefold())
        return values
