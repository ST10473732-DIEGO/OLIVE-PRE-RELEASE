import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from olive.agent.agent_task import AgentTask
from olive.agent.direct_action import DirectAction
from olive.agent.executor import ToolExecutor
from olive.agent.permission_service import PermissionService
from olive.agent.planner import PlannedAction
from olive.agent.tool_schema import ToolContext, ToolDefinition
from olive.agent.tool_result import ToolResult
from olive.services.project_scaffold import create_folder
from olive.services.build_test_service import BuildAndTestService
from olive.services.run_service import RunService
from olive.workspace import Workspace


class DirectActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_action_skips_ask_but_never_deny(self):
        with tempfile.TemporaryDirectory() as directory:
            permissions = PermissionService(Path(directory)/'permissions.json')
            definition = ToolDefinition('studio.save', 'Save', 'studio', {},
                required_permissions=('filesystem.write',), confirmation_required=True)
            registry = Mock()
            registry.require.return_value.definition = definition
            host = Mock(execute=AsyncMock(return_value=ToolResult(True, 'Saved', {})))
            confirmations = Mock(request=AsyncMock(side_effect=AssertionError('Duplicate approval')))
            executor = ToolExecutor(registry, permissions, confirmations, Mock(), host)
            for decision in ('ask','deny'):
                permissions.save({'filesystem.write': decision})
                task = AgentTask('Save')
                args = {'path':'Main.java','text':'hello','expected_hash':'base'}
                result = await executor.execute(task, PlannedAction('studio.save',args),
                    ToolContext(task.id, direct_action=DirectAction(task.id,'studio.save',args)))
                self.assertEqual(result.success, decision == 'ask')
            host.execute.assert_awaited_once()

    def test_consent_is_exact_expiring_and_single_use(self):
        args = {'path':'a','text':'original'}
        for task, tool, supplied in [('other','studio.save',args), ('t','terminal.run',args),
                                     ('t','studio.save',dict(args,text='changed'))]:
            consent = DirectAction('t','studio.save',args)
            self.assertFalse(consent.consume(task,tool,supplied))
            self.assertFalse(consent.consume('t','studio.save',args))
        consent = DirectAction('t','studio.save',args)
        consent.expires = 0
        self.assertFalse(consent.consume('t','studio.save',args))
        consent = DirectAction('t','studio.save',args)
        self.assertTrue(consent.consume('t','studio.save',args))
        self.assertFalse(consent.consume('t','studio.save',args))


class ProjectStarterTests(unittest.TestCase):
    def test_dotnet_environment_is_project_local_and_does_not_inherit_secrets(self):
        from unittest.mock import patch
        from olive.services.run_service import ExecutionPolicy
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {
            'APPDATA':'private-user-settings', 'DOTNET_CLI_HOME':'private-home',
            'NUGET_AUTH_TOKEN':'secret', 'PROGRAMFILES':'sdk-installation',
        }, clear=True):
            env = RunService.dotnet_environment(directory, ExecutionPolicy().environment())
            self.assertTrue(Path(env['DOTNET_CLI_HOME']).is_relative_to(Path(directory)))
            self.assertTrue(Path(env['APPDATA']).is_relative_to(Path(directory)))
            self.assertNotIn('NUGET_AUTH_TOKEN', env)
            self.assertEqual(env['PROGRAMFILES'], 'sdk-installation')

    def test_csharp_starter_uses_existing_dotnet_services_without_packages(self):
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as directory:
            root = create_folder(directory, 'CSharp Fixture', 'csharp')
            project = ET.parse(root/'App.csproj').getroot()
            self.assertEqual(project.findtext('PropertyGroup/TargetFramework'), 'net10.0')
            self.assertFalse(project.findall('.//PackageReference'))
            self.assertIsNotNone(ET.parse(root/'NuGet.Config').find('packageSources/clear'))
            self.assertIn('Console.WriteLine', (root/'Program.cs').read_text())
            command, _ = RunService.detect_command(Workspace('CSharp', str(root)))
            self.assertEqual(command[0], 'dotnet')
            self.assertIn('run', command)
            self.assertEqual([c.name for c in BuildAndTestService().detect(root)],
                             ['.NET restore', '.NET build', '.NET test'])

    def test_java_starter_and_run_build_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = create_folder(directory, 'My Java Project', 'java')
            self.assertEqual(root.parent, Path(directory).resolve()/'projects')
            command, kind = RunService.detect_command(Workspace('Java',str(root)))
            self.assertEqual(kind,'java_console')
            self.assertIn(str(root/'lib'/'*'), command[2])
            self.assertEqual(command[-1], str(root/'Main.java'))
            checks = BuildAndTestService().detect(root)
            self.assertEqual(checks[0].executable,'javac')
            self.assertIn('-proc:none',checks[0].arguments)

    def test_project_names_cannot_escape_or_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('../escape','a/b','C:\\oops','CON','NUL.txt','trailing.','bad:stream'):
                with self.assertRaises(ValueError):
                    create_folder(directory,name,'java')
            root = create_folder(directory,'Keep','python')
            (root/'main.py').write_text('user content',encoding='utf-8')
            with self.assertRaises(FileExistsError):
                create_folder(directory,'Keep','java')
            self.assertEqual((root/'main.py').read_text(),'user content')

    def test_python_and_javascript_starters(self):
        with tempfile.TemporaryDirectory() as directory:
            for language, entry in [('python','main.py'),('javascript','main.js')]:
                root = create_folder(directory,language,language)
                command, _ = RunService.detect_command(Workspace(language,str(root)))
                self.assertEqual(command[-1],str(root/entry))
