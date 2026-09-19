"""Live local coding acceptance. Approvals only cover a disposable Python fixture.

Generated source is parsed and constrained before approval; no broad approval
loop, external messages, arbitrary terminals or user workspaces are permitted.
"""
import ast
import asyncio
import json
import re
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


def check_source(source):
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [v.name for v in node.names] if isinstance(node, ast.Import) else [node.module]
            if not all(m in {"unittest", "math", "operator", "sys", "main"} for m in modules):
                raise AssertionError(f"Unapproved fixture imports: {modules}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "open", "compile", "__import__", "getattr", "setattr", "delattr", "breakpoint"}:
                raise AssertionError("Unapproved fixture call")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise AssertionError("Unapproved fixture introspection")


async def main():
    root = Path(tempfile.mkdtemp(prefix="olive-project-live-")).resolve()
    reviews = []
    async def review(request):
        args = request.arguments
        allowed = {"studio.new_project", "studio.tree", "studio.open", "studio.save", "code.create_file", "workspace.run_validation", "studio.run"}
        assert request.tool_name in allowed, request.tool_name
        target = Path(args.get("workspace") or args.get("location") or args.get("path")).resolve()
        assert target.is_relative_to(root), target
        if request.tool_name == "studio.new_project":
            assert args["language"] == "python" and args["template"] == "console" and target == root
        if args.get("text"):
            assert args["path"].endswith(".py")
            check_source(args["text"])
        reviews.append({"tool": request.tool_name, "arguments": args})
        print("Reviewed fixture operation:", request.tool_name, flush=True)
        return ConfirmationResponse(True)
    services = ServiceContainer(lambda *args: None, review, root, migrate=False)
    try:
        await services.initialize()
        result = await services.interaction.submit("Create a calculator project in Studio and run it.")
        print("ANSWER", result["messages"][-1]["content"], flush=True)
        trace = services.interaction.inspect(services.current_chat_id)
        workspaces = services.workspace_repo.load_all()
        assert len(workspaces) == 1, trace
        workspace = next(iter(workspaces.values()))
        assert list(services.run_service.sessions.values()), "No actual process was created"
        app_runs = [r for r in services.run_service.sessions.values() if r.accepts_input]
        assert len(app_runs) == 1, "No interactive calculator run"
        await services.studio.input(workspace.id, app_runs[0].id, "2 + 3\n8 / 2\n9 / 0\nquit\n")
        final = await asyncio.wait_for(services.run_service.wait(app_runs[0].id), 15)
        assert final.state == "completed", final.to_dict()
        assert re.search(r"(?:Result:|=)\s*5(?:\.0)?\b", final.stdout), final.stdout
        assert re.search(r"(?:Result:|=)\s*4(?:\.0)?\b", final.stdout), final.stdout
        before = workspace.id
        unrelated = root / "unrelated.txt"
        unrelated.write_text("Preserve this fixture")
        followup = await services.interaction.submit("Change it so it handles division by zero.")
        assert services.interaction.context(services.current_chat_id).workspace_id == before
        assert unrelated.read_text() == "Preserve this fixture"
        assert "checks passed" in followup["messages"][-1]["content"], followup["messages"][-1]["content"]
        rerun = await services.studio.run(workspace.id)
        await services.studio.input(workspace.id, rerun["session_id"], "9 / 0\n2 + 3\nquit\n")
        final = await asyncio.wait_for(services.run_service.wait(rerun["session_id"]), 15)
        assert final.state == "completed" and "zero" in final.stdout.lower(), final.to_dict()
        assert re.search(r"(?:Result:|=)\s*5(?:\.0)?\b", final.stdout), final.stdout
        runs = []
        for run in list(services.run_service.sessions.values()):
            runs.append((await services.run_service.wait(run.id)).to_dict())
        sources = {str(p.relative_to(workspace.root_path)): p.read_text() for p in Path(workspace.root_path).rglob("*.py")}
        record = {"trace": trace, "answer": result["messages"][-1]["content"], "workspace": workspace.to_dict(), "sources": sources, "runs": runs, "reviews": reviews}
        (root / "acceptance.json").write_text(json.dumps(record, indent=2))
        print("EVIDENCE", root, flush=True)
        print(json.dumps({"workspace_id": workspace.id, "runs": [{"state": r["state"], "output": r["stdout"][-1200:]} for r in runs]}), flush=True)
    finally:
        await services.shutdown()


if __name__ == "__main__":
    if sys.argv[1:] == ["--check-source"]:
        check_source(sys.stdin.read())
    else:
        asyncio.run(main())
