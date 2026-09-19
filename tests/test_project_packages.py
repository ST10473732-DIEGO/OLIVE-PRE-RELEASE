import tempfile
import unittest
from pathlib import Path
from olive.services.package_service import installation_plan
from olive.workspace import Workspace


class PackagePlanTests(unittest.TestCase):
    def test_python_is_project_local_and_does_not_execute_source_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            plan=installation_plan(Workspace('Fixture',directory),'python','example-package==1.2.3')
            self.assertEqual(plan[0][-1],str(Path(directory).resolve()/'.venv'))
            self.assertIn('--only-binary=:all:',plan[-1])
            self.assertIn('--require-virtualenv',plan[-1])
            self.assertEqual(plan[-1][-1],'example-package==1.2.3')

    def test_options_urls_paths_shell_and_untrusted_installations_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Workspace('Fixture',directory)
            for manager in ('python','node'):
                for name in ('--global','https://example.org/a','../library','a;whoami','a && cmd','a --index-url x'):
                    with self.assertRaises(ValueError):installation_plan(workspace,manager,name)
            workspace.trust_level='untrusted'
            with self.assertRaises(PermissionError):installation_plan(workspace,'python','example')
