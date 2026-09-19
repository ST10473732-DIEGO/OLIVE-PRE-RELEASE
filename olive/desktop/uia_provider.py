"""Bounded UI Automation calls isolated from Qt, asyncio and other COM apartments."""

import asyncio
import json
import os
import subprocess
import sys
from .errors import ObservationUnavailable


class WindowsUIAutomationProvider:
    name = "windows_uia"

    def __init__(self, timeout=12, stop=None):
        self.timeout = timeout
        self.workers = set()
        from .emergency_stop import EmergencyStop
        self.stop = stop or EmergencyStop()

    async def call(self, action, window, **arguments):
        if os.name != "nt":
            raise RuntimeError("Windows UI Automation is unavailable")
        if self.stop.is_set():
            raise InterruptedError("Desktop control stopped")
        request = json.dumps({"action": action, "window": window, **arguments, "stop_name": self.stop.name}).encode("utf-8")
        if len(request) > 65536:
            raise ValueError("UI Automation request exceeds size limit")
        # Avoid the Windows venv redirector: foreground permission must name the
        # actual helper PID. Preserve this environment's import paths explicitly.
        executable = getattr(sys, "_base_executable", sys.executable)
        environment = {key: value for key, value in os.environ.items() if key.upper() in
                       {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "USERPROFILE"}}
        environment["PYTHONPATH"] = os.pathsep.join(os.path.abspath(path or os.getcwd()) for path in sys.path)
        bootstrap = "import site,sys,runpy; site.addsitedir(sys.argv[1]); runpy.run_module('olive.desktop.uia_worker',run_name='__main__')"
        process = await asyncio.create_subprocess_exec(executable, "-c", bootstrap,
            os.path.join(sys.prefix, "Lib", "site-packages"),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=environment)
        self.workers.add(process)
        try:
            if action == "activate":
                import ctypes
                # Windows remains authoritative: this grant can fail if the user
                # is working elsewhere. The helper subsequently verifies focus.
                ctypes.windll.user32.AllowSetForegroundWindow(process.pid)
            output, _ = await asyncio.wait_for(process.communicate(request), self.timeout)
            if len(output) > 6 * 1024 * 1024:
                raise ValueError("UI Automation observation exceeded size limit")
            if process.returncode or not output:
                raise RuntimeError("Windows accessibility helper could not start (exit " + str(process.returncode) + ")")
            try:
                result = json.loads(output)
            except (ValueError, UnicodeError) as error:
                raise RuntimeError("Windows accessibility helper returned an invalid observation") from error
            if not result.get("ok"):
                self.last_error = {"operation": action, "type": result.get("error"), "code": result.get("code")}
                if action == "observe" and result.get("error") in {"COMError", "ElementNotFoundError", "ElementNotAvailable"}:
                    raise ObservationUnavailable("The application's accessibility snapshot changed while it was being read")
                error_type = {"PermissionError": PermissionError, "InterruptedError": InterruptedError,
                              "TimeoutError": TimeoutError, "ValueError": ValueError, "LookupError": LookupError}.get(result.get("error"), RuntimeError)
                raise error_type(result.get("message", "Windows accessibility operation failed"))
            return result["value"]
        finally:
            if process.returncode is None:
                process.kill()  # Only the OLIVE-owned helper, never the target application.
                await process.wait()
            self.workers.discard(process)

    async def observe(self, window):
        return await self.call("observe", window)

    async def close(self):
        for process in list(self.workers):
            if process.returncode is None:
                process.kill()
                await process.wait()
        self.workers.clear()
