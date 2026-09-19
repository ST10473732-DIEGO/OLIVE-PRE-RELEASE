import asyncio
import unittest

from olive.desktop.application_discovery import identity
from olive.desktop.application_sessions import ApplicationSessions
from olive.desktop.workflow import DesktopStep, DesktopWorkflow


class FakeGateway:
    def __init__(self):
        self.controls = {}
        self.actions = []
        self.allow = True
        self.verify = True

    async def observe(self, session):
        return {"window": {"hwnd": 1 if session.identity.display_name == "A" else 2, "pid": 10},
                "controls": self.controls.get(session.identity.id, [])}

    async def authorize(self, session, step):
        if not self.allow:
            raise PermissionError("Denied")
        return "test-permit"

    async def execute(self, session, step, permit, stop):
        if permit != "test-permit" or stop.is_set():
            raise PermissionError("Invalid authorization")
        self.actions.append((session.identity.id, step.action))
        if self.verify:
            self.controls[session.identity.id] = [dict(step.expected)]


class DesktopWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.a = identity("A", "executable", "a.exe")
        self.b = identity("B", "executable", "b.exe")
        self.identities = {app.id: app for app in (self.a, self.b)}
        self.gateway = FakeGateway()
        self.workflow = DesktopWorkflow(ApplicationSessions("test"), self.gateway, timeout=.1)

    def step(self, app):
        return DesktopStep(app.id, "set_text", {"name": "Editor"}, {"text": "hello"},
                           {"name": "Editor", "value": "hello"}, "desktop.keyboard_input")

    async def test_adapter_free_multi_app_round_trip(self):
        result = await self.workflow.run([self.step(app) for app in (self.a, self.b, self.a)], self.identities)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual([app for app, _ in self.gateway.actions], [self.a.id, self.b.id, self.a.id])
        self.assertNotIn("hello", str(result))

    async def test_denial_stops_before_input(self):
        self.gateway.allow = False
        with self.assertRaises(PermissionError):
            await self.workflow.run([self.step(self.a)], self.identities)
        self.assertFalse(self.gateway.actions)

    async def test_transient_verification_snapshot_never_repeats_input(self):
        from olive.desktop.errors import ObservationUnavailable
        observe = self.gateway.observe
        failed = False
        async def changing_snapshot(session):
            nonlocal failed
            if self.gateway.actions and not failed:
                failed = True
                raise ObservationUnavailable("Fixture tree replaced")
            return await observe(session)
        self.gateway.observe = changing_snapshot
        result = await self.workflow.run([self.step(self.a)], self.identities)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(len(self.gateway.actions), 1)

    async def test_unavailable_snapshots_remain_bounded_and_fail(self):
        from olive.desktop.errors import ObservationUnavailable
        observe = self.gateway.observe
        async def unavailable(session):
            if self.gateway.actions:
                raise ObservationUnavailable("Fixture unavailable")
            return await observe(session)
        self.gateway.observe = unavailable
        self.workflow.timeout = .5
        with self.assertRaises(ObservationUnavailable):
            await self.workflow.run([self.step(self.a)], self.identities)
        self.assertEqual(len(self.gateway.actions), 1)

    async def test_existing_label_cannot_verify_a_new_invocation(self):
        self.gateway.controls[self.a.id] = [{"name": "Save"}]
        step = DesktopStep(self.a.id, "invoke", {"name": "Save"}, {}, {"name": "Save"}, "desktop.control_application")
        with self.assertRaisesRegex(ValueError, "postcondition already exists"):
            await self.workflow.run([step], self.identities)
        self.assertFalse(self.gateway.actions)
        self.assertEqual(self.workflow.status, "PAUSED_REVIEW_REQUIRED")

    async def test_sent_input_is_not_success_without_verification(self):
        self.gateway.verify = False
        with self.assertRaises(TimeoutError):
            await self.workflow.run([self.step(self.a)], self.identities)
        self.assertEqual(len(self.gateway.actions), 1)  # Never repeat a consequential action blindly.
        self.assertEqual(self.workflow.status, "PAUSED_REVIEW_REQUIRED")

    async def test_emergency_stop_blocks_future_actions(self):
        self.workflow.emergency_stop()
        with self.assertRaises(asyncio.CancelledError):
            await self.workflow.run([self.step(self.a)], self.identities)
        self.assertFalse(self.gateway.actions)

    async def test_unknown_application_rejected_before_observation(self):
        with self.assertRaises(ValueError):
            await self.workflow.run([self.step(self.a)], {})

    async def test_pause_blocks_progress(self):
        self.workflow.pause()
        task = asyncio.create_task(self.workflow.run([self.step(self.a)], self.identities))
        await asyncio.sleep(.06)
        self.assertFalse(self.gateway.actions)
        self.workflow.resume()
        result = await asyncio.wait_for(task, 1)
        self.assertEqual(result["status"], "COMPLETED")

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            DesktopStep(self.a.id, "run_shell", {}, {}, {"value": "done"}, "desktop.control_application")
