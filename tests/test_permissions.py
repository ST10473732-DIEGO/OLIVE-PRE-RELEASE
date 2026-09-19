import tempfile, unittest
from pathlib import Path
from olive.agent.permission_service import PermissionDecision, PermissionService

class PermissionTests(unittest.TestCase):
    def test_app_allow_cannot_skip_more_specific_path_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = PermissionService(Path(tmp) / "p.json")
            service.save({}, [{"permission": "filesystem.read", "application": "browser", "decision": "allow"},
                              {"permission": "filesystem.read", "path": tmp, "decision": "deny"}])
            self.assertEqual(service.evaluate("filesystem.read", str(Path(tmp) / "private.txt"), application="browser").decision, PermissionDecision.DENY)

    def test_app_path_rule_and_equal_specificity_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = PermissionService(Path(tmp) / "p.json")
            rules = [{"permission": "filesystem.read", "path": tmp, "decision": "allow"},
                     {"permission": "filesystem.read", "path": tmp, "application": "browser", "decision": "deny"}]
            service.save({}, rules)
            self.assertEqual(service.evaluate("filesystem.read", tmp, application="browser").decision, PermissionDecision.DENY)
            self.assertEqual(service.evaluate("filesystem.read", tmp, application="editor").decision, PermissionDecision.ALLOW)
            rules.append({"permission": "filesystem.read", "path": tmp, "decision": "deny"})
            service.save({}, rules)
            self.assertEqual(service.evaluate("filesystem.read", tmp, application="editor").decision, PermissionDecision.DENY)

    def test_most_specific_scope_and_default_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); child=root/"project"; child.mkdir()
            service=PermissionService(root/"p.json")
            service.save({"filesystem.read":"deny"},[{"permission":"filesystem.read","path":str(child),"decision":"allow"}])
            self.assertEqual(service.evaluate("filesystem.read",str(child/"x")).decision,PermissionDecision.ALLOW)
            self.assertEqual(service.evaluate("filesystem.read",str(root/"other")).decision,PermissionDecision.DENY)
            self.assertEqual(service.evaluate("unknown.permission").decision,PermissionDecision.DENY)

    def test_trusted_actions_are_tool_and_target_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=PermissionService(Path(tmp)/"p.json")
            service.trust_action("system.open_application","Discord.exe")
            self.assertTrue(service.is_action_trusted("system.open_application","discord"))
            self.assertFalse(service.is_action_trusted("system.close_application","discord"))
            self.assertFalse(service.is_action_trusted("system.open_application","chrome"))
            self.assertEqual(service.clear_trusted_actions(),1)

    def test_wildcard_trust_is_limited_to_one_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=PermissionService(Path(tmp)/"p.json")
            service.trust_action("system.open_application","*")
            self.assertTrue(service.is_action_trusted("system.open_application","any app"))
            self.assertFalse(service.is_action_trusted("system.close_application","any app"))
