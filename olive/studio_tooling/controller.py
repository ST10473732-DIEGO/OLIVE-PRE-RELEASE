"""Studio tooling controller: permission-gated entry points for real IDE services.

Every session start (language server, build/test job, debug session, terminal,
scaffold, local request) is a registered tool executed through the agent
executor so the permission engine, one-use direct-action consent and the audit
trail apply. Long-lived sessions are then addressed by id; their per-message
traffic does not re-enter the policy path, and their lifetime is bounded to
the runtime (everything is stopped at shutdown).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import time
import uuid

from ..agent.tool_result import ToolResult
from ..agent.tool_schema import ToolDefinition
from ..services.run_service import ExecutionPolicy, RunService
from ..services.workspace_service import require_approved_workspace
from . import dotnet, projects, web
from .errors import StudioToolingError
from .dap import DebugServices, dotnet_launch, python_launch
from .lsp import LanguageServices
from .pty import TerminalServices
from .run_config import RunConfigurations
from .toolchain import PINNED, dotnet_info, inventory, python_executable

LANGUAGE_FOR_SUFFIX = {".cs": "csharp", ".py": "python"}
JOB_OUTPUT_LIMIT = 400_000


class _Tool:
    """Tool registry adapter: validates the boundary; the controller does the work."""

    def __init__(self, definition: ToolDefinition, handler):
        self.definition = definition
        self.handler = handler

    async def execute(self, arguments, context):
        try:
            data = await self.handler(arguments, context)
        except Exception as error:  # Reported to the user, not swallowed.
            return ToolResult.failure(f"{type(error).__name__}: {error}"[:600], type(error).__name__)
        # Nest under one key: the executor merges its own task state into the outcome.
        return ToolResult(True, self.definition.description, {"data": data})


class StudioToolingController:
    def __init__(self, services):
        self.s = services
        self.language = LanguageServices(self._publish)
        self.debug = DebugServices(self._publish)
        self.terminals = TerminalServices(self._publish)
        self.s.run_service.terminals = self.terminals
        self.run_configs = RunConfigurations(Path(services.data_dir) / "studio-run-configs.json")
        self.jobs: dict[str, dict] = {}
        self.web_history: dict[str, list[dict]] = {}
        self._dotnet_info_cache: dict | None = None
        self._toolchains_cache: dict | None = None
        from .designer import DesignerController
        self.designer=DesignerController(services)
        self._register()

    def _publish(self, topic, value):
        self.s.publish(topic, value)

    def _register(self):
        register = self.s.tool_registry.register
        register(_Tool(ToolDefinition("studio.language_service", "Start code intelligence for an approved workspace", "studio",
                                      {"type": "object", "required": ["workspace", "language"]}, risk_level="medium",
                                      required_permissions=("filesystem.read",), confirmation_required=False, timeout_seconds=180),
                       self._tool_language))
        register(_Tool(ToolDefinition("studio.build", "Build, rebuild, clean or restore a .NET target", "studio",
                                      {"type": "object", "required": ["workspace", "mode"]}, risk_level="high",
                                      required_permissions=("filesystem.read", "terminal.execute"), confirmation_required=True, timeout_seconds=1200),
                       self._tool_build))
        register(_Tool(ToolDefinition("studio.test", "Discover or run tests with the installed test runner", "studio",
                                      {"type": "object", "required": ["workspace"]}, risk_level="high",
                                      required_permissions=("filesystem.read", "terminal.execute"), confirmation_required=True, timeout_seconds=1800),
                       self._tool_test))
        register(_Tool(ToolDefinition("studio.debug", "Launch the startup program under a real debugger", "studio",
                                      {"type": "object", "required": ["workspace"]}, risk_level="high",
                                      required_permissions=("filesystem.read", "terminal.execute"), confirmation_required=True, timeout_seconds=600),
                       self._tool_debug))
        register(_Tool(ToolDefinition("studio.terminal", "Open a trusted native terminal in an approved workspace", "studio",
                                      {"type": "object", "required": ["workspace", "shell"]}, risk_level="high",
                                      required_permissions=("terminal.execute",), confirmation_required=True, timeout_seconds=30),
                       self._tool_terminal))
        register(_Tool(ToolDefinition("studio.scaffold", "Create a .NET project or solution from an installed template", "studio",
                                      {"type": "object", "required": ["workspace", "kind", "name"]}, risk_level="high",
                                      required_permissions=("filesystem.write", "terminal.execute"), confirmation_required=True, timeout_seconds=600),
                       self._tool_scaffold))
        register(_Tool(ToolDefinition("studio.new_project", "Create a new project folder from an installed template", "studio",
                                      {"type": "object", "required": ["language", "template", "name", "location"]}, risk_level="high",
                                      required_permissions=("filesystem.write", "terminal.execute"), confirmation_required=True, timeout_seconds=900),
                       self._tool_new_project))
        register(_Tool(ToolDefinition("studio.launch", "Run the configured startup project without a debugger", "studio",
                                      {"type": "object", "required": ["workspace"]}, risk_level="high",
                                      required_permissions=("filesystem.read", "terminal.execute"), confirmation_required=True, timeout_seconds=60),
                       self._tool_launch))
        register(_Tool(ToolDefinition("studio.web_request", "Send one request to a project's owned local endpoint", "studio",
                                      {"type": "object", "required": ["workspace", "session_id", "method", "path"]}, risk_level="medium",
                                      required_permissions=("network.read",), confirmation_required=False, timeout_seconds=90),
                       self._tool_web_request))

    # ---- helpers -------------------------------------------------------
    def _workspace(self, workspace_id: str):
        return require_approved_workspace(self.s.workspace_repo, workspace_id)

    async def _direct(self, tool: str, arguments: dict, summary: str):
        outcome = await self.s.agent.tool(tool, arguments, summary, direct_user_action=True, retain_failure=True, return_outcome=True)
        if outcome.get("state") != "completed":
            raise StudioToolingError(str(outcome.get("summary") or "The operation could not complete"))
        return outcome.get("data") or {}

    def _environment(self, workspace, dotnet_context: bool = False) -> dict[str, str]:
        environment = ExecutionPolicy(workspace.trust_level).environment()
        if dotnet_context:
            environment = RunService.dotnet_environment(workspace.root_path, environment)
        return environment

    # Language servers are user tooling that reads per-user caches and
    # configuration; they get the policy environment plus profile locations,
    # never secret-looking variables.
    PROFILE_VARIABLES = ("USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES",
                         "PROGRAMFILES(X86)", "USERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")

    def _language_environment(self, workspace, language: str) -> dict[str, str]:
        import os
        from ..services.run_service import SECRET_NAME
        environment = self._environment(workspace, dotnet_context=language == "csharp")
        for name in self.PROFILE_VARIABLES:
            value = os.environ.get(name)
            if value and not SECRET_NAME.search(name):
                environment[name] = value
        return environment

    def _terminal_environment(self, workspace) -> dict[str, str]:
        """A native shell keeps the user's ordinary environment minus secret-looking variables."""
        import os
        from ..services.run_service import SECRET_NAME
        return {key: value for key, value in os.environ.items() if not SECRET_NAME.search(key)}

    async def _dotnet_info(self) -> dict:
        # dotnet --list-sdks/--list-runtimes/--version are slow subprocesses;
        # the installed SDK does not change within a session, so cache it.
        if self._dotnet_info_cache is None:
            self._dotnet_info_cache = await dotnet_info()
        return self._dotnet_info_cache

    async def inventory(self) -> dict:
        return {**inventory(), "dotnet": await self._dotnet_info()}

    # ---- project languages, templates and creation ----------------------
    async def toolchains(self, workspace_id: str = "", refresh: bool = False) -> dict:
        """What this machine can really create, cached between wizard renders."""
        root = ""
        if workspace_id:
            try:
                root = self._workspace(workspace_id).root_path
            except Exception:
                root = ""
        fresh = self._toolchains_cache
        if refresh or not fresh or time.time() - fresh.get("checked_at", 0) > projects.CACHE_SECONDS:
            fresh = await projects.discover(root or None)
            self._toolchains_cache = fresh
        return fresh

    def new_project_preview(self, language: str, template: str, name: str, location: str) -> dict:
        """The exact folder and operation, shown before anything is created."""
        target = projects.resolve_destination(location, name)
        return {"destination": str(target), "language": language, "template": template,
                "exists": target.exists()}

    async def _tool_new_project(self, arguments, context):
        language = str(arguments["language"])
        template = str(arguments["template"])
        name = projects.validate_name(str(arguments["name"]))
        target = projects.resolve_destination(str(arguments["location"]), name)
        def guard():
            from ..agent.permission_service import PermissionDecision
            if context.cancellation_event and context.cancellation_event.is_set():
                raise ValueError('Project creation cancelled')
            for permission in ('filesystem.write', 'terminal.execute'):
                if self.s.permissions.evaluate(permission, str(target)).decision == PermissionDecision.DENY:
                    raise PermissionError('Project creation permission denied')
        guard()
        steps: list[dict] = []
        created_here = not target.exists()
        if language == "csharp" and template == "winforms":
            import sys
            from . import winforms
            executable=projects.dotnet_executable()
            if sys.platform!='win32' or not executable or 'winforms' not in await asyncio.to_thread(projects._dotnet_template_names,executable):
                raise ValueError('The installed environment does not support the Windows Forms template')
            version=(await self._dotnet_info()).get('version','')
            framework=str(arguments.get('framework') or 'net'+version.split('.')[0]+'.0')
            guard()
            written=winforms.create(target,name,framework)
            steps.append({'command':['write OLIVE-owned Windows Forms project'],'exit_code':0,'output':'\n'.join(written)})
        elif language == "csharp":
            executable = projects.dotnet_executable()
            if not executable:
                raise FileNotFoundError("The .NET SDK was not found on this machine.")
            command = projects.dotnet_new_command(executable, template, name, target,
                                                  str(arguments.get("framework", "")))
            code, output = await asyncio.to_thread(projects._run, command, 900)
            steps.append({"command": command, "exit_code": code, "output": output[-4000:]})
            if code != 0:
                # Leave whatever the SDK wrote in place and say so; never delete
                # a directory the person chose.
                raise RuntimeError(
                    "dotnet new failed. The chosen folder was left as the SDK left it.\n" + output[-2000:])
        else:
            written = projects.write_local_template(target, language, template)
            steps.append({"command": ["write starter files"], "exit_code": 0,
                          "output": "\n".join(written)})
        if arguments.get("git"):
            guard()
            command = projects.git_init_command(target)
            code, output = await asyncio.to_thread(projects._run, command, 120)
            steps.append({"command": command, "exit_code": code, "output": output[-2000:]})
        workspace = self.s.data.create_workspace(name, str(target))
        return {"workspace": workspace, "destination": str(target), "steps": steps,
                "created_folder": created_here}

    async def new_project(self, language: str, template: str, name: str, location: str,
                          framework: str = "", interpreter: str = "", git: bool = False) -> dict:
        preview = self.new_project_preview(language, template, name, location)
        arguments = {"language": language, "template": template, "name": name, "location": location,
                     "framework": framework, "interpreter": interpreter, "git": bool(git)}
        result = await self._direct("studio.new_project", arguments,
                                    f"Create {language} project {name} in {preview['destination']}")
        if interpreter and result.get("workspace"):
            try:
                self.run_configs.save(result["workspace"]["id"], Path(result["destination"]),
                                      {**self.run_configs.get(result["workspace"]["id"], Path(result["destination"])),
                                       "interpreter": interpreter})
            except Exception:
                pass  # The project exists; a preference failure must not undo it.
        return result

    # ---- language services ---------------------------------------------
    async def _tool_language(self, arguments, context):
        workspace = self._workspace(arguments["workspace"])
        language = arguments["language"]
        session = await self.language.ensure(workspace.id, workspace.root_path, language, self._language_environment(workspace, language))
        return session.status()

    async def language_start(self, workspace_id: str, language: str) -> dict:
        workspace = self._workspace(workspace_id)
        existing = self.language.get(workspace.id, language)
        if existing and existing.state in ("starting", "ready"):
            return existing.status()
        return await self._direct("studio.language_service", {"workspace": workspace.id, "language": language},
                                  f"Start {language} code intelligence for {workspace.title}")

    async def language_stop(self, workspace_id: str, language: str = "") -> dict:
        await self.language.stop(workspace_id, language or None)
        return {"stopped": True}

    async def language_restart(self, workspace_id: str, language: str) -> dict:
        session = self.language.get(workspace_id, language)
        if session is None:
            return await self.language_start(workspace_id, language)
        await session.restart()
        return session.status()

    def language_status(self, workspace_id: str) -> dict:
        return {"sessions": self.language.status(workspace_id)}

    def _session_for(self, workspace_id: str, path: str, language: str = ""):
        language = language or LANGUAGE_FOR_SUFFIX.get(Path(path).suffix.casefold(), "")
        session = self.language.get(workspace_id, language) if language else None
        if session is None or session.state not in ("starting", "ready"):
            raise ValueError("Code intelligence is not running for this file's language")
        return session

    async def language_open(self, workspace_id: str, path: str, text: str, language_id: str = "") -> dict:
        workspace = self._workspace(workspace_id)
        resolved = workspace.resolve(path)
        session = self._session_for(workspace.id, str(resolved), language_id)
        await session.open(str(resolved), text, language_id or session.language)
        return {"version": session.documents[str(resolved)]["version"]}

    async def language_change(self, workspace_id: str, path: str, text: str) -> dict:
        workspace = self._workspace(workspace_id)
        resolved = workspace.resolve(path)
        session = self._session_for(workspace.id, str(resolved))
        return {"version": await session.change(str(resolved), text)}

    async def language_close(self, workspace_id: str, path: str) -> dict:
        workspace = self._workspace(workspace_id)
        resolved = workspace.resolve(path)
        try:
            session = self._session_for(workspace.id, str(resolved))
        except ValueError:
            return {"closed": False}
        await session.close(str(resolved))
        return {"closed": True}

    async def language_saved(self, workspace_id: str, path: str) -> dict:
        workspace = self._workspace(workspace_id)
        resolved = workspace.resolve(path)
        try:
            session = self._session_for(workspace.id, str(resolved))
        except ValueError:
            return {"notified": False}
        await session.saved(str(resolved))
        return {"notified": True}

    async def language_request(self, workspace_id: str, feature: str, path: str = "", params: dict | None = None, language: str = "") -> dict:
        workspace = self._workspace(workspace_id)
        resolved = str(workspace.resolve(path)) if path else ""
        session = self._session_for(workspace.id, resolved, language)
        result = await session.feature(feature, resolved, params or {})
        return {"result": result}

    def language_diagnostics(self, workspace_id: str) -> dict:
        items = []
        for session in self.language.sessions.values():
            if session.workspace_id == workspace_id:
                for path, diagnostics in session.diagnostics.items():
                    items.append({"path": path, "diagnostics": diagnostics})
        return {"files": items}

    # ---- project system ------------------------------------------------
    async def project_scan(self, workspace_id: str) -> dict:
        workspace = self._workspace(workspace_id)
        root = Path(workspace.root_path)
        scanned = dotnet.scan(root)
        config = self.run_configs.get(workspace.id, root)
        if not config["startup_project"] and scanned["projects"]:
            config["startup_project"] = dotnet.default_startup(scanned["projects"])
        return {**scanned, "workspace_id": workspace.id, "run_configuration": config,
                "tooling": {**inventory(root), "dotnet": await self._dotnet_info()},
                "jobs": [self._job_summary(job) for job in self.jobs.values() if job["workspace_id"] == workspace.id][-20:]}

    def config_get(self, workspace_id: str) -> dict:
        workspace = self._workspace(workspace_id)
        return self.run_configs.get(workspace.id, Path(workspace.root_path))

    def config_save(self, workspace_id: str, config: dict) -> dict:
        workspace = self._workspace(workspace_id)
        return self.run_configs.save(workspace.id, Path(workspace.root_path), config)

    def _job_summary(self, job: dict) -> dict:
        return {key: value for key, value in job.items() if key not in {"task"}}

    async def _run_job(self, workspace, kind: str, command: list[str], label: str, application_type: str, on_done) -> dict:
        job = {"id": uuid.uuid4().hex, "workspace_id": workspace.id, "kind": kind, "label": label, "command": command, "state": "running",
               "started_at": time.time(), "ended_at": None, "exit_code": None, "output": "", "session_id": None, "cancelled": False}
        self.jobs[job["id"]] = job
        for stale in [j for j in self.jobs.values() if j["workspace_id"] == workspace.id and j["state"] != "running"][:-30]:
            self.jobs.pop(stale["id"], None)
        policy = ExecutionPolicy(workspace.trust_level, 1200, False, True)
        environment = self._environment(workspace, dotnet_context=command[0] == "dotnet")
        session = await self.s.run_service.start(workspace, command, application_type, policy, environment)
        job["session_id"] = session.id
        self._publish("build.progress", self._job_summary(job))

        async def monitor():
            while session.state in ("starting", "running"):
                job["output"] = (session.stdout + session.stderr)[-JOB_OUTPUT_LIMIT:]
                self._publish("build.progress", {**self._job_summary(job), "output": job["output"][-4000:]})
                await asyncio.sleep(0.25)
            final = await self.s.run_service.wait(session.id)
            job["output"] = (final.stdout + final.stderr)[-JOB_OUTPUT_LIMIT:]
            job["exit_code"] = final.exit_code
            job["ended_at"] = time.time()
            job["state"] = "cancelled" if job["cancelled"] or final.state == "stopped" else "completed" if final.exit_code == 0 else "failed"
            try:
                extra = await on_done(job, final)
            except Exception as error:
                extra = {"error": f"{type(error).__name__}: {error}"[:400]}
            job.update(extra or {})
            self._publish("build.result", self._job_summary(job))
        job["task"] = asyncio.create_task(monitor())
        return job

    async def job_cancel(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("Unknown job")
        job["cancelled"] = True
        if job.get("session_id"):
            await self.s.run_service.stop(job["session_id"])
        return {"cancelled": True}

    def jobs_list(self, workspace_id: str) -> dict:
        return {"jobs": [self._job_summary(job) for job in self.jobs.values() if job["workspace_id"] == workspace_id]}

    async def _tool_build(self, arguments, context):
        workspace = self._workspace(arguments["workspace"])
        root = Path(workspace.root_path)
        config = self.run_configs.get(workspace.id, root)
        scanned = dotnet.scan(root)
        target = arguments.get("target") or self._build_target(scanned, config)
        if not target:
            raise ValueError("No .NET solution or project was found in this workspace")
        command = dotnet.build_command(target, config["configuration"], arguments["mode"])

        async def done(job, session):
            diagnostics = dotnet.parse_build_diagnostics(job["output"])
            self._publish("problems", {"workspace_id": workspace.id, "items": [
                {"file": self._relative(root, d["file"]), "line": d["line"], "column": d["column"], "severity": d["severity"], "message": f"{d['code']}: {d['message']}"}
                for d in diagnostics]})
            return {"diagnostics": diagnostics, "target": target}
        job = await self._run_job(workspace, arguments["mode"], command, f"{arguments['mode'].title()} {Path(target).name}", "dotnet_build", done)
        return self._job_summary(job)

    @staticmethod
    def _relative(root: Path, file: str) -> str:
        try:
            return Path(file).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return file

    @staticmethod
    def _build_target(scanned: dict, config: dict) -> str:
        if scanned["solutions"]:
            return scanned["solutions"][0]["path"]
        if config.get("startup_project"):
            return config["startup_project"]
        if scanned["projects"]:
            return scanned["projects"][0]["path"]
        return ""

    async def build(self, workspace_id: str, mode: str, target: str = "") -> dict:
        workspace = self._workspace(workspace_id)
        if mode not in {"build", "rebuild", "clean", "restore"}:
            raise ValueError("Unsupported build mode")
        arguments = {"workspace": workspace.id, "mode": mode}
        if target:
            arguments["target"] = str(workspace.resolve(target))
        return await self._direct("studio.build", arguments, f"{mode.title()} {workspace.title}")

    async def _tool_test(self, arguments, context):
        workspace = self._workspace(arguments["workspace"])
        root = Path(workspace.root_path)
        scanned = dotnet.scan(root)
        filters = [str(f)[:400] for f in arguments.get("filters") or []][:200]
        list_only = bool(arguments.get("list_only"))
        if scanned["projects"]:
            test_projects = [p for p in scanned["projects"] if p["is_test"]]
            if not test_projects:
                raise ValueError("No test project was found. Add a test project (xUnit, NUnit or MSTest) to the solution.")
            target = arguments.get("target") or (scanned["solutions"][0]["path"] if scanned["solutions"] and len(test_projects) > 1 else test_projects[0]["path"])
            testing_platform = any(p["uses_testing_platform"] for p in test_projects)
            results_directory = root / "obj" / ".olive-tests" / uuid.uuid4().hex[:8]
            results_directory.mkdir(parents=True, exist_ok=True)
            config = self.run_configs.get(workspace.id, root)
            command = dotnet.test_command(target, config["configuration"], str(results_directory), filters, testing_platform, list_only)

            async def done(job, session):
                if list_only:
                    return {"tests": [{"full_name": name, "name": name.rsplit(".", 1)[-1]} for name in dotnet.parse_list_tests(job["output"])], "runner": "vstest" if not testing_platform else "testing-platform"}
                reports = sorted(results_directory.rglob("*.trx"))
                if not reports:
                    return {"summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration_seconds": 0.0}, "results": [],
                            "error": "No TRX report was produced; the build or discovery failed. Inspect the raw log.", "runner": "vstest"}
                parsed = dotnet.parse_trx(reports[-1])
                for item in parsed["results"]:
                    if item["file"]:
                        item["relative_file"] = self._relative(root, item["file"])
                self._publish("tests.results", {"workspace_id": workspace.id, "job_id": job["id"], **parsed})
                return {**parsed, "runner": "testing-platform" if testing_platform else "vstest"}
            job = await self._run_job(workspace, "test-list" if list_only else "test", command,
                                      "Discover tests" if list_only else ("Run selected tests" if filters else "Run tests"), "dotnet_test", done)
            return self._job_summary(job)
        python = self.run_configs.get(workspace.id, root)["interpreter"] or python_executable(root)
        report = root / "obj" / ".olive-tests" / (uuid.uuid4().hex[:8] + ".json")
        report.parent.mkdir(parents=True, exist_ok=True)
        runner = str(Path(__file__).with_name("python_tests.py"))
        start = "tests" if (root / "tests").is_dir() else "."
        command = [python, runner, str(root), "--json", str(report), "--start", start] + (["--list"] if list_only else []) + filters

        async def done(job, session):
            import json
            try:
                parsed = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {"summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration_seconds": 0.0}, "results": [],
                        "error": "The Python test runner produced no report. Inspect the raw log.", "runner": "unittest"}
            if list_only:
                return {"tests": parsed.get("tests", []), "error": parsed.get("error", ""), "runner": "unittest"}
            for item in parsed.get("results", []):
                if item.get("file"):
                    item["relative_file"] = self._relative(root, item["file"])
            self._publish("tests.results", {"workspace_id": workspace.id, "job_id": job["id"], **parsed})
            return {**parsed, "runner": "unittest"}
        job = await self._run_job(workspace, "test-list" if list_only else "test", command,
                                  "Discover tests" if list_only else "Run tests", "python_test", done)
        return self._job_summary(job)

    async def test(self, workspace_id: str, filters: list[str] | None = None, list_only: bool = False, target: str = "") -> dict:
        workspace = self._workspace(workspace_id)
        arguments = {"workspace": workspace.id, "filters": list(filters or []), "list_only": bool(list_only)}
        if target:
            arguments["target"] = str(workspace.resolve(target))
        return await self._direct("studio.test", arguments, f"{'Discover' if list_only else 'Run'} tests in {workspace.title}")

    # ---- debugging -----------------------------------------------------
    async def _tool_debug(self, arguments, context):
        workspace = self._workspace(arguments["workspace"])
        root = Path(workspace.root_path)
        config = self.run_configs.get(workspace.id, root)
        scanned = dotnet.scan(root)
        environment = self._environment(workspace, dotnet_context=bool(scanned["projects"]))
        if scanned["projects"]:
            project = config["startup_project"] or dotnet.default_startup(scanned["projects"])
            if not project:
                raise ValueError("Choose a startup project first")
            build = await self._run_job(workspace, "build", dotnet.build_command(project, config["configuration"], "build"),
                                        f"Build {Path(project).name} for debugging", "dotnet_build", lambda job, s: self._build_done(workspace, job))
            await build["task"]
            if build["state"] != "completed":
                raise RuntimeError("The build failed; fix the errors in Problems before debugging")
            session = await self.s.run_service.start(workspace, dotnet.target_path_command(project, config["configuration"]), "dotnet_build",
                                                     ExecutionPolicy(workspace.trust_level, 120, False, True), environment)
            final = await self.s.run_service.wait(session.id)
            program = (final.stdout or "").strip().splitlines()[-1].strip() if (final.stdout or "").strip() else ""
            if not program or not Path(program).is_file():
                raise RuntimeError("The build output could not be located (TargetPath). Inspect the build log.")
            cwd = config["working_directory"] or str(Path(project).parent)
            launch = dotnet_launch(program, cwd, config["arguments"], {**environment, **config["environment"]}, config["stop_at_entry"])
            adapter = "coreclr"
        else:
            program = config["program"] or (str(root / "main.py") if (root / "main.py").is_file() else "")
            if not program:
                raise ValueError("Choose a Python program to debug (main.py or the run configuration's program)")
            python = config["interpreter"] or python_executable(root)
            cwd = config["working_directory"] or str(root)
            launch = python_launch(program, cwd, config["arguments"], {**environment, **config["environment"]}, python, config["stop_at_entry"])
            launch["python"] = python
            adapter = "python"
        session = await self.debug.launch(workspace.id, str(root), adapter, launch, environment)
        return session.status()

    # ---- running the startup project -----------------------------------
    def _launch_plan(self, workspace) -> tuple[list[str], str, str, dict[str, str]]:
        """Command, application type, working directory and environment for the run configuration."""
        root = Path(workspace.root_path)
        config = self.run_configs.get(workspace.id, root)
        scanned = dotnet.scan(root)
        if scanned["projects"]:
            project = config["startup_project"] or dotnet.default_startup(scanned["projects"])
            if not project:
                raise ValueError("Choose a startup project first")
            record = next((p for p in scanned["projects"] if p["path"] == project), None)
            command = dotnet.run_command(project, config["configuration"], config["arguments"], config["launch_profile"])
            kind = "aspnet_web" if record and record["is_web"] else "dotnet_application"
            return command, kind, config["working_directory"] or str(Path(project).parent), self._environment(workspace, dotnet_context=True)
        program = config["program"] or (str(root / "main.py") if (root / "main.py").is_file() else "")
        if not program:
            raise ValueError("Choose a Python program to run (main.py or the run configuration's program)")
        python = config["interpreter"] or python_executable(root)
        text = Path(program).read_text(encoding="utf-8", errors="ignore")[:100_000] if Path(program).is_file() else ""
        kind = "python_gui" if "tkinter" in text or "flet" in text else "python_console"
        return [python, program, *config["arguments"]], kind, config["working_directory"] or str(root), self._environment(workspace)

    async def _tool_launch(self, arguments, context):
        workspace = self._workspace(arguments["workspace"])
        if any(s.workspace_id == workspace.id and s.state in {"starting", "running"} for s in self.s.run_service.sessions.values()):
            raise ValueError("This workspace already has a running program")
        command, kind, cwd, environment = self._launch_plan(workspace)
        config = self.run_configs.get(workspace.id, Path(workspace.root_path))
        policy = ExecutionPolicy(workspace.trust_level, 3600, False, True)
        session = await self.s.run_service.start(workspace, command, kind, policy, {**environment, **config["environment"]}, cwd=cwd,
                                                 interactive=kind in {'python_console','dotnet_application'}, configured_environment=config['environment'])
        task = asyncio.create_task(self.s.studio.observe(session.id))
        self.s.studio.monitors.add(task)
        task.add_done_callback(self.s.studio.monitors.discard)
        return {"session_id": session.id, "process_id": session.process_id, "application_type": kind, "command": command}

    async def run(self, workspace_id: str) -> dict:
        workspace = self._workspace(workspace_id)
        return await self._direct("studio.launch", {"workspace": workspace.id}, f"Run {workspace.title}")

    async def _build_done(self, workspace, job):
        diagnostics = dotnet.parse_build_diagnostics(job["output"])
        self._publish("problems", {"workspace_id": workspace.id, "items": [
            {"file": self._relative(Path(workspace.root_path), d["file"]), "line": d["line"], "column": d["column"], "severity": d["severity"],
             "message": f"{d['code']}: {d['message']}"} for d in diagnostics]})
        return {"diagnostics": diagnostics}

    async def debug_launch(self, workspace_id: str) -> dict:
        workspace = self._workspace(workspace_id)
        return await self._direct("studio.debug", {"workspace": workspace.id}, f"Debug {workspace.title}")

    async def debug_stop(self, session_id: str) -> dict:
        await self.debug.stop(session_id)
        return {"stopped": True}

    async def debug_request(self, session_id: str, command: str, arguments: dict | None = None, generation: int | None = None) -> dict:
        session = self.debug.sessions.get(session_id)
        if session is None:
            raise ValueError("Unknown debug session")
        return {"body": await session.forward(command, arguments or {}, generation)}

    async def debug_breakpoints(self, workspace_id: str, path: str, lines: list[dict]) -> dict:
        workspace = self._workspace(workspace_id)
        resolved = str(workspace.resolve(path))
        self.debug.remember_breakpoints(workspace.id, resolved, lines)
        session = self.debug.active(workspace.id)
        if session:
            return {"breakpoints": await session.set_breakpoints(resolved, lines)}
        return {"breakpoints": [{"line": int(item["line"]), "requested_line": int(item["line"]), "verified": False,
                                 "message": "Set when the debugger starts", "condition": str(item.get("condition", ""))} for item in lines[:200]]}

    def debug_status(self, workspace_id: str) -> dict:
        sessions = [s.status() for s in self.debug.sessions.values() if s.workspace_id == workspace_id]
        active = self.debug.active(workspace_id)
        return {"sessions": sessions[-5:], "active": active.status() if active else None,
                "output": active.output[-400:] if active else [],
                "breakpoints": {path: items for path, items in self.debug.workspace_breakpoints.get(workspace_id, {}).items()}}

    # ---- terminals -----------------------------------------------------
    async def _tool_terminal(self, arguments, context):
        workspace = self._workspace(arguments["workspace"])
        session = self.terminals.create(workspace.id, workspace.root_path, arguments["shell"], self._terminal_environment(workspace))
        return session.status()

    async def terminal_open(self, workspace_id: str, shell: str = "powershell") -> dict:
        workspace = self._workspace(workspace_id)
        return await self._direct("studio.terminal", {"workspace": workspace.id, "shell": shell}, f"Open a {shell} terminal in {workspace.title}")

    def terminal_write(self, session_id: str, data: str) -> dict:
        self.terminals.require(session_id).write(data)
        return {"written": len(data)}

    def terminal_resize(self, session_id: str, columns: int, rows: int) -> dict:
        self.terminals.require(session_id).resize(columns, rows)
        return {"columns": columns, "rows": rows}

    def terminal_close(self, session_id: str) -> dict:
        self.terminals.close(session_id)
        return {"closed": True}

    def terminal_list(self, workspace_id: str) -> dict:
        return {"sessions": self.terminals.list(workspace_id)}

    # ---- scaffolding ---------------------------------------------------
    TEMPLATES = {"console": "console", "webapi": "webapi", "classlib": "classlib", "xunit": "xunit", "mstest": "mstest", "nunit": "nunit", "sln": "sln"}

    async def _tool_scaffold(self, arguments, context):
        workspace = self._workspace(arguments["workspace"])
        root = Path(workspace.root_path)
        kind, name = arguments["kind"], arguments["name"]
        if kind not in self.TEMPLATES:
            raise ValueError("Unsupported template")
        if not name.replace("_", "").replace("-", "").replace(".", "").isalnum() or len(name) > 80:
            raise ValueError("Invalid project name")
        directory = workspace.resolve(arguments.get("directory") or ".")
        if not directory.is_relative_to(root):
            raise ValueError("Projects must be created inside the workspace")
        environment = self._environment(workspace, dotnet_context=True)
        policy = ExecutionPolicy(workspace.trust_level, 600, True, True)
        steps = []
        if kind == "sln":
            command = ["dotnet", "new", "sln", "-n", name, "-o", str(directory)]
        else:
            command = ["dotnet", "new", self.TEMPLATES[kind], "-n", name, "-o", str(directory / name)]
        session = await self.s.run_service.start(workspace, command, "dotnet_build", policy, environment)
        final = await self.s.run_service.wait(session.id)
        steps.append({"command": command, "exit_code": final.exit_code, "output": (final.stdout + final.stderr)[-4000:]})
        if final.exit_code != 0:
            raise RuntimeError("dotnet new failed:\n" + (final.stdout + final.stderr)[-2000:])
        solution = arguments.get("solution")
        if solution and kind != "sln":
            solution_path = workspace.resolve(solution)
            command = ["dotnet", "sln", str(solution_path), "add", str(directory / name)]
            session = await self.s.run_service.start(workspace, command, "dotnet_build", policy, environment)
            final = await self.s.run_service.wait(session.id)
            steps.append({"command": command, "exit_code": final.exit_code, "output": (final.stdout + final.stderr)[-4000:]})
            if final.exit_code != 0:
                raise RuntimeError("Adding the project to the solution failed:\n" + (final.stdout + final.stderr)[-2000:])
        for reference in arguments.get("references") or []:
            target = workspace.resolve(reference)
            command = ["dotnet", "add", str(directory / name), "reference", str(target)]
            session = await self.s.run_service.start(workspace, command, "dotnet_build", policy, environment)
            final = await self.s.run_service.wait(session.id)
            steps.append({"command": command, "exit_code": final.exit_code, "output": (final.stdout + final.stderr)[-4000:]})
            if final.exit_code != 0:
                raise RuntimeError("Adding the project reference failed:\n" + (final.stdout + final.stderr)[-2000:])
        return {"created": str(directory / name) if kind != "sln" else str(directory), "steps": steps}

    async def scaffold(self, workspace_id: str, kind: str, name: str, directory: str = "", solution: str = "", references: list[str] | None = None) -> dict:
        workspace = self._workspace(workspace_id)
        arguments = {"workspace": workspace.id, "kind": kind, "name": name, "directory": directory, "solution": solution, "references": list(references or [])}
        return await self._direct("studio.scaffold", arguments, f"Create {kind} project {name} in {workspace.title}")

    async def add_existing(self, workspace_id: str, solution: str, project: str) -> dict:
        workspace = self._workspace(workspace_id)
        solution_path, project_path = workspace.resolve(solution), workspace.resolve(project)
        if not solution_path.is_file() or not project_path.is_file():
            raise ValueError("Solution and project must exist inside the workspace")
        command = ["dotnet", "sln", str(solution_path), "add", str(project_path)]

        async def done(job, session):
            return {}
        job = await self._run_job(workspace, "sln-add", command, f"Add {project_path.name} to {solution_path.name}", "dotnet_build", done)
        await job["task"]
        if job["state"] != "completed":
            raise RuntimeError(job["output"][-2000:] or "dotnet sln add failed")
        return self._job_summary(job)

    # ---- local request inspector ----------------------------------------
    async def _tool_web_request(self, arguments, context):
        workspace = self._workspace(arguments["workspace"])
        session = self.s.run_service.sessions.get(arguments["session_id"])
        if session is None or session.workspace_id != workspace.id:
            raise ValueError("The run session does not belong to this workspace")
        from ..services.local_preview import authorize
        await asyncio.to_thread(authorize, self.s, session.id)
        result = await web.inspect(session, arguments["method"], arguments["path"], arguments.get("headers") or {}, arguments.get("body") or "")
        record = {"id": uuid.uuid4().hex[:12], "time": time.time(), "session_id": session.id, **web.summarize(result)}
        history = self.web_history.setdefault(workspace.id, [])
        history.append(record)
        del history[:-50]
        return record

    async def web_request(self, workspace_id: str, session_id: str, method: str, path: str, headers: dict | None = None, body: str = "") -> dict:
        workspace = self._workspace(workspace_id)
        return await self._direct("studio.web_request", {"workspace": workspace.id, "session_id": session_id, "method": method, "path": path,
                                                         "headers": dict(headers or {}), "body": body},
                                  f"{method} {path} on the local {workspace.title} endpoint")

    def web_history(self, workspace_id: str) -> dict:
        return {"requests": list(self.web_history.get(workspace_id, []))}

    # ---- lifecycle -----------------------------------------------------
    async def shutdown(self):
        await self.debug.stop_all()
        await self.language.stop_all()
        self.terminals.close_all()
        for job in self.jobs.values():
            task = job.get("task")
            if task and not task.done():
                task.cancel()
