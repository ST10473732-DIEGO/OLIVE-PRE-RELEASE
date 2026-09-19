"""Real Studio tooling: project system, run configurations, structured tests, PTY,
LSP versioning and DAP lifecycle. Tool-backed tests skip honestly when the
pinned toolchain is not provisioned on this machine."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from olive.studio_tooling import dotnet, run_config, web
from olive.studio_tooling.toolchain import PINNED, dotnet_executable, module_available

ROOT = Path(__file__).resolve().parents[1]
HAVE_DOTNET = dotnet_executable() is not None
HAVE_OMNISHARP = PINNED["omnisharp"]["executable"].is_file()
HAVE_NETCOREDBG = PINNED["netcoredbg"]["executable"].is_file()
HAVE_WINPTY = sys.platform == "win32" and module_available(sys.executable, "winpty")
HAVE_DEBUGPY = module_available(sys.executable, "debugpy")


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ProjectSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_scan_parses_slnx_sln_projects_and_launch_profiles(self):
        write(self.root / "App.slnx", '<Solution><Folder Name="/src/"><Project Path="src/App/App.csproj" /></Folder><Project Path="tests/App.Tests/App.Tests.csproj" /></Solution>')
        write(self.root / "Legacy.sln", 'Microsoft Visual Studio Solution File\nProject("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "src\\App\\App.csproj", "{11111111-1111-1111-1111-111111111111}"\nEndProject\n')
        write(self.root / "src/App/App.csproj", '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup><ItemGroup><ProjectReference Include="..\\Core\\Core.csproj" /></ItemGroup></Project>')
        write(self.root / "src/App/Properties/launchSettings.json", json.dumps({"profiles": {"http": {"commandName": "Project", "applicationUrl": "http://localhost:5100", "launchBrowser": True}}}))
        write(self.root / "src/Core/Core.csproj", '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFrameworks>net10.0;net8.0</TargetFrameworks></PropertyGroup></Project>')
        write(self.root / "tests/App.Tests/App.Tests.csproj", '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup><ItemGroup><PackageReference Include="xunit" Version="2.9.3" /><PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.14.1" /></ItemGroup></Project>')
        write(self.root / "global.json", json.dumps({"sdk": {"version": "10.0.400", "rollForward": "latestFeature"}}))
        write(self.root / "bin/Ignored/Ignored.csproj", "<Project />")
        scanned = dotnet.scan(self.root)
        self.assertEqual(scanned["kind"], "dotnet")
        self.assertEqual({s["format"] for s in scanned["solutions"]}, {"slnx", "sln"})
        slnx = next(s for s in scanned["solutions"] if s["format"] == "slnx")
        self.assertEqual(len(slnx["projects"]), 2)
        names = {p["name"]: p for p in scanned["projects"]}
        self.assertEqual(set(names), {"App", "Core", "App.Tests"})
        self.assertTrue(names["App"]["is_web"] and names["App"]["is_executable"])
        self.assertEqual(names["App"]["launch_profiles"][0]["application_url"], "http://localhost:5100")
        self.assertEqual(names["Core"]["target_frameworks"], ["net10.0", "net8.0"])
        self.assertTrue(names["App.Tests"]["is_test"] and not names["App.Tests"]["uses_testing_platform"])
        self.assertEqual(scanned["global_json"]["sdk_version"], "10.0.400")
        self.assertEqual(Path(dotnet.default_startup(scanned["projects"])).name, "App.csproj")

    def test_commands_are_structured_and_validated(self):
        self.assertEqual(dotnet.build_command("x.sln", "Release", "rebuild")[:6], ["dotnet", "build", "x.sln", "-c", "Release", "--no-incremental"])
        with self.assertRaises(ValueError):
            dotnet.build_command("x.sln", "Custom; rm -rf", "build")
        with self.assertRaises(ValueError):
            dotnet.build_command("x.sln", "Debug", "publish")
        vstest = dotnet.test_command("t.csproj", "Debug", "out", ["A.B.C"], testing_platform=False)
        self.assertIn("trx;LogFileName=olive.trx", vstest)
        self.assertIn("FullyQualifiedName=A.B.C", vstest)
        platform = dotnet.test_command("t.csproj", "Debug", "out", None, testing_platform=True)
        self.assertIn("--report-trx", platform)
        self.assertEqual(dotnet.run_command("p.csproj", "Debug", ["--flag"])[-3:], ["--no-launch-profile", "--", "--flag"])

    def test_trx_and_build_diagnostics_parse_structured_results(self):
        trx = self.root / "olive.trx"
        write(trx, '''<?xml version="1.0" encoding="utf-8"?>
<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <Results>
    <UnitTestResult testId="a" testName="Adds" outcome="Passed" duration="00:00:00.0123456" />
    <UnitTestResult testId="b" testName="Fails" outcome="Failed" duration="00:00:01.5">
      <Output><ErrorInfo><Message>Assert.Equal() Failure: Expected 3 Actual 4</Message><StackTrace>   at App.Tests.MathTests.Fails() in C:\\work\\tests\\App.Tests\\MathTests.cs:line 17</StackTrace></ErrorInfo></Output>
    </UnitTestResult>
    <UnitTestResult testId="c" testName="Skipped" outcome="NotExecuted" duration="00:00:00" />
  </Results>
  <TestDefinitions>
    <UnitTest id="a"><TestMethod className="App.Tests.MathTests" name="Adds" /></UnitTest>
    <UnitTest id="b"><TestMethod className="App.Tests.MathTests" name="Fails" /></UnitTest>
    <UnitTest id="c"><TestMethod className="App.Tests.MathTests" name="Skipped" /></UnitTest>
  </TestDefinitions>
</TestRun>''')
        parsed = dotnet.parse_trx(trx)
        self.assertEqual(parsed["summary"], {"total": 3, "passed": 1, "failed": 1, "skipped": 1, "duration_seconds": 1.512})
        failed = next(r for r in parsed["results"] if r["state"] == "failed")
        self.assertEqual((failed["full_name"], failed["file"], failed["line"]), ("App.Tests.MathTests.Fails", "C:\\work\\tests\\App.Tests\\MathTests.cs", 17))
        self.assertIn("Expected 3", failed["message"])
        diagnostics = dotnet.parse_build_diagnostics("C:\\w\\src\\App\\Program.cs(12,9): error CS0029: Cannot implicitly convert type 'string' to 'int' [C:\\w\\src\\App\\App.csproj]\n"
                                                    "C:\\w\\src\\App\\Program.cs(12,9): error CS0029: Cannot implicitly convert type 'string' to 'int' [C:\\w\\src\\App\\App.csproj]\n"
                                                    "warning NU1603: something unrelated\n")
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual((diagnostics[0]["line"], diagnostics[0]["column"], diagnostics[0]["code"], diagnostics[0]["severity"]), (12, 9, "CS0029", "error"))
        self.assertEqual(dotnet.parse_list_tests("Test run for x\nThe following Tests are available:\n    A.B.C\n    A.B.D\n"), ["A.B.C", "A.B.D"])

    def test_run_configuration_rejects_secrets_and_escapes(self):
        config = run_config.sanitize({"startup_project": "src/App/App.csproj", "configuration": "Release", "arguments": ["--port", "5001"],
                                      "environment": {"ASPNETCORE_ENVIRONMENT": "Development"}}, self.root)
        self.assertEqual(config["configuration"], "Release")
        self.assertEqual(run_config.sanitize({}, self.root)['environment'], {})
        self.assertTrue(Path(config["startup_project"]).is_relative_to(self.root))
        with self.assertRaises(ValueError):
            run_config.sanitize({"environment": {"API_KEY": "x"}}, self.root)
        with self.assertRaises(ValueError):
            run_config.sanitize({"startup_project": "../outside.csproj"}, self.root)
        with self.assertRaises(ValueError):
            run_config.sanitize({"configuration": "Debug; evil"}, self.root)
        store = run_config.RunConfigurations(self.root / "configs.json")
        saved = store.save("ws", self.root, {"arguments": ["a"]})
        self.assertEqual(store.get("ws", self.root)["arguments"], ["a"])
        self.assertEqual(saved["configuration"], "Debug")

    def test_python_structured_runner_reports_states_and_locations(self):
        write(self.root / "calc.py", "def add(a, b):\n    return a + b\n")
        write(self.root / "tests/test_calc.py", "import unittest\nfrom calc import add\n\nclass CalcTests(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n    def test_wrong(self):\n        self.assertEqual(add(1, 2), 4)\n    @unittest.skip('later')\n    def test_skip(self):\n        pass\n")
        report = self.root / "report.json"
        runner = ROOT / "olive" / "studio_tooling" / "python_tests.py"
        completed = subprocess.run([sys.executable, str(runner), str(self.root), "--json", str(report), "--start", "tests"], capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 1)
        parsed = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual({k: parsed["summary"][k] for k in ("total", "passed", "failed", "skipped")}, {"total": 3, "passed": 1, "failed": 1, "skipped": 1})
        failed = next(r for r in parsed["results"] if r["state"] == "failed")
        self.assertTrue(failed["file"].endswith("test_calc.py") and failed["line"] == 7)
        self.assertIn("4 != 3", failed["message"].replace("3 != 4", "4 != 3"))
        listing = subprocess.run([sys.executable, str(runner), str(self.root), "--json", str(report), "--start", "tests", "--list"], capture_output=True, text=True, timeout=60)
        self.assertEqual(listing.returncode, 0)
        self.assertEqual(len(json.loads(report.read_text(encoding="utf-8"))["tests"]), 3)


class WebInspectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_owned_local_origins_are_reachable(self):
        class Session:
            local_url = None
        with self.assertRaises(ValueError):
            await web.inspect(Session(), "GET", "/", {}, "")
        Session.local_url = "http://example.com:80/"
        with self.assertRaises(ValueError):
            await web.inspect(Session(), "GET", "/", {}, "")
        Session.local_url = "http://127.0.0.1:1/"
        result = await web.inspect(Session(), "GET", "/health", {}, "", timeout=2)
        self.assertFalse(result["ok"])
        self.assertIn("Error", result["error"])
        with self.assertRaises(ValueError):
            await web.inspect(Session(), "TRACE", "/", {}, "")
        with self.assertRaises(ValueError):
            await web.inspect(Session(), "GET", "relative", {}, "")


@unittest.skipUnless(HAVE_WINPTY, "pywinpty is not installed")
class TerminalTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_receives_input_resizes_and_cleans_up(self):
        from olive.studio_tooling.pty import TerminalServices
        events = []
        services = TerminalServices(lambda topic, value: events.append((topic, value)))
        root = tempfile.mkdtemp(prefix="olive-pty-")
        try:
            session = services.create("ws", root, "cmd", {k: v for k, v in os.environ.items()}, "Probe")
            self.assertEqual(session.state, "running")
            await asyncio.sleep(1.0)
            services.terminal_write = None
            session.write("set /p NAME=Your name? \r\n")
            await asyncio.sleep(0.4)
            session.write("olive\r\n")
            await asyncio.sleep(0.4)
            session.write("echo Hello %NAME%\r\n")
            await asyncio.sleep(0.8)
            session.resize(120, 40)
            session.write("mode con | findstr Columns\r\n")
            await asyncio.sleep(0.8)
            text = "".join(value["data"] for topic, value in events if topic == "terminal.data")
            self.assertIn("Hello olive", text)
            self.assertIn("120", text)
            self.assertLessEqual(max(len(value["data"]) for topic, value in events if topic == "terminal.data"), 16 * 1024)
            services.close(session.id)
            self.assertEqual(session.state, "closed")
            self.assertNotIn(session.id, services.sessions)
        finally:
            shutil.rmtree(root, ignore_errors=True)


def _dotnet_solution(root: Path):
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE="true")
    def run(*args):
        completed = subprocess.run(["dotnet", *args], cwd=str(root), capture_output=True, text=True, timeout=300, env=env)
        if completed.returncode != 0:
            raise RuntimeError(completed.stdout + completed.stderr)
    run("new", "sln", "-n", "Fixture")
    run("new", "classlib", "-n", "Fixture.Core", "-o", "Fixture.Core")
    run("new", "console", "-n", "Fixture.App", "-o", "Fixture.App")
    run("sln", "add", "Fixture.Core", "Fixture.App")
    run("add", "Fixture.App", "reference", "Fixture.Core")
    write(root / "Fixture.Core" / "Class1.cs", "namespace Fixture.Core;\n\npublic static class Calculator\n{\n    public static int Add(int a, int b) => a + b;\n}\n")
    write(root / "Fixture.App" / "Program.cs", "using Fixture.Core;\n\nvar total = Calculator.Add(1, 2);\nvar name = \"olive\";\nConsole.WriteLine($\"{name}: {total}\");\n")
    return env


@unittest.skipUnless(HAVE_DOTNET and HAVE_OMNISHARP, "dotnet SDK and OmniSharp are required")
class LanguageServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsaved_buffers_drive_completion_definition_and_diagnostics(self):
        from olive.studio_tooling.lsp import LanguageServices, uri_to_path, path_to_uri
        root = Path(tempfile.mkdtemp(prefix="olive-lsp-"))
        try:
            env = _dotnet_solution(root)
            events = []
            services = LanguageServices(lambda topic, value: events.append((topic, value)))
            session = await services.ensure("ws", str(root), "csharp", env)
            self.assertEqual(session.state, "ready")
            program = root / "Fixture.App" / "Program.cs"
            core = root / "Fixture.Core" / "Class1.cs"
            core_text = core.read_text(encoding="utf-8").replace("Add(int a, int b) => a + b;", "Add(int a, int b) => a + b;\n    public static int Twice(int a) => a * 2;")
            await session.open(str(core), core_text, "csharp")
            await session.open(str(program), program.read_text(encoding="utf-8"), "csharp")
            await asyncio.sleep(4)
            await session._reassert_buffers()
            # Unsaved member 'Twice' exists only in the editor buffer.
            text = program.read_text(encoding="utf-8") + "var t = Calculator.Tw"
            version = await session.change(str(program), text)
            self.assertGreaterEqual(version, 2)
            line = text.count("\n")
            character = len(text.rsplit("\n", 1)[-1])
            completion = None
            for _ in range(10):
                completion = await session.feature("completion", str(program), {"position": {"line": line, "character": character}})
                if any(item["label"] == "Twice" for item in completion["items"]):
                    break
                await asyncio.sleep(1)
            self.assertTrue(any(item["label"] == "Twice" for item in completion["items"]), [i["label"] for i in completion["items"][:10]])
            hover = await session.feature("hover", str(program), {"position": {"line": 2, "character": 24}})
            self.assertIn("Add", json.dumps(hover))
            definition = await session.feature("definition", str(program), {"position": {"line": 2, "character": 24}})
            self.assertEqual(Path(definition[0]["path"]).name, "Class1.cs")
            references = await session.feature("references", str(core), {"position": {"line": 4, "character": 23}})
            self.assertGreaterEqual(len(references), 2)
            symbols = await session.feature("workspaceSymbol", str(core), {"query": "Twice"})
            self.assertTrue(any(s["name"].startswith("Twice") for s in symbols))
            # A deliberate type error appears, then disappears once corrected.
            await session.change(str(program), text.rsplit("\n", 1)[0] + "\nint broken = \"oops\";\n")
            found = False
            for _ in range(30):
                await asyncio.sleep(1)
                items = session.diagnostics.get(str(program.resolve()), [])
                if any(item["code"] == "CS0029" for item in items):
                    found = True
                    break
            self.assertTrue(found, session.diagnostics)
            await session.change(str(program), program.read_text(encoding="utf-8"))
            for _ in range(30):
                await asyncio.sleep(1)
                items = session.diagnostics.get(str(program.resolve()), [])
                if not any(item["severity"] == 1 for item in items):
                    break
            self.assertFalse(any(item["severity"] == 1 for item in session.diagnostics.get(str(program.resolve()), [])))
            rename = await session.feature("rename", str(core), {"position": {"line": 4, "character": 23}, "newName": "Sum"})
            self.assertGreaterEqual(rename["total"], 2)
            self.assertEqual({Path(f["path"]).name for f in rename["files"]}, {"Class1.cs", "Program.cs"})
            self.assertEqual(uri_to_path(path_to_uri(program)), str(program.resolve()))
            signature = await session.feature("signatureHelp", str(program), {"position": {"line": 2, "character": 27}})
            self.assertIn("Add", json.dumps(signature))
            self.assertIn("int a", json.dumps(signature))
            await session.change(str(core), "namespace Fixture.Core; public static class Calculator{public static int Add(int a,int b)=>a+b;}\n")
            formatting = await session.feature("formatting", str(core), {})
            self.assertTrue(formatting, "The compact fixture should produce real formatting edits")
            self.assertTrue(all("range" in edit and "newText" in edit for edit in formatting))
            await session.change(str(program), "var builder = new StringBuilder();\n")
            for _ in range(30):
                await asyncio.sleep(.2)
                missing = [item for item in session.diagnostics.get(str(program.resolve()), []) if item['code'] == 'CS0246']
                if missing:
                    break
            self.assertTrue(missing, session.diagnostics)
            actions = await session.feature("codeAction", str(program), {"range": missing[0]['range'], "diagnostics": missing})
            self.assertTrue(any('System.Text' in action['title'] for action in actions), actions)
            await services.stop_all()
            self.assertEqual(session.state, "stopped")
        finally:
            shutil.rmtree(root, ignore_errors=True)


@unittest.skipUnless(HAVE_DOTNET and HAVE_NETCOREDBG, "dotnet SDK and netcoredbg are required")
class DotnetDebuggerTests(unittest.IsolatedAsyncioTestCase):
    async def test_breakpoint_locals_step_continue_and_stale_generation(self):
        from olive.studio_tooling.dap import DebugServices, dotnet_launch
        root = Path(tempfile.mkdtemp(prefix="olive-dap-"))
        try:
            env = _dotnet_solution(root)
            completed = subprocess.run(["dotnet", "build", "Fixture.App", "-c", "Debug", "--nologo"], cwd=str(root), capture_output=True, text=True, timeout=300, env=env)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            program = next((root / "Fixture.App" / "bin" / "Debug").rglob("Fixture.App.dll"))
            events = []
            services = DebugServices(lambda topic, value: events.append((topic, value)))
            services.remember_breakpoints("ws", str(root / "Fixture.App" / "Program.cs"), [{"line": 4}])
            session = await services.launch("ws", str(root), "coreclr", dotnet_launch(str(program), str(root / "Fixture.App"), [], env), env)
            for _ in range(60):
                if session.suspended:
                    break
                await asyncio.sleep(0.5)
            self.assertTrue(session.suspended, [e for e in events if e[0] == "dap.event"][-5:])
            breakpoints = session.breakpoints[str((root / "Fixture.App" / "Program.cs").resolve())]
            self.assertTrue(breakpoints[0]["verified"])
            threads = await session.forward("threads", {})
            thread = threads["threads"][0]["id"]
            stack = await session.forward("stackTrace", {"threadId": thread}, session.generation)
            self.assertEqual(stack["stackFrames"][0]["line"], 4)
            scopes = await session.forward("scopes", {"frameId": stack["stackFrames"][0]["id"]}, session.generation)
            variables = await session.forward("variables", {"variablesReference": scopes["scopes"][0]["variablesReference"]}, session.generation)
            values = {v["name"]: v["value"] for v in variables["variables"]}
            self.assertEqual(values["total"], "3")
            self.assertEqual((await session.forward("evaluate", {"expression": "total + 1", "frameId": stack["stackFrames"][0]["id"], "context": "watch"}, session.generation))["result"], "4")
            stale = session.generation
            await session.forward("next", {"threadId": thread})
            for _ in range(40):
                if session.suspended and session.generation > stale:
                    break
                await asyncio.sleep(0.25)
            with self.assertRaises(ValueError):
                await session.forward("variables", {"variablesReference": scopes["scopes"][0]["variablesReference"]}, stale)
            stack = await session.forward("stackTrace", {"threadId": thread}, session.generation)
            self.assertEqual(stack["stackFrames"][0]["line"], 5)
            await session.forward("continue", {"threadId": thread})
            for _ in range(60):
                if session.state in ("terminated", "stopped"):
                    break
                await asyncio.sleep(0.5)
            self.assertIn(session.state, ("terminated", "stopped"))
            self.assertTrue(any("olive: 3" in o["output"] for o in session.output))
            await services.stop_all()
            self.assertFalse(session.transport.alive)
        finally:
            shutil.rmtree(root, ignore_errors=True)


@unittest.skipUnless(HAVE_DEBUGPY, "debugpy is not installed")
class PythonDebuggerTests(unittest.IsolatedAsyncioTestCase):
    async def test_python_breakpoint_and_locals(self):
        from olive.studio_tooling.dap import DebugServices, python_launch
        root = Path(tempfile.mkdtemp(prefix="olive-pydap-"))
        try:
            write(root / "main.py", "def total(a, b):\n    result = a + b\n    return result\n\nvalue = total(2, 3)\nprint('value', value)\n")
            services = DebugServices(lambda topic, value: None)
            services.remember_breakpoints("ws", str(root / "main.py"), [{"line": 3}])
            env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT", "COMSPEC"}}
            session = await services.launch("ws", str(root), "python", python_launch(str(root / "main.py"), str(root), [], env, sys.executable), env)
            for _ in range(60):
                if session.suspended:
                    break
                await asyncio.sleep(0.5)
            self.assertTrue(session.suspended)
            thread = (await session.forward("threads", {}))["threads"][0]["id"]
            stack = await session.forward("stackTrace", {"threadId": thread}, session.generation)
            self.assertEqual(stack["stackFrames"][0]["line"], 3)
            scopes = await session.forward("scopes", {"frameId": stack["stackFrames"][0]["id"]}, session.generation)
            variables = await session.forward("variables", {"variablesReference": scopes["scopes"][0]["variablesReference"]}, session.generation)
            self.assertEqual({v["name"]: v["value"] for v in variables["variables"]}["result"], "5")
            await session.forward("continue", {"threadId": thread})
            for _ in range(60):
                if session.state in ("terminated", "stopped"):
                    break
                await asyncio.sleep(0.5)
            self.assertIn("value 5", "".join(o["output"] for o in session.output if o["category"] == "stdout"))
            await services.stop_all()
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_WINPTY, "pywinpty is not installed")
class ControllerPolicyTests(unittest.IsolatedAsyncioTestCase):
    """Tooling starts pass the permission engine: Deny blocks, Ask is satisfied by the direct UI action and audited."""

    async def asyncSetUp(self):
        from olive.application.service_container import ServiceContainer
        from olive.agent.confirmation_service import ConfirmationResponse
        from olive.workspace import Workspace
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.events = []

        async def confirm(request):
            return ConfirmationResponse(True)
        self.s = ServiceContainer(lambda topic, value: self.events.append((topic, value)), confirm, root / "data", migrate=False)
        (root / "ws").mkdir()
        self.workspace = Workspace("Fixture", str(root / "ws"), trust_level="approved")
        self.s.workspace_repo.save(self.workspace)

    async def asyncTearDown(self):
        await self.s.shutdown()
        self.temp.cleanup()

    async def test_terminal_open_respects_deny_and_records_direct_action(self):
        from olive.studio_tooling.errors import StudioToolingError
        policies = self.s.permissions.policies()
        policies["permissions"]["terminal.execute"] = "deny"
        self.s.permissions.save(policies["permissions"], policies["scopes"])
        with self.assertRaises(StudioToolingError):
            await self.s.studio_tooling.terminal_open(self.workspace.id, "cmd")
        policies["permissions"]["terminal.execute"] = "ask"
        self.s.permissions.save(policies["permissions"], policies["scopes"])
        status = await self.s.studio_tooling.terminal_open(self.workspace.id, "cmd")
        self.assertEqual((status["state"], status["trust"], status["shell"]), ("running", "native", "cmd"))
        tasks = [task for task in self.s.agent_task_repo.load_all().values() if "terminal" in task.user_request.lower()]
        self.assertTrue(tasks and tasks[-1].state == "completed")
        self.s.studio_tooling.terminal_close(status["session_id"])
        with self.assertRaises(PermissionError):
            await self.s.studio_tooling.terminal_open("not-a-workspace", "cmd")
        from olive.bridge.tooling_routes import call
        with self.assertRaises(StudioToolingError):
            await call(self.s, "terminal.open", {"workspace_id": "not-a-workspace", "shell": "cmd"})
