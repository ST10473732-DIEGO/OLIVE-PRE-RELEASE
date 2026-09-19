import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from olive.desktop.consequence_service import DesktopConsequences


class DesktopConsequenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.d = Mock()
        session = SimpleNamespace(key="app", identity=SimpleNamespace(id="app", display_name="Store"), observe=Mock())
        self.d.sessions.current = "app"
        self.d.sessions.sessions = {"app": session}
        self.d.gateway.approval = AsyncMock()
        self.d.gateway.execute = AsyncMock()
        self.d.gateway.permits = {}
        self.controls = [{"runtime_id": key, "name": name} for key, name in
                         (("app", "Fixture App"), ("publisher", "Fixture Publisher"), ("cost", "Free"))]
        self.controls.append({"runtime_id": "install", "name": "Install", "actions": ["invoke"]})
        self.bindings = {key: {"runtime_id": target} for key, target in
                         (("application", "app"), ("publisher", "publisher"), ("cost", "cost"))}
        self.service = DesktopConsequences(self.d)
        self.d.gateway.observe = AsyncMock(side_effect=[{"controls": self.controls}, {"controls": self.controls},
                                                        {"controls": [{"name": "Installed"}]}])

    async def test_free_install_requires_semantic_preview_then_verified_result(self):
        result = await self.service.run("software.install", {"runtime_id": "install"}, self.bindings, {"name": "Installed"})
        self.assertTrue(result["verified"])
        approval = self.d.gateway.approval.await_args
        self.assertEqual(approval.args[1], "software.install")
        self.assertEqual(approval.args[3], {"application": "Fixture App", "publisher": "Fixture Publisher", "cost": "free", "source": "Store"})
        self.assertTrue(approval.kwargs["always"])
        self.d.gateway.execute.assert_awaited_once()

    async def test_paid_or_unknown_cost_cannot_use_install_approval(self):
        for price in ("$4.99", "Free trial", "Unknown"):
            self.controls[2]["name"] = price
            self.d.gateway.observe = AsyncMock(return_value={"controls": self.controls})
            with self.assertRaises(PermissionError):
                await self.service.run("software.install", {"runtime_id": "install"}, self.bindings, {"name": "Installed"})
        self.d.gateway.execute.assert_not_awaited()

    async def test_publisher_changed_after_approval_stops_install(self):
        changed = [dict(item) for item in self.controls]
        changed[1]["name"] = "Different publisher"
        self.d.gateway.observe = AsyncMock(side_effect=[{"controls": self.controls}, {"controls": changed}])
        with self.assertRaisesRegex(PermissionError, "evidence changed"):
            await self.service.run("software.install", {"runtime_id": "install"}, self.bindings, {"name": "Installed"})
        self.d.gateway.execute.assert_not_awaited()

    async def test_existing_completion_state_does_not_validate_new_install(self):
        self.controls.append({"name": "Installed"})
        with self.assertRaisesRegex(ValueError, "already exists"):
            await self.service.run("software.install", {"runtime_id": "install"}, self.bindings, {"name": "Installed"})
        self.d.gateway.execute.assert_not_awaited()

    async def test_secret_field_cannot_be_preview_evidence(self):
        self.controls[0]["password"] = True
        with self.assertRaises(PermissionError):
            await self.service.run("software.install", {"runtime_id": "install"}, self.bindings, {"name": "Installed"})
        self.d.gateway.execute.assert_not_awaited()
