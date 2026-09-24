from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from olive.agent.permission_service import PermissionService
from olive.desktop.adapters import ApplicationAdapterRegistry
from olive.desktop.communication import ExternalMessagePreview
from olive.desktop.control import DesktopControlService,DesktopTarget,Observation
from olive.services.checkpoint_service import CheckpointService
from olive.services.problem_service import ProblemService
from olive.services.run_service import ExecutionPolicy,RunService
from olive.services.execution_provider import ExecutionProviderRegistry, DockerExecutionProvider, NativeExecutionProvider
from olive.services.studio_service import StudioService
from olive.workspace import Workspace


class Adapter:
    name="test";capabilities=("launch","read_state")


class Provider:
    name="fake"
    async def act(self,target,action,arguments):return {"issued":action}
    async def observe(self,target):return Observation(target,{"channel":"programming"})


class StudioRunTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.workspace=Workspace("Test",str(self.root))

    async def test_terminal_status_waits_for_exit_code_and_output_drain(self):
        native = Mock(spec=NativeExecutionProvider)
        process = Mock(pid=123, returncode=0)
        process.stdout = asyncio.StreamReader()
        process.stderr = asyncio.StreamReader()
        process.stdout.feed_data(b'owned output\n')
        process.stdout.feed_eof()
        process.stderr.feed_eof()
        process.wait = AsyncMock(return_value=0)
        native.start = AsyncMock(return_value=process)
        service = RunService(ExecutionProviderRegistry(native=native))
        draining, release = asyncio.Event(), asyncio.Event()
        original_wait = asyncio.wait_for

        async def held_drain(awaitable, timeout):
            if isinstance(awaitable, asyncio.Future):
                draining.set()
                await release.wait()
            return await original_wait(awaitable, timeout)

        with patch('olive.services.run_service.asyncio.wait_for', held_drain):
            session = await service.start(self.workspace, ['python', 'main.py'])
            try:
                await original_wait(draining.wait(), 2)
                self.assertEqual(session.state, 'running')
                self.assertIsNone(session.exit_code)
                self.assertIn(session.id, service._processes)
            finally:
                release.set()
                await service.wait(session.id)
        self.assertEqual((session.state, session.exit_code), ('completed', 0))
        self.assertEqual(session.stdout, 'owned output\n')
        self.assertNotIn(session.id, service._processes)

    async def test_run_lifecycle_stdout_stderr_exit_and_url(self):
        service=RunService();session=await service.start(self.workspace,[sys.executable,"-c","import sys;print('http://localhost:8123');print('warning',file=sys.stderr)"],"local_web",ExecutionPolicy(max_runtime_seconds=5))
        self.assertEqual(session.state,"running");completed=await service.wait(session.id)
        self.assertEqual(completed.state,"completed");self.assertEqual(completed.exit_code,0);self.assertIn("warning",completed.stderr);self.assertEqual(completed.local_url,"http://localhost:8123")

    async def test_run_timeout_and_cancellation(self):
        service=RunService();timed=await service.start(self.workspace,[sys.executable,"-c","import time;time.sleep(2)"],policy=ExecutionPolicy(max_runtime_seconds=.1));self.assertEqual((await service.wait(timed.id)).state,"timed_out")
        running=await service.start(self.workspace,[sys.executable,"-c","import time;time.sleep(5)"],policy=ExecutionPolicy(max_runtime_seconds=10));self.assertEqual((await service.stop(running.id)).state,"stopped")
        self.assertIsNotNone(running.exit_code)
        self.assertNotIn(running.id, service._processes)

    async def test_untrusted_run_fails_closed_without_isolation_provider(self):
        native = Mock(spec=NativeExecutionProvider)
        docker = Mock(spec=DockerExecutionProvider)
        docker.available.return_value = False
        service = RunService(ExecutionProviderRegistry(native=native, docker=docker))
        with self.assertRaisesRegex(PermissionError, 'requires Docker isolation'):
            await service.start(self.workspace, [sys.executable, '-c', "print('no')"],
                                policy=ExecutionPolicy('untrusted'))
        native.start.assert_not_called()
        docker.start.assert_not_called()
        self.assertFalse(service.sessions)
        self.assertFalse(service._processes)

    async def test_untrusted_run_uses_available_isolation_provider_only(self):
        native = Mock(spec=NativeExecutionProvider)
        docker = Mock(spec=DockerExecutionProvider)
        docker.available.return_value = True
        process = Mock(pid=123, returncode=0)
        process.stdout = asyncio.StreamReader()
        process.stderr = asyncio.StreamReader()
        process.stdout.feed_eof()
        process.stderr.feed_eof()
        process.wait = AsyncMock(return_value=0)
        docker.start = AsyncMock(return_value=process)
        service = RunService(ExecutionProviderRegistry(native=native, docker=docker))
        command = ['python', '-c', "print('isolated fixture')"]
        session = await service.start(self.workspace, command, policy=ExecutionPolicy('untrusted'))
        self.assertEqual((await service.wait(session.id)).state, 'completed')
        docker.start.assert_awaited_once()
        self.assertEqual(docker.start.call_args.args[0], command)
        self.assertFalse(docker.start.call_args.args[3].network_enabled)
        native.start.assert_not_called()

    def test_execution_policy_filters_secrets_and_artifacts_stay_in_workspace(self):
        environment=ExecutionPolicy().environment({"PATH":"safe","API_KEY":"never","UNRELATED":"no"})
        self.assertEqual(environment["PATH"],"safe");self.assertNotIn("API_KEY",environment);self.assertNotIn("UNRELATED",environment)
        artifact=self.root/"result.csv";artifact.write_text("a,b",encoding="utf-8");service=RunService();session=__import__("olive.services.run_service",fromlist=["RunSession"]).RunSession(self.workspace.id,["test"],"console");service.sessions[session.id]=session
        self.assertEqual(service.add_artifact(session.id,self.workspace,"result.csv").label,"result.csv")
        with self.assertRaises(PermissionError):service.add_artifact(session.id,self.workspace,"../outside.txt")

    def test_problem_parsing(self):
        output="Program.cs(12,4): error CS1002: ; expected [App.csproj]\n  File \"app.py\", line 7, in main\n    broken()"
        values=ProblemService().parse(output);self.assertEqual(values[0].error_code,"CS1002");self.assertEqual(values[0].line,12);self.assertEqual(values[1].tool,"python")

    def test_studio_file_state_save_and_concurrent_edit(self):
        path=self.root/"app.py";path.write_text("one",encoding="utf-8");studio=StudioService(self.workspace,CheckpointService(self.root/"snapshots"));state=studio.open_file("app.py");studio.update("app.py","two");self.assertTrue(state.unsaved)
        studio.save("app.py","task");self.assertFalse(state.unsaved);self.assertEqual(path.read_text(),"two")
        studio.update("app.py","three");path.write_text("human",encoding="utf-8")
        with self.assertRaises(RuntimeError):studio.save("app.py","task2")

    def test_adapter_registry_permissions_and_external_message_contract(self):
        registry=ApplicationAdapterRegistry();registry.register(Adapter());self.assertIn("launch",registry.capabilities()["test"])
        with self.assertRaises(ValueError):registry.register(Adapter())
        permissions=PermissionService(self.root/"permissions.json");self.assertEqual(permissions.evaluate("desktop.view_screen").decision.value,"deny");self.assertEqual(permissions.evaluate("communication.send").decision.value,"ask")
        preview=ExternalMessagePreview("Discord","server/channel","Exact message");self.assertEqual(preview.permission,"communication.send")

    async def test_act_observe_verify_does_not_assume_success(self):
        target=DesktopTarget("Discord",role="channel",name="programming");service=DesktopControlService(Provider())
        success=await service.act_observe_verify(target,"navigate",{},lambda observed:observed.state.get("channel")=="programming")
        failure=await service.act_observe_verify(target,"navigate",{},lambda observed:observed.state.get("channel")=="general")
        self.assertTrue(success["verified"]);self.assertFalse(failure["verified"]);self.assertTrue(success["observation"].untrusted_content)


if __name__=="__main__":unittest.main()
