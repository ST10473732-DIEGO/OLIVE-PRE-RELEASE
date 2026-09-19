import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olive.agent.tool_schema import ToolContext
from olive.tools.system import SystemTool, WindowsApplicationResolver, _find_matching_processes, _matching_processes


class SystemToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # These fixtures exercise the retained Windows adapter without OS calls.
        guard = patch("olive.platform_support.require_windows")
        guard.start()
        self.addCleanup(guard.stop)

    def test_resolves_start_menu_shortcut(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); roaming = root / "roaming"; programs = roaming / "Microsoft/Windows/Start Menu/Programs/Discord Inc"
            programs.mkdir(parents=True); shortcut = programs / "Discord.lnk"; shortcut.write_bytes(b"shortcut")
            resolver = WindowsApplicationResolver(local_app_data=root/"local", roaming_app_data=roaming,
                                                  program_data=root/"programdata")
            self.assertEqual(resolver.resolve("Discord").path, shortcut.resolve())

    def test_resolves_squirrel_updater_when_no_shortcut_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); updater = root / "local/Discord/Update.exe"; updater.parent.mkdir(parents=True); updater.write_bytes(b"exe")
            resolver = WindowsApplicationResolver(local_app_data=root/"local", roaming_app_data=root/"roaming",
                                                  program_data=root/"programdata")
            target = resolver.resolve("Discord")
            self.assertEqual(target.path, updater.resolve())
            self.assertEqual(target.arguments, ("--processStart", "Discord.exe"))

    async def test_unknown_application_returns_structured_failure(self):
        tool = SystemTool("open_application")
        with patch("olive.tools.system.WindowsApplicationResolver.resolve", return_value=None):
            result = await tool.execute({"application":"DefinitelyMissing"}, ToolContext("task"))
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "ApplicationNotFound")

    def test_resolves_registered_app_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "Example.exe"; executable.write_bytes(b"exe")
            resolver = WindowsApplicationResolver(local_app_data=Path(tmp)/"local",
                                                  roaming_app_data=Path(tmp)/"roaming", program_data=Path(tmp)/"data")
            with patch.object(resolver, "_registered_app_paths", return_value={"example":executable}):
                self.assertEqual(resolver.resolve("Example").path, executable)

    def test_resolves_store_and_desktop_start_apps(self):
        resolver = WindowsApplicationResolver()
        apps = [{"Name":"Calculator","AppID":"Microsoft.Calculator!App"},
                {"Name":"Visual Studio Code","AppID":"Microsoft.VSCode"}]
        with patch.object(resolver, "_start_apps", return_value=apps):
            target = resolver.resolve("calculator")
            self.assertIn("shell:AppsFolder", target.arguments[0])
            self.assertEqual(resolver.resolve("visual studio code").arguments[0], "shell:AppsFolder\\Microsoft.VSCode")

    def test_ambiguous_fuzzy_app_name_is_not_guessed(self):
        resolver = WindowsApplicationResolver()
        with patch.object(resolver, "_start_apps", return_value=[{"Name":"Photo Editor One","AppID":"one"},
                                                                  {"Name":"Photo Editor Two","AppID":"two"}]):
            self.assertIsNone(resolver._match_start_app("Photo Editor"))

    async def test_close_application_uses_matching_pids(self):
        tool = SystemTool("close_application")
        processes = [{"name":"Discord.exe","pid":10},{"name":"Discord.exe","pid":11}]
        completed = __import__("subprocess").CompletedProcess([],0,"closed","")
        with patch("olive.tools.system._running_processes",return_value=processes), \
             patch("olive.tools.system.subprocess.run",return_value=completed) as run:
            result = await tool.execute({"application":"Discord"},ToolContext("task"))
        self.assertTrue(result.success); self.assertEqual(run.call_count,1)
        command = run.call_args.args[0]
        self.assertEqual(command.count("/PID"),2)

    def test_process_lookup_avoids_verbose_scan_when_name_matches(self):
        processes = [{"name":"Discord.exe","pid":10,"window_title":""}]
        with patch("olive.tools.system._running_processes",return_value=processes) as running:
            self.assertEqual(_find_matching_processes("Discord")[0]["pid"],10)
        running.assert_called_once_with()

    def test_process_lookup_uses_window_titles_only_as_fallback(self):
        fast = [{"name":"MSACCESS.EXE","pid":1,"window_title":""}]
        titled = [{"name":"MSACCESS.EXE","pid":1,"window_title":"Student Database - Access"}]
        with patch("olive.tools.system._running_processes",side_effect=[fast,titled]) as running:
            self.assertEqual(_find_matching_processes("Access")[0]["pid"],1)
        self.assertEqual(running.call_args_list[-1].kwargs,{"include_window_titles":True})

    async def test_close_protects_olive_and_windows_processes(self):
        tool = SystemTool("close_application")
        with patch("olive.tools.system._running_processes",return_value=[{"name":"python.exe","pid":10}]):
            result = await tool.execute({"application":"python"},ToolContext("task"))
        self.assertEqual(result.error_type,"ProtectedProcess")

    async def test_terminate_force_closes_entire_process_tree(self):
        tool = SystemTool("terminate_application")
        completed = __import__("subprocess").CompletedProcess([],0,"terminated","")
        with patch("olive.tools.system._running_processes",return_value=[{"name":"Discord.exe","pid":10}]), \
             patch("olive.tools.system.subprocess.run",return_value=completed) as run:
            result = await tool.execute({"application":"Discord"},ToolContext("task"))
        self.assertTrue(result.success); self.assertTrue(result.data["forced"])
        command = run.call_args.args[0]
        self.assertIn("/F",command); self.assertIn("/T",command)

    def test_process_matching_does_not_guess_ambiguous_prefix(self):
        processes=[{"name":"PhotoEditor.exe","pid":1},{"name":"PhotoEditorPro.exe","pid":2}]
        self.assertEqual(_matching_processes("Photo",processes),[])

    def test_process_matching_can_use_visible_window_title(self):
        processes=[{"name":"MSACCESS.EXE","pid":1,"window_title":"Student Database - Access"}]
        self.assertEqual(_matching_processes("Access",processes)[0]["pid"],1)


if __name__ == "__main__": unittest.main()
