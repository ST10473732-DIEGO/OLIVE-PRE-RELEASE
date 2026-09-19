"""The .NET project system: discovery, structured commands and structured test results.

Commands are assembled from the project graph, never from model prose. Nothing
here upgrades an SDK or framework; the workspace's own global.json and project
files decide what the installed CLI does.
"""
from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .toolchain import read_json

IGNORED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "bin", "obj", ".vs", "dist", "build", "__pycache__", "TestResults"}
PROJECT_SUFFIXES = {".csproj", ".fsproj", ".vbproj"}
TEST_PACKAGES = {"microsoft.net.test.sdk", "xunit", "xunit.v3", "nunit", "mstest.testframework", "mstest", "tunit"}
SLN_PROJECT = re.compile(r'^Project\("\{[0-9A-Fa-f-]+\}"\)\s*=\s*"([^"]*)",\s*"([^"]*)",\s*"\{([0-9A-Fa-f-]+)\}"', re.M)


def _walk(root: Path, suffixes: set[str], depth: int = 6) -> list[Path]:
    found = []
    stack = [(root, 0)]
    while stack:
        folder, level = stack.pop()
        try:
            entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name.casefold() not in IGNORED_DIRECTORIES and not entry.is_symlink() and level < depth:
                    stack.append((entry, level + 1))
            elif entry.suffix.casefold() in suffixes:
                found.append(entry)
            if len(found) > 400:
                return found
    return found


def _text(element, name: str) -> str:
    for child in element.iter(name):
        return (child.text or "").strip()
    return ""


def parse_project(path: Path, root: Path) -> dict:
    """Bounded XML read of an SDK-style project; malformed files are reported, not raised."""
    item = {"path": str(path), "relative_path": path.relative_to(root).as_posix(), "name": path.stem, "sdk": "", "target_frameworks": [],
            "output_type": "", "assembly_name": path.stem, "references": [], "packages": [], "is_test": False, "is_web": False,
            "is_executable": False, "launch_profiles": [], "error": ""}
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as error:
        item["error"] = f"Project file could not be read: {error}"[:200]
        return item
    project = tree.getroot()
    item["sdk"] = project.get("Sdk", "")
    frameworks = _text(project, "TargetFrameworks") or _text(project, "TargetFramework")
    item["target_frameworks"] = [f.strip() for f in frameworks.split(";") if f.strip()]
    item["output_type"] = _text(project, "OutputType") or ("Exe" if "Web" in item["sdk"] else "Library")
    item["assembly_name"] = _text(project, "AssemblyName") or path.stem
    is_test_property = _text(project, "IsTestProject").casefold()
    for reference in project.iter("ProjectReference"):
        include = reference.get("Include", "")
        if include:
            item["references"].append((path.parent / include.replace("\\", "/")).resolve().as_posix())
    for package in project.iter("PackageReference"):
        include = package.get("Include", "")
        if include:
            item["packages"].append(include)
    packages = {p.casefold() for p in item["packages"]}
    item["is_test"] = is_test_property == "true" or bool(packages & TEST_PACKAGES) or "microsoft.net.sdk.test" in item["sdk"].casefold()
    item["uses_testing_platform"] = _text(project, "UseMicrosoftTestingPlatformRunner").casefold() == "true" or any(
        p.startswith("microsoft.testing.platform") for p in packages) or "xunit.v3" in packages
    item["is_web"] = "Microsoft.NET.Sdk.Web" in item["sdk"]
    item["is_executable"] = item["output_type"].casefold() in {"exe", "winexe"} or item["is_web"]
    settings = read_json(path.parent / "Properties" / "launchSettings.json")
    if isinstance(settings, dict):
        for name, profile in (settings.get("profiles") or {}).items():
            if isinstance(profile, dict):
                item["launch_profiles"].append({"name": str(name)[:100], "command": str(profile.get("commandName", ""))[:40],
                                                "application_url": str(profile.get("applicationUrl", ""))[:300],
                                                "launch_browser": bool(profile.get("launchBrowser", False))})
    return item


def parse_solution(path: Path, root: Path) -> dict:
    item = {"path": str(path), "relative_path": path.relative_to(root).as_posix(), "name": path.stem, "format": path.suffix.lstrip("."),
            "projects": [], "error": ""}
    try:
        if path.suffix.casefold() == ".slnx":
            tree = ET.parse(path)
            for project in tree.getroot().iter("Project"):
                include = project.get("Path", "")
                if include:
                    item["projects"].append((path.parent / include.replace("\\", "/")).resolve().as_posix())
        else:
            text = path.read_text(encoding="utf-8-sig", errors="replace")[:400_000]
            for _, relative, _ in SLN_PROJECT.findall(text):
                if Path(relative).suffix.casefold() in PROJECT_SUFFIXES:
                    item["projects"].append((path.parent / relative.replace("\\", "/")).resolve().as_posix())
    except (ET.ParseError, OSError) as error:
        item["error"] = f"Solution could not be read: {error}"[:200]
    return item


def scan(root: str | Path) -> dict:
    root = Path(root).resolve()
    solutions = [parse_solution(p, root) for p in _walk(root, {".sln", ".slnx"}, depth=2)]
    projects = [parse_project(p, root) for p in _walk(root, PROJECT_SUFFIXES)]
    global_json = read_json(root / "global.json")
    sdk = (global_json or {}).get("sdk") if isinstance(global_json, dict) else None
    python_markers = [p for p in ("pyproject.toml", "requirements.txt", "main.py", "setup.py") if (root / p).exists()]
    return {
        "root": str(root),
        "solutions": solutions,
        "projects": projects,
        "global_json": {"sdk_version": str(sdk.get("version", ""))[:40] if isinstance(sdk, dict) else "",
                        "roll_forward": str(sdk.get("rollForward", ""))[:40] if isinstance(sdk, dict) else ""} if global_json else None,
        "python": {"present": bool(python_markers), "markers": python_markers, "tests_directory": (root / "tests").is_dir()},
        "node": {"present": (root / "package.json").exists()},
        "kind": "dotnet" if projects else "python" if python_markers else "node" if (root / "package.json").exists() else "folder",
    }


def default_startup(projects: list[dict]) -> str:
    executables = [p for p in projects if p["is_executable"] and not p["is_test"]]
    web = [p for p in executables if p["is_web"]]
    chosen = (web or executables or projects)[:1]
    return chosen[0]["path"] if chosen else ""


def build_command(target: str, configuration: str, mode: str = "build") -> list[str]:
    """Structured CLI invocation; only whitelisted modes and a validated configuration."""
    if configuration not in {"Debug", "Release"}:
        raise ValueError("Configuration must be Debug or Release")
    if mode == "build":
        return ["dotnet", "build", target, "-c", configuration, "--nologo", "-v", "minimal"]
    if mode == "rebuild":
        return ["dotnet", "build", target, "-c", configuration, "--no-incremental", "--nologo", "-v", "minimal"]
    if mode == "clean":
        return ["dotnet", "clean", target, "-c", configuration, "--nologo", "-v", "minimal"]
    if mode == "restore":
        return ["dotnet", "restore", target, "--nologo", "-v", "minimal"]
    raise ValueError("Unsupported build mode")


def run_command(project: str, configuration: str, arguments: list[str], launch_profile: str = "") -> list[str]:
    if configuration not in {"Debug", "Release"}:
        raise ValueError("Configuration must be Debug or Release")
    command = ["dotnet", "run", "--project", project, "-c", configuration, "--nologo"]
    if launch_profile:
        command += ["--launch-profile", launch_profile]
    else:
        command += ["--no-launch-profile"]
    if arguments:
        command += ["--", *arguments]
    return command


def target_path_command(project: str, configuration: str) -> list[str]:
    return ["dotnet", "msbuild", project, f"-p:Configuration={configuration}", "-getProperty:TargetPath", "-nologo"]


def test_command(target: str, configuration: str, results_directory: str, filters: list[str] | None, testing_platform: bool,
                 list_only: bool = False, no_build: bool = False) -> list[str]:
    if configuration not in {"Debug", "Release"}:
        raise ValueError("Configuration must be Debug or Release")
    command = ["dotnet", "test", target, "-c", configuration, "--nologo", "-v", "minimal"]
    if no_build:
        command.append("--no-build")
    if list_only:
        return command + (["--", "--list-tests"] if testing_platform else ["--list-tests"])
    if testing_platform:
        command += ["--", "--report-trx", "--report-trx-filename", "olive.trx", "--results-directory", results_directory]
        if filters:
            command += ["--filter", "|".join(f"FullyQualifiedName={name}" for name in filters)]
    else:
        command += ["--logger", "trx;LogFileName=olive.trx", "--results-directory", results_directory]
        if filters:
            command += ["--filter", "|".join(f"FullyQualifiedName={name}" for name in filters)]
    return command


def parse_list_tests(output: str) -> list[str]:
    names, active = [], False
    for line in output.splitlines():
        if "The following Tests are available" in line:
            active = True
            continue
        if active:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("Test run for", "Build", "Determining")):
                active = False
                continue
            names.append(stripped)
    return names[:5000]


STACK_LOCATION = re.compile(r" in (.+?):line (\d+)", re.I)


def parse_trx(path: Path) -> dict:
    """Structured results from a VSTest/MTP TRX report."""
    results, summary = [], {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration_seconds": 0.0}
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as error:
        return {"results": [], "summary": summary, "error": f"TRX could not be read: {error}"[:200]}
    namespace = ""
    root = tree.getroot()
    if root.tag.startswith("{"):
        namespace = root.tag[: root.tag.index("}") + 1]
    definitions = {}
    for definition in root.iter(namespace + "UnitTest"):
        method = definition.find(namespace + "TestMethod")
        if method is not None:
            definitions[definition.get("id", "")] = {"class": method.get("className", ""), "method": method.get("name", "")}
    for result in root.iter(namespace + "UnitTestResult"):
        outcome = (result.get("outcome") or "").casefold()
        state = "passed" if outcome == "passed" else "failed" if outcome in {"failed", "error", "timeout", "aborted"} else "skipped"
        duration = result.get("duration") or "0:00:00"
        seconds = 0.0
        try:
            hours, minutes, rest = duration.split(":")
            seconds = int(hours) * 3600 + int(minutes) * 60 + float(rest)
        except ValueError:
            pass
        message, stack, file, line = "", "", "", None
        error = result.find(namespace + "Output/" + namespace + "ErrorInfo")
        if error is not None:
            message = (error.findtext(namespace + "Message") or "")[:4000]
            stack = (error.findtext(namespace + "StackTrace") or "")[:12000]
            match = STACK_LOCATION.search(stack)
            if match:
                file, line = match.group(1), int(match.group(2))
        definition = definitions.get(result.get("testId", ""), {})
        results.append({"name": result.get("testName", ""), "full_name": (definition.get("class", "") + "." + definition.get("method", "")).strip("."),
                        "state": state, "duration_seconds": round(seconds, 4), "message": message, "stack_trace": stack,
                        "file": file, "line": line})
        summary[state] += 1
        summary["duration_seconds"] += seconds
    summary["total"] = len(results)
    summary["duration_seconds"] = round(summary["duration_seconds"], 3)
    return {"results": results[:5000], "summary": summary, "error": ""}


BUILD_DIAGNOSTIC = re.compile(r"^(?P<file>[^\s(][^(]*?)\((?P<line>\d+),(?P<column>\d+)\):\s*(?P<severity>error|warning)\s+(?P<code>[A-Z]+\d+):\s*(?P<message>.*?)(?:\s*\[(?P<project>[^\]]+)\])?\s*$", re.I)


def parse_build_diagnostics(output: str) -> list[dict]:
    seen, items = set(), []
    for line in output.splitlines():
        match = BUILD_DIAGNOSTIC.match(line.strip())
        if not match:
            continue
        key = (match["file"], match["line"], match["code"], match["message"])
        if key in seen:
            continue
        seen.add(key)
        items.append({"file": match["file"], "line": int(match["line"]), "column": int(match["column"]), "severity": match["severity"].lower(),
                      "code": match["code"], "message": match["message"][:1000], "project": match["project"] or ""})
        if len(items) >= 500:
            break
    return items
