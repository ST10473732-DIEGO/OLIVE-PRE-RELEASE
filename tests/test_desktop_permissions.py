from pathlib import Path
import tempfile
import unittest

from olive.agent.permission_service import PermissionService, PermissionDecision


class DesktopPermissionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.permissions = PermissionService(Path(self.folder.name) / "permissions.json")

    def test_application_scope_overrides_global_control(self):
        self.permissions.save({"desktop.control_application": "allow"}, [
            {"application": "app-id", "permission": "desktop.control_application", "decision": "deny"}])
        self.assertEqual(self.permissions.evaluate("desktop.control_application", application="app-id").decision,
                         PermissionDecision.DENY)

    def test_duplicate_application_rules_cannot_dilute_deny(self):
        self.permissions.save({}, [{"application": "app-id", "permission": "desktop.keyboard_input", "decision": value}
                                   for value in ("allow", "deny")])
        self.assertEqual(self.permissions.evaluate("desktop.keyboard_input", application="app-id").decision,
                         PermissionDecision.DENY)

    def test_application_metadata_is_not_a_permission(self):
        self.permissions.save({"desktop.control_application": "allow"})
        for permission in ("software.install", "software.purchase", "communication.send", "application.upload"):
            self.assertEqual(self.permissions.evaluate(permission, application="app-id").decision, PermissionDecision.ASK)

    def test_unrelated_application_rule_does_not_apply(self):
        self.permissions.save({}, [{"application": "one", "permission": "desktop.keyboard_input", "decision": "allow"}])
        self.assertEqual(self.permissions.evaluate("desktop.keyboard_input", application="two").decision,
                         PermissionDecision.DENY)
