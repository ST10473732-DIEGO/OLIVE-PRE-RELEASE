"""Catalog-bound launch, with process/window evidence rather than launch assumptions."""

import asyncio
import os
from pathlib import Path
import subprocess
import time
import uuid

from .application_sessions import ApplicationSession
from ..agent.tool_schema import ToolContext, ToolDefinition
from ..agent.tool_result import ToolResult


def launch_identity(application):
    from ..platform_support import require_windows
    require_windows('Desktop Control')
    mechanism, target = application.launch_mechanism, application.launch_target
    if mechanism == "app_id":
        if not target or any(character in target for character in "\r\n\x00"):
            raise ValueError("Invalid installed application identity")
        subprocess.Popen([str(Path(os.environ["WINDIR"]) / "explorer.exe"), "shell:AppsFolder\\" + target], shell=False)
    elif mechanism in {"executable", "shortcut"}:
        path = Path(target).resolve(strict=True)
        if path.suffix.casefold() != (".exe" if mechanism == "executable" else ".lnk"):
            raise ValueError("Unsupported installed launch target")
        if mechanism == "shortcut":
            os.startfile(str(path))
        else:
            subprocess.Popen([str(path)], shell=False)
    else:
        raise ValueError("This application has no supported launch mechanism")


def matches(application, window):
    if application.executable:
        return os.path.normcase(window.get("executable", "")) == os.path.normcase(application.executable)
    return bool(application.package_identity and window.get("package_identity") == application.package_identity)


class ApplicationLaunchTool:
    def __init__(self, discovery, stop):
        self.discovery, self.stop = discovery, stop
        self.definition = ToolDefinition("desktop.launch", "Launch a selected installed application", "desktop", {})

    async def execute(self, arguments, context):
        if context.progress_callback is not self or self.stop.is_set():
            raise PermissionError("Application launch authorization required")
        app = next((item for item in self.discovery.applications if item.id == arguments["application_id"]), None)
        if app is None:
            raise ValueError("Refresh installed applications before launching")
        await asyncio.to_thread(launch_identity, app)
        return ToolResult(True, "Launch requested; window verification pending")


class ApplicationLauncher:
    def __init__(self, desktop):
        self.desktop = desktop
        desktop.s.tool_registry.register(ApplicationLaunchTool(desktop.discovery, desktop.stop_event))

    async def open(self, application_id):
        desktop = self.desktop
        desktop.gateway.check()
        app = next((item for item in desktop.discovery.applications if item.id == application_id), None)
        if app is None:
            raise ValueError("Select an application from the discovered catalog")
        if app.launch_mechanism == 'executable':
            from .owned_launch import canonical
            launched = await desktop.launch_targets.launch(app,(app.launch_target,),(canonical(app.launch_target),))
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                desktop.gateway.check()
                try:
                    state = await desktop.launch_targets.attach(launched['launch_id'])
                    return {**launched,'verified':True,'state':'observed','desktop':state}
                except LookupError:
                    await asyncio.sleep(.15)
            return {**launched,'verified':False,'state':'review_required',
                    'message':'Owned window not resolved; use Attach launched target to retry inspection. Launch will not be replayed.'}
        session = ApplicationSession(app, str(uuid.uuid4()))
        await desktop.gateway.approval(session, "system.open_application", "Open the selected installed application",
                                      {"application": app.display_name, "launch_target": app.launch_target}, always=True)
        import win32gui
        import win32process
        handle = win32gui.GetForegroundWindow()
        approved_foreground = {"hwnd": handle, "pid": win32process.GetWindowThreadProcessId(handle)[1]} if handle else None
        await desktop.list_windows()
        found = [key for key, window in desktop.windows.items() if matches(app, window)]
        if not found:
            tool = desktop.s.tool_registry.require("desktop.launch")
            await tool.execute({"application_id": app.id}, ToolContext(session.task_id, progress_callback=tool))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            desktop.gateway.check()
            await desktop.list_windows()
            found = [key for key, window in desktop.windows.items() if matches(app, window)]
            if not found and not app.executable and any(window["application"].casefold() == app.display_name.casefold()
                                                        for window in desktop.windows.values()):
                # A Win32 Start Menu ID may not be a process package ID. Refresh
                # shortcut-backed executable evidence after a cold launch; never
                # accept a matching window title/name alone as verification.
                refreshed = await desktop.discovery.refresh()
                app = next((item for item in refreshed if item.id == app.id), app)
                found = [key for key, window in desktop.windows.items() if matches(app, window)]
            if len(found) > 1:
                return {"verified": False, "state": "clarification", "application": app.display_name,
                        "windows": found, "message": "Select the intended application window"}
            if found:
                window = desktop.windows[found[0]]
                if window.get("window_class") == "Windows.UI.Core.CoreWindow" and not window["foreground"]:
                    # UWP launch exposes content briefly before Windows attaches
                    # its real foreground frame. Wait for identity normalization.
                    await asyncio.sleep(.1)
                    continue
                if not window["foreground"]:
                    if not approved_foreground:
                        raise PermissionError("Activate the requested application manually before continuing")
                    await desktop.provider.call("activate", window, expected_foreground=approved_foreground)
                result = await desktop.inspect(found[0])
                return {"verified": True, "state": "observed", "application": app.display_name, "desktop": result}
            await asyncio.sleep(.15)
        return {"verified": False, "state": "review_required", "application": app.display_name,
                "message": "Launch requested; its window identity was not verified. Select the window manually."}
