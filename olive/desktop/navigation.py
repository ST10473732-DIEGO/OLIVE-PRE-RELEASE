"""Deterministic Windows navigation accelerators, with observed postconditions."""

import asyncio
import os
from pathlib import Path
import time
import uuid

from .application_discovery import identity
from .application_sessions import ApplicationSession
from ..agent.tool_schema import ToolDefinition, ToolContext
from ..agent.tool_result import ToolResult


SETTINGS_PAGES = {"bluetooth": "ms-settings:bluetooth", "display": "ms-settings:display",
                  "network": "ms-settings:network", "apps": "ms-settings:appsfeatures"}


class WindowsNavigationTool:
    def __init__(self, stop, kind):
        self.stop, self.kind = stop, kind
        self.definition = ToolDefinition("desktop.navigate_" + kind, "Open an approved Windows location", "desktop", {})

    async def execute(self, arguments, context):
        if context.progress_callback is not self or self.stop.is_set():
            raise PermissionError("Navigation gateway authorization required")
        target = str(Path(arguments["path"]).resolve(strict=True)) if self.kind == "folder" else SETTINGS_PAGES[arguments["page"]]
        if self.kind == "folder" and not Path(target).is_dir():
            raise ValueError("Navigation target must be a directory")
        await asyncio.to_thread(os.startfile, target)
        return ToolResult(True, "Navigation requested; verification pending")


class WindowsNavigation:
    def __init__(self, desktop):
        self.desktop = desktop
        for kind in ("folder", "settings"):
            desktop.s.tool_registry.register(WindowsNavigationTool(desktop.stop_event, kind))

    async def application_identity(self, kind):
        """Use the same scope identity as discovery and normal application control."""
        if kind == "folder":
            return identity("File Explorer", "executable", str(Path(os.environ["WINDIR"]) / "explorer.exe"))
        if not self.desktop.discovery.applications:
            await self.desktop.discovery.refresh()
        matches = [app for app in self.desktop.discovery.applications
                   if app.package_identity.casefold().startswith("windows.immersivecontrolpanel_")]
        if len(matches) != 1:
            raise LookupError("Refresh applications and select an unambiguous Windows Settings identity")
        return matches[0]

    async def open_folder(self, path):
        target = Path(path).expanduser().resolve(strict=True)
        if not target.is_dir():
            raise ValueError("Select a directory")
        session = ApplicationSession(await self.application_identity("folder"), str(uuid.uuid4()))
        await self.desktop.gateway.approval(session, "filesystem.read", "Show this folder in File Explorer", {"path": str(target)})
        await self.desktop.gateway.approval(session, "app.file_explorer.navigate", "Open File Explorer at the selected folder",
                                            {"path": str(target)}, always=True)
        self.desktop.gateway.require_not_denied(session, "filesystem.read", str(target))
        tool = self.desktop.s.tool_registry.require("desktop.navigate_folder")
        await tool.execute({"path": str(target)}, ToolContext(session.task_id, progress_callback=tool))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.desktop.gateway.check()
            result = await self.desktop.provider.call("verify_folder", {}, path=str(target))
            if result["verified"]:
                return result
            await asyncio.sleep(.15)
        raise TimeoutError("Explorer opened, but its actual location could not be verified")

    async def open_settings(self, page="bluetooth"):
        if page not in SETTINGS_PAGES:
            raise ValueError("Unsupported safe Settings page")
        session = ApplicationSession(await self.application_identity("settings"), str(uuid.uuid4()))
        await self.desktop.gateway.approval(session, "app.windows_settings.navigate", "Navigate Windows Settings without changing configuration",
                                            {"page": page}, always=True)
        tool = self.desktop.s.tool_registry.require("desktop.navigate_settings")
        await tool.execute({"page": page}, ToolContext(session.task_id, progress_callback=tool))
        expected = {"bluetooth": ("Bluetooth & devices", "Bluetooth and devices"), "display": ("Display",),
                    "network": ("Network & internet",), "apps": ("Installed apps",)}[page]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            await self.desktop.list_windows()
            for window in self.desktop.windows.values():
                if window["application"] != "systemsettings":
                    continue
                session.window = window
                observation = await self.desktop.gateway.observe(session)
                headings = [control for control in observation["controls"] if control["name"] in expected
                            and control["control_type"] == "Text" and control["visible"]]
                if headings:
                    return {"verified": True, "page": page, "window": window}
            self.desktop.gateway.check()
            await asyncio.sleep(.15)
        raise TimeoutError("Settings navigation was requested, but its page heading was not verified")
