import tempfile, unittest
import asyncio
from olive.agent.tool_schema import ToolContext
from olive.tools.terminal import TerminalRunTool

class TerminalTests(unittest.IsolatedAsyncioTestCase):
    async def test_output_bound_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool=TerminalRunTool(); context=ToolContext("t")
            result=await tool.execute({"environment":"python","command":"print('x'*5000)","working_directory":tmp,"max_output_bytes":1024},context)
            self.assertTrue(result.success); self.assertTrue(result.data["stdout_truncated"])
            timeout=await tool.execute({"environment":"python","command":"import time; time.sleep(2)","working_directory":tmp,"timeout":.1},context)
            self.assertEqual(timeout.error_type,"Timeout")
    def test_admin_and_destructive_detection(self):
        self.assertTrue(TerminalRunTool.requires_admin("Start-Process cmd -Verb RunAs"))
        self.assertTrue(TerminalRunTool.destructive("Remove-Item thing"))

    async def test_active_command_can_be_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            event=asyncio.Event(); context=ToolContext("t",event)
            task=asyncio.create_task(TerminalRunTool().execute({"environment":"python","command":"import time; time.sleep(5)","working_directory":tmp},context))
            await asyncio.sleep(.05); event.set(); result=await task
            self.assertEqual(result.error_type,"Cancelled")

    async def test_terminal_excludes_unrelated_environment_secrets(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{'OLIVE_FIXTURE_TOKEN':'must-not-leak','OLIVE_UNRELATED_VALUE':'also-private'}):
            result=await TerminalRunTool().execute({'environment':'python','command':"import os; print(os.getenv('OLIVE_FIXTURE_TOKEN')); print(os.getenv('OLIVE_UNRELATED_VALUE'))",'working_directory':tmp},ToolContext('fixture'))
            self.assertTrue(result.success)
            self.assertEqual(result.data['stdout'].splitlines(),['None','None'])
