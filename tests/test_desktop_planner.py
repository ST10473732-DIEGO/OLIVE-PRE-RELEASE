import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from olive.desktop.application_discovery import identity
from olive.desktop.application_sessions import ApplicationSessions
from olive.desktop.planner import DesktopPlanner


class DesktopPlannerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sessions = ApplicationSessions("task")
        self.app = identity("Unknown app", "executable", "unknown.exe")
        session = self.sessions.select(self.app)
        session.observe({"window": {"hwnd": 1, "pid": 2}, "controls": [
            {"runtime_id": "field", "name": "Text", "visible": True, "enabled": True,
             "control_type": "Edit", "actions": ["set_text"]}]})
        self.ollama = SimpleNamespace(chat_once=AsyncMock())
        self.roles = []
        def route(request):
            self.roles.append(request.role)
            return SimpleNamespace(name="local-model")
        self.planner = DesktopPlanner(self.ollama, SimpleNamespace(route=route))

    def response(self, **changes):
        return {"steps": [{"application_id": self.app.id, "control_id": "field", "action": "set_text",
                           "text": "Hello", "expected_name": "", **changes}]}

    async def test_unknown_app_plan_uses_observed_capability_and_fast_role(self):
        self.ollama.chat_once.return_value = json.dumps(self.response())
        steps = await self.planner.plan("Type Hello", self.sessions)
        self.assertEqual(steps[0].expected["value"], "Hello")
        self.assertEqual(self.roles, ["fast"])

    async def test_invented_control_rejected(self):
        self.ollama.chat_once.return_value = json.dumps(self.response(control_id="invented"))
        with self.assertRaises(ValueError):
            await self.planner.plan("Type Hello", self.sessions)

    async def test_screen_text_cannot_create_tool(self):
        self.ollama.chat_once.return_value = json.dumps(self.response(action="run_powershell"))
        with self.assertRaises(ValueError):
            await self.planner.plan("Type Hello", self.sessions)

    async def test_markdown_wrapped_json_rejected(self):
        self.ollama.chat_once.return_value = "```json\n" + json.dumps(self.response()) + "\n```"
        with self.assertRaises(ValueError):
            await self.planner.plan("Type Hello", self.sessions)
