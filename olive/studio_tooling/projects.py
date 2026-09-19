"""Project language/template discovery and new-project creation.

Discovery reports what this machine can *actually* do: an installed SDK or
interpreter, the templates that SDK really offers, and whether OLIVE has a
creation/run adapter for that language. Nothing is installed, and a language is
never reported ready because an editor can colour its syntax.

Creation writes real files through the existing services: `dotnet new` for .NET
(the same CLI the solution system uses) and bounded local starter files for the
others. No package is downloaded and no template hook runs unless the caller
explicitly asked for it as a separate, approval-bound step.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from .toolchain import dotnet_executable, dotnet_info, python_executable

# How long a discovery result stays fresh. Probing spawns processes, so the
# wizard reads the cache and only re-probes when asked.
CACHE_SECONDS = 300
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_. -]{0,79}$")
RESERVED = {"CON", "PRN", "AUX", "NUL", *{f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}}

# Availability vocabulary shown verbatim in the wizard.
READY = "ready"                       # OLIVE can create and open this today
TOOLCHAIN_MISSING = "toolchain_missing"   # SDK/interpreter not installed
TEMPLATE_UNAVAILABLE = "template_unavailable"  # tooling present, templates absent
EDITING_ONLY = "editing_only"         # Monaco can edit it; no creation adapter

# Local starter templates. These never reach the network.
LOCAL_TEMPLATES = {
    "python": {
        "console": {
            "label": "Console application",
            "description": "A main.py entry point and a tests folder.",
            "files": {
                "main.py": 'def greeting(name: str) -> str:\n    return f"Hello, {name}!"\n\n\ndef main() -> None:\n    print(greeting("OLIVE"))\n\n\nif __name__ == "__main__":\n    main()\n',
                "tests/test_main.py": 'import unittest\n\nfrom main import greeting\n\n\nclass GreetingTests(unittest.TestCase):\n    def test_greeting(self):\n        self.assertEqual(greeting("OLIVE"), "Hello, OLIVE!")\n',
                "requirements.txt": "# Add project dependencies here, then use Restore in Studio.\n",
                ".gitignore": "__pycache__/\n.venv/\n*.pyc\n",
                "README.md": "# Python project\n\nRun and debug from Studio. Tests use the standard library `unittest`.\n",
            },
        },
        "package": {
            "label": "Package",
            "description": "An importable package folder with tests.",
            "files": {
                "src/__init__.py": "",
                "src/core.py": 'def greeting(name: str) -> str:\n    return f"Hello, {name}!"\n',
                "tests/test_core.py": 'import unittest\n\nfrom src.core import greeting\n\n\nclass CoreTests(unittest.TestCase):\n    def test_greeting(self):\n        self.assertEqual(greeting("OLIVE"), "Hello, OLIVE!")\n',
                "pyproject.toml": '[project]\nname = "project"\nversion = "0.1.0"\n',
                ".gitignore": "__pycache__/\n.venv/\n*.pyc\n",
            },
        },
    },
    "javascript": {
        "console": {
            "label": "Node script",
            "description": "A single entry point run by the installed Node.",
            "files": {
                "main.js": 'function greeting(name) {\n  return `Hello, ${name}!`;\n}\n\nconsole.log(greeting("OLIVE"));\n\nexport { greeting };\n',
                "package.json": '{\n  "private": true,\n  "type": "module",\n  "scripts": { "start": "node main.js", "test": "node --test" }\n}\n',
                ".gitignore": "node_modules/\n",
                "README.md": "# Node project\n\nNo dependencies are installed. Add them explicitly when you need them.\n",
            },
        },
    },
    "typescript": {
        "console": {
            "label": "TypeScript script",
            "description": "A typed entry point. Compiling needs TypeScript installed.",
            "files": {
                "main.ts": 'export function greeting(name: string): string {\n  return `Hello, ${name}!`;\n}\n\nconsole.log(greeting("OLIVE"));\n',
                "tsconfig.json": '{\n  "compilerOptions": {\n    "target": "ES2022",\n    "module": "ESNext",\n    "moduleResolution": "Bundler",\n    "strict": true\n  }\n}\n',
                "package.json": '{\n  "private": true,\n  "type": "module"\n}\n',
                ".gitignore": "node_modules/\ndist/\n",
            },
        },
    },
    "java": {
        "console": {
            "label": "Console application",
            "description": "A Main class compiled by the installed JDK.",
            "files": {
                "Main.java": 'public class Main {\n    static String greeting(String name) {\n        return "Hello, " + name + "!";\n    }\n\n    public static void main(String[] args) {\n        System.out.println(greeting("OLIVE"));\n    }\n}\n',
                "lib/.gitkeep": "",
                ".gitignore": "*.class\n",
                "README.md": "# Java project\n\nRun uses the installed JDK. Put approved dependency JARs in lib/.\n",
            },
        },
    },
    "empty": {
        "empty": {
            "label": "Empty folder",
            "description": "Just a README, for files you bring yourself.",
            "files": {"README.md": "# New project\n"},
        },
    },
}
# .NET templates OLIVE supports; the installed SDK decides which actually exist.
DOTNET_TEMPLATES = {
    "console": ("Console application", "A runnable console project."),
    "winforms": ("Windows Forms visual application", "An OLIVE-owned native form with Design, Code and Preview surfaces."),
    "classlib": ("Class library", "Shared code referenced by other projects."),
    "webapi": ("ASP.NET Core Web API", "A minimal HTTP API you can run and inspect."),
    "xunit": ("xUnit test project", "Tests with the xUnit framework."),
    "mstest": ("MSTest test project", "Tests with MSTest."),
    "nunit": ("NUnit test project", "Tests with NUnit."),
}


def _run(command: list[str], timeout: float = 25) -> tuple[int, str]:
    """Run a probe with a deadline that actually holds.

    `subprocess.run(timeout=...)` kills the child and then waits again on the
    pipes, which never closes while a grandchild still holds them: a `dotnet`
    first run leaves one behind and the probe hangs forever. Kill, drain once
    with a short deadline, and give up rather than block discovery.
    """
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, ValueError):
        return 1, ""
    try:
        out, _ = process.communicate(timeout=timeout)
        return process.returncode, out.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.communicate(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            pass
        return 1, ""
    except OSError:
        return 1, ""


def _dotnet_template_names(executable: str) -> set[str]:
    """Short names the installed SDK actually offers."""
    for arguments in (["new", "list"], ["new", "--list"]):
        code, out = _run([executable, *arguments], timeout=20)
        if code == 0 and out:
            names: set[str] = set()
            for line in out.splitlines():
                # Columns are localised; the short-name column is comma separated
                # and contains no spaces, so match those tokens directly.
                for token in re.findall(r"[a-z][a-z0-9.-]{2,}(?:,[a-z][a-z0-9.-]{2,})*", line):
                    names.update(token.split(","))
            if names:
                return names
    return set()


def _python_interpreters(root: str | None) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()

    def add(path: str, label: str):
        if not path:
            return
        resolved = str(Path(path))
        if resolved.lower() in seen or not Path(resolved).is_file():
            return
        seen.add(resolved.lower())
        code, out = _run([resolved, "-c", "import sys;print(sys.version.split()[0])"], timeout=15)
        found.append({"path": resolved, "label": label, "version": out.strip() if code == 0 else ""})

    if root:
        add(python_executable(root), "Project interpreter")
    add(sys.executable, "OLIVE runtime interpreter")
    which = shutil.which("python") or shutil.which("python3")
    if which:
        add(which, "System interpreter")
    return found[:8]


async def discover(root: str | None = None) -> dict:
    """Probe real tooling. Runs off the event loop; the caller caches it."""
    return await asyncio.to_thread(_discover_blocking, root)


#: Whole-discovery deadline. A probe that misses it is reported as unknown
#: rather than holding the wizard open on a spinner.
PROBE_SECONDS = 45


def _discover_blocking(root: str | None) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    languages: list[dict] = []
    # Independent probes run together so the wizard is not held up by the
    # slowest toolchain on the machine. The pool is never joined: a probe that
    # outlives its deadline is abandoned, not waited for.
    pool = ThreadPoolExecutor(max_workers=4)
    try:
        dotnet_templates = pool.submit(
            lambda: _dotnet_template_names(dotnet_executable()) if dotnet_executable() else set())
        python_probe = pool.submit(_python_interpreters, root)
        node_probe = pool.submit(shutil.which, "node")
        javac_probe = pool.submit(shutil.which, "javac")
        deadline = time.monotonic() + PROBE_SECONDS

        def answer(probe, fallback):
            try:
                return probe.result(timeout=max(0.1, deadline - time.monotonic()))
            except Exception:
                return fallback
    finally:
        pool.shutdown(wait=False)

    # --- C# / .NET -------------------------------------------------------
    executable = dotnet_executable()
    if executable:
        names = answer(dotnet_templates, set())
        templates = [
            {"id": key, "label": label, "description": description, "network": key in {'xunit','mstest','nunit'}}
            for key, (label, description) in DOTNET_TEMPLATES.items()
            if (not names or key in names) and (key!='winforms' or sys.platform=='win32' and 'winforms' in names)
        ]
        code, out = _run([executable, "--version"], timeout=20)
        version = out.strip() if code == 0 else ""
        languages.append({
            "id": "csharp", "label": "C#", "runtime": ".NET SDK",
            "availability": READY if templates else TEMPLATE_UNAVAILABLE,
            "detail": f".NET SDK {version}" if version else ".NET SDK detected",
            "templates": templates,
            "solution": True,
            "options": {"frameworks": []},
        })
    else:
        languages.append({
            "id": "csharp", "label": "C#", "runtime": ".NET SDK",
            "availability": TOOLCHAIN_MISSING,
            "detail": "The .NET SDK was not found. Install it, then refresh.",
            "templates": [], "solution": True, "options": {},
        })

    # --- Python ----------------------------------------------------------
    interpreters = answer(python_probe, [])
    languages.append({
        "id": "python", "label": "Python", "runtime": "Interpreter",
        "availability": READY if interpreters else TOOLCHAIN_MISSING,
        "detail": (f"{interpreters[0]['label']} {interpreters[0]['version']}".strip()
                   if interpreters else "A Python interpreter was not found. Install one, then refresh."),
        "templates": [{"id": key, "label": item["label"], "description": item["description"], "network": False}
                      for key, item in LOCAL_TEMPLATES["python"].items()],
        "solution": False,
        "options": {"interpreters": interpreters},
    })

    # --- JavaScript / TypeScript ----------------------------------------
    node = answer(node_probe, None)
    node_version = ""
    if node:
        code, out = _run([node, "--version"], timeout=15)
        node_version = out.strip() if code == 0 else ""
    for language_id, label in (("javascript", "JavaScript"), ("typescript", "TypeScript")):
        languages.append({
            "id": language_id, "label": label, "runtime": "Node.js",
            "availability": READY if node else TOOLCHAIN_MISSING,
            "detail": (f"Node {node_version}" if node_version else "Node.js detected") if node
                      else "Node.js was not found. Install it, then refresh.",
            "templates": [{"id": key, "label": item["label"], "description": item["description"], "network": False}
                          for key, item in LOCAL_TEMPLATES[language_id].items()],
            "solution": False,
            "options": {},
        })

    # --- Java ------------------------------------------------------------
    javac = answer(javac_probe, None)
    java_version = ""
    if javac:
        code, out = _run([javac, "-version"], timeout=20)
        java_version = out.strip()
    languages.append({
        "id": "java", "label": "Java", "runtime": "JDK",
        "availability": READY if javac else TOOLCHAIN_MISSING,
        "detail": (java_version or "JDK detected") if javac
                  else "A JDK (javac) was not found. Install one, then refresh.",
        "templates": [{"id": key, "label": item["label"], "description": item["description"], "network": False}
                      for key, item in LOCAL_TEMPLATES["java"].items()],
        "solution": False,
        "options": {},
    })

    # --- Empty -----------------------------------------------------------
    languages.append({
        "id": "empty", "label": "Empty project", "runtime": "None",
        "availability": READY,
        "detail": "A folder with a README, for files you bring yourself.",
        "templates": [{"id": "empty", "label": "Empty folder",
                       "description": LOCAL_TEMPLATES["empty"]["empty"]["description"], "network": False}],
        "solution": False, "options": {},
    })
    return {"languages": languages, "checked_at": time.time(), "git": bool(shutil.which("git"))}


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not NAME.fullmatch(name) or name.endswith((" ", ".")):
        raise ValueError("Use a project name without path separators or reserved characters.")
    if name.split(".")[0].upper() in RESERVED:
        raise ValueError("That name is reserved by Windows. Choose another.")
    return name


def resolve_destination(location: str, name: str) -> Path:
    """The exact folder that will be created, refusing to reuse a non-empty one."""
    validate_name(name)
    if not isinstance(location, str) or not location.strip():
        raise ValueError("Choose where the project should be created.")
    parent = Path(location).expanduser()
    if not parent.is_absolute():
        raise ValueError("Choose an absolute location.")
    parent = parent.resolve()
    if not parent.is_dir():
        raise ValueError("That location does not exist.")
    target = (parent / name).resolve()
    if parent not in target.parents:
        raise ValueError("The project must be created inside the chosen location.")
    if target.exists() and any(target.iterdir()):
        # Never merge into or overwrite an existing folder.
        raise ValueError("A non-empty folder with that name already exists there.")
    return target


def write_local_template(target: Path, language: str, template: str) -> list[str]:
    group = LOCAL_TEMPLATES.get(language)
    if not group or template not in group:
        raise ValueError("That template is not available for this language.")
    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for relative, content in group[template]["files"].items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:  # exclusive: never overwrite
            handle.write(content)
        written.append(relative)
    return written


def git_init_command(target: Path) -> list[str]:
    return ["git", "init", "-q", str(target)]


def dotnet_new_command(executable: str, template: str, name: str, target: Path,
                       framework: str = "") -> list[str]:
    if template not in DOTNET_TEMPLATES:
        raise ValueError("That template is not available for this language.")
    command = [executable, "new", template, "-n", name, "-o", str(target)]
    command += ['--no-restore','--no-update-check']
    if template=='webapi':command+=['--no-openapi']
    if framework:
        if not re.fullmatch(r"net\d+\.\d+", framework):
            raise ValueError("Invalid target framework")
        command += ["-f", framework]
    return command


def dotnet_environment() -> dict[str, str]:
    return dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")


async def dotnet_sdk_version() -> str:
    info = await dotnet_info()
    return str(info.get("version", "")) if isinstance(info, dict) else ""
