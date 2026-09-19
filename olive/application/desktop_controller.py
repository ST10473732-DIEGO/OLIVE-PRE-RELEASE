"""Shared desktop runtime; all live work runs on the existing application loop."""

import asyncio
from dataclasses import asdict

from ..desktop.application_discovery import ApplicationDiscoveryService, identity
from ..desktop.application_sessions import ApplicationSessions
from ..desktop.capabilities import capability_map
from ..desktop.gateway import DesktopGateway
from ..desktop.models import DesktopControlSession
from ..desktop.session_repository import DesktopSessionRepository
from ..desktop.settings import validate
from ..desktop.uia_provider import WindowsUIAutomationProvider
from ..desktop.windows_observation import enumerate_windows
from ..desktop.workflow import DesktopStep, DesktopWorkflow
from ..desktop.emergency_stop import EmergencyStop
from ..desktop.capture import ScreenshotStore


class DesktopController:
    def __init__(self, services):
        self.s = services
        self.stop_event = EmergencyStop()
        self.provider = WindowsUIAutomationProvider(stop=self.stop_event)
        self.discovery = ApplicationDiscoveryService(aliases=lambda: self.s.settings.get("application_aliases", {}))
        self.repository = DesktopSessionRepository(services.data_dir / "desktop_sessions.json")
        self.repository.recover()
        self.gateway = DesktopGateway(self.provider, services.tool_registry, services.permissions,
            services.confirmations, services.agent_audit, self.stop_event, self.configuration)
        self.record = None
        self.sessions = None
        self.workflow = None
        self.operation = None
        self.windows = {}
        self.observation = {}
        self.pending_plan = []
        self.screenshots = ScreenshotStore(services.data_dir / "desktop_captures")
        from .interactive_controller import InteractiveController
        self.browser = InteractiveController(self)
        from ..desktop.navigation import WindowsNavigation
        self.navigation = WindowsNavigation(self)
        from ..desktop.application_launch import ApplicationLauncher
        self.launcher = ApplicationLauncher(self)
        from ..desktop.launch_targets import LaunchTargets
        self.launch_targets = LaunchTargets(self)
        from ..desktop.media import MediaController
        self.media = MediaController(self)
        from ..desktop.consequence_service import DesktopConsequences
        self.consequences = DesktopConsequences(self)
        from ..desktop.universal_workflow import UniversalWorkflow
        self.universal = UniversalWorkflow(self)
        from ..desktop.visual_input import VisualInput
        self.visual = VisualInput(self)
        from ..desktop.clipboard import ClipboardController
        self.clipboard = ClipboardController(self)

    async def clipboard_action(self, action, text=""):
        return await self._track(self.clipboard.run, action, text)

    def busy(self):
        owner = self.universal.owner
        current = asyncio.current_task()
        return (self.operation is not None and self.operation is not current) or (owner is not None and owner is not current)

    async def _track(self, function, *arguments):
        if self.busy():
            raise ValueError("A desktop operation is already active")
        self.gateway.check()
        previous, self.operation = self.operation, asyncio.current_task()
        self.publish()
        try:
            return await function(*arguments)
        finally:
            self.operation = previous
            self.publish()

    async def consequence(self, permission, target, bindings, expected, method="invoke"):
        if self.busy():
            raise ValueError("A desktop operation is already active")
        self.operation = asyncio.current_task()
        self.gateway.last_verified_window = None
        try:
            if method == "invoke":
                return await self.consequences.run(permission, target, bindings, expected)
            if method != "editor_enter" or permission != "communication.send":
                raise ValueError("Unsupported consequence submission method")
            from ..desktop.message_submission import submit_editor_message
            return await submit_editor_message(self, target, bindings)
        except asyncio.CancelledError:
            if self.record:
                self.record.status = "cancelled"
            raise
        except Exception:
            if self.record:
                self.record.status = "PAUSED_REVIEW_REQUIRED"
            raise
        finally:
            self.operation = None
            self.publish()

    async def media_sessions(self):
        return await self._track(self.media.run)

    async def media_action(self, application_id, action):
        return await self._track(self.media.run, "act", application_id, action)

    async def discover_applications(self):
        if self.busy():
            raise ValueError("A desktop operation is already active")
        self.gateway.check()
        await self.review_discovery()
        return [asdict(item) for item in await self.discovery.refresh()]

    async def review_discovery(self):
        from ..desktop.application_sessions import ApplicationSession
        import uuid
        scope = ApplicationSession(identity('Running application discovery','discovery','visible-windows'),str(uuid.uuid4()))
        await self.gateway.approval(scope,'desktop.inspect_application',
            'Discover running applications and window titles',
            {'scope':'All visible windows: titles and process metadata; no UI trees',
             'consequence':'May reveal names of unrelated applications and documents'},always=True,explicit=True)

    async def open_application(self, application_id):
        return await self._track(self.launcher.open, application_id)

    async def launch_local(self, path, kind):
        return await self._track(self.launch_targets.launch_local, path, kind)

    async def attach_launch(self, launch_id):
        return await self._track(self.launch_targets.attach, launch_id)

    async def run_request(self, objective):
        import re
        self.gateway.check()
        match = re.fullmatch(r"(?:open|launch)\s+([^\r\n]{1,100})", objective.strip(), re.IGNORECASE)
        if match and not re.search(r"\b(and|then)\b", match[1], re.IGNORECASE):
            await self.review_discovery()
            await self.discovery.refresh()
            app = self.discovery.resolve(match[1])
            result = await self.open_application(app.id)
            if not result["verified"]:
                raise ValueError(result["message"])
            self.record.status = "completed"
            self.record.verification = "Requested application identity and window observed"
            self.publish()
            return self.status()
        return await self.universal.run(objective)

    def application_alias(self, alias, application_id):
        from ..desktop.application_discovery import normalized
        alias = normalized(alias)
        if not 1 <= len(alias) <= 80 or application_id not in {item.id for item in self.discovery.applications}:
            raise ValueError("Select a discovered application and a short alias")
        aliases = dict(self.s.settings.get("application_aliases", {}))
        if len(aliases) >= 100 and alias not in aliases:
            raise ValueError("Application alias limit reached")
        aliases[alias] = application_id
        self.s.settings["application_aliases"] = aliases
        self.s.settings_repo.save(self.s.settings)
        return {"alias": alias, "application_id": application_id}

    def configuration(self):
        return validate(self.s.settings.get("desktop_control"))

    def configure(self, settings):
        self.s.settings["desktop_control"] = validate(settings)
        if not self.s.settings["desktop_control"]["enabled"]:
            self.stop()
        policies = self.s.permissions.policies()
        for field, permission in (("keyboard_policy", "desktop.keyboard_input"), ("mouse_policy", "desktop.mouse_input")):
            if field in settings:
                policies["permissions"][permission] = settings[field]
        self.s.permissions.save(policies["permissions"], policies["scopes"])
        self.s.settings_repo.save(self.s.settings)
        self.publish()
        return self.status()

    def status(self):
        return {"settings": self.configuration(), "stopped": self.stop_event.is_set(),
                "session": self.record.to_dict() if self.record else None,
                "observation": self.observation, "capabilities": capability_map(self.observation),
                "provider": self.provider.name, "active": self.operation is not None or self.universal.owner is not None,
                "workflow_phases": list(self.universal.history)}

    def publish(self):
        if self.record:
            self.repository.save(self.record)
        self.s.publish("desktop", self.status())

    async def list_windows(self):
        if self.busy():
            raise ValueError("A desktop operation is already active")
        if not self.configuration()["enabled"]:
            raise PermissionError("Enable Desktop Control first")
        await self.review_discovery()
        windows = await asyncio.to_thread(enumerate_windows)
        self.windows = {str(window["hwnd"]): window for window in windows if window["executable"]}
        return [{"id": key, "title": value["title"], "application": value["application"]}
                for key, value in self.windows.items()]

    async def inspect(self, window_id):
        if self.busy():
            raise ValueError("A desktop action is running")
        window = self.windows[window_id]
        if self.stop_event.is_set():
            raise PermissionError("Desktop control is stopped; explicitly reset before continuing")
        app = identity(window["application"], "app_id", window["package_identity"]) if window.get("package_identity") else identity(window["application"], "executable", window["executable"])
        return await self.inspect_target(app,window)

    async def inspect_target(self, app, window):
        self.gateway.check()
        if not self.record:
            self.record = DesktopControlSession("User-directed application control")
            self.sessions = ApplicationSessions(self.record.id)
        session = self.sessions.attach(app, window)
        self.record.application = app.display_name
        self.record.status = "running"
        self.record.window = {key: window[key] for key in ("hwnd", "pid", "application")}
        try:
            self.observation = await self.gateway.observe(session)
            session.observe(self.observation)
            self.record.status = "paused"
        except asyncio.CancelledError:
            self.record.status = 'cancelled'
            raise
        except Exception:
            self.record.status = 'PAUSED_REVIEW_REQUIRED'
            self.record.verification = 'Target inspection did not complete; no control action performed'
            raise
        finally:
            self.publish()
        return self.status()

    async def perform(self, action, target, arguments, expected):
        if self.busy() or not self.sessions or not self.sessions.current:
            raise ValueError("Inspect an application before performing an action")
        session = self.sessions.sessions[self.sessions.current]
        step = DesktopStep(session.key, action, target, arguments, expected, "desktop.control_application")
        return await self._run_steps([step])

    async def plan(self, objective):
        if self.busy() or not self.sessions:
            raise ValueError("Inspect target applications before planning")
        from ..desktop.planner import DesktopPlanner
        self.gateway.check()
        self.operation = asyncio.current_task()
        self.pending_plan = []
        try:
            self.pending_plan = await DesktopPlanner(self.s.ollama, self.s.model_router).plan(objective, self.sessions)
            return [{"application": self.sessions.sessions[step.application_id].identity.display_name,
                     "action": step.action, "target": step.target, "expected": step.expected} for step in self.pending_plan]
        finally:
            self.operation = None

    async def execute_plan(self):
        if self.busy() or not self.pending_plan:
            raise ValueError("Create a desktop plan first")
        steps, self.pending_plan = self.pending_plan, []
        return await self._run_steps(steps)

    async def _run_steps(self, steps):
        self.gateway.last_verified_window = None
        self.operation = asyncio.current_task()
        self.workflow = DesktopWorkflow(self.sessions, self.gateway, stop_event=self.stop_event)
        self.record.status, self.record.current_action = "running", steps[0].action
        self.publish()
        try:
            result = await self.workflow.run(steps, {key: session.identity for key, session in self.sessions.sessions.items()})
            session = self.sessions.sessions[self.sessions.current]
            self.record.status = "completed"
            self.record.verification = "Expected state observed"
            self.record.history.extend(result["history"])
            self.record.history[:] = self.record.history[-100:]
            self.observation = session.observations[-1]
            self.record.application = session.identity.display_name
        except (PermissionError, TimeoutError, InterruptedError, ValueError, LookupError) as error:
            self.record.status = "PAUSED_REVIEW_REQUIRED"
            self.record.verification = str(error)
            raise
        except asyncio.CancelledError:
            self.record.status = "cancelled"
            raise
        except Exception:
            self.record.status = "failed"
            self.record.verification = "Action failed; inspect the application before retrying"
            raise
        finally:
            self.operation = None
            self.publish()
        return self.status()

    def pause(self):
        if self.universal.owner:
            self.universal.paused = True
        if self.workflow:
            self.workflow.pause()
            self.record.status = "paused"
            self.publish()

    def resume(self):
        if self.universal.owner:
            self.universal.paused = False
            return
        if not self.operation or not self.workflow:
            raise ValueError("Inspect and replan an interrupted session before resuming")
        self.workflow.resume()
        self.record.status = "running"
        self.publish()

    async def screenshot(self):
        if self.busy() and self.operation is not asyncio.current_task():
            raise ValueError("Pause the active action before requesting a separate capture")
        if not self.configuration()["screen_observation"] or not self.sessions or not self.sessions.current:
            raise PermissionError("Enable screen observation and inspect a target window first")
        session = self.sessions.sessions[self.sessions.current]
        await self.gateway.approval(session, "desktop.view_screen", "Capture only this application's window",
                                    {"application": session.identity.display_name}, always=True)
        from ..agent.tool_schema import ToolContext
        tool = self.s.tool_registry.require("desktop.capture")
        result = await tool.execute({"window": session.window}, ToolContext(session.task_id, progress_callback=tool))
        capture = result.data
        return self.screenshots.add(session.task_id, capture, self.configuration()["screenshot_retention"])

    async def browser_launch(self, channel="chrome"):
        return await self._browser_operation(self.browser.launch, channel)

    async def _browser_operation(self, function, *arguments):
        if self.busy():
            raise ValueError("A desktop operation is already active")
        self.gateway.check()
        if not self.record:
            self.record = DesktopControlSession("User-directed browser control")
            self.sessions = ApplicationSessions(self.record.id)
        self.browser.session.task_id = self.record.id
        self.operation = asyncio.current_task()
        self.record.status, self.record.application = "running", "OLIVE Interactive Browser"
        self.record.current_action = function.__name__
        self.publish()
        try:
            result = await function(*arguments)
            self.record.status = "completed"
            self.record.verification = "Browser operation returned verified observations" if isinstance(result, dict) and result.get("verified") else "Browser operation returned; inspect current state"
            self.record.history.append({"application": "Interactive browser", "action": function.__name__, "status": "completed"})
            self.record.history[:] = self.record.history[-100:]
            return result
        except asyncio.CancelledError:
            self.record.status = "cancelled"
            raise
        except Exception:
            self.record.status = "PAUSED_REVIEW_REQUIRED"
            self.record.verification = "Browser operation needs review; no automatic retry"
            raise
        finally:
            self.operation = None
            self.publish()

    async def open_folder(self, path):
        return await self._track(self.navigation.open_folder, path)

    async def open_settings(self, page="bluetooth"):
        return await self._track(self.navigation.open_settings, page)

    async def vision_observe(self, question):
        return await self._track(self._vision_observe, question)

    async def vision_verify_label(self, expected):
        return await self._track(self._vision_verify_label, expected)

    async def _vision_verify_label(self, expected):
        if not self.configuration()["vision_fallback"]:
            raise PermissionError("Enable vision fallback first")
        from ..desktop.vision import DesktopVision
        capture = await self.screenshot()
        return await DesktopVision(self.s.ollama, self.s.model_router).verify_label(capture, expected)

    async def _vision_observe(self, question):
        if not self.configuration()["vision_fallback"]:
            raise PermissionError("Enable vision fallback first")
        from ..desktop.vision import DesktopVision
        capture = await self.screenshot()
        result = await DesktopVision(self.s.ollama, self.s.model_router).observe(capture, question)
        self.visual.remember(result)
        return {**result, "capture": capture}

    async def visual_click(self, capture_id, expected):
        if self.busy():
            raise ValueError("A desktop operation is already active")
        self.operation = asyncio.current_task()
        try:
            return await self.visual.click(capture_id, expected)
        finally:
            self.operation = None
            self.publish()

    async def browser_navigate(self, tab_id, url):
        return await self._browser_operation(self.browser.navigate, tab_id, url)

    async def browser_observe(self, tab_id):
        return await self._browser_operation(self.browser.observe, tab_id)

    async def browser_action(self, target_id, action, value="", expected=""):
        return await self._browser_operation(self.browser.action, target_id, action, value, expected)

    async def browser_tab(self, action, tab_id="", url=""):
        return await self._browser_operation(self.browser.tab, action, tab_id, url)

    async def browser_dialog(self, dismiss=False):
        return await self._browser_operation(self.browser.dialog_review, dismiss)

    async def browser_send(self, fields, expected):
        return await self._browser_operation(self.browser.consequences.send, fields, expected)

    async def browser_upload(self, target_id, path):
        return await self._browser_operation(self.browser.consequences.upload, target_id, path)

    async def browser_download(self, target_id):
        result = await self._browser_operation(self.browser.download, target_id)
        from ..desktop.application_sessions import TaskValue, ContextTrust
        self.sessions.put_value("download", TaskValue(result["download"]["id"], ContextTrust.OBSERVATION, self.browser.session.identity.id))
        return result

    async def save_download(self, download_id, destination):
        return await self._track(self.s.research.export_download, download_id, destination)

    def stop(self):
        self.stop_event.set()
        if self.universal.owner:
            self.universal.owner.cancel()
        if self.operation:
            self.operation.cancel()
        self.publish()
        return self.status()

    def reset(self):
        if self.operation or self.universal.owner:
            raise ValueError("Wait for the active operation to stop")
        self.stop_event.clear()
        self.gateway.last_verified_window = None
        self.observation = {}
        self.pending_plan = []
        return self.status()

    async def shutdown(self):
        current = asyncio.current_task()
        pending = {task for task in (self.operation, self.universal.owner)
                   if task is not None and task is not current and not task.done()}
        self.stop()
        if pending:
            # Let operation finally blocks persist their paused state before
            # closing browser/helper resources or the shared repositories.
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=10)
        await self.browser.shutdown()
        await self.provider.close()
        self.media.provider.close()
