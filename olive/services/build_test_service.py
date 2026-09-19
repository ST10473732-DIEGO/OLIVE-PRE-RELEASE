from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import sys


@dataclass(frozen=True,slots=True)
class ValidationCommand:
    name: str
    executable: str
    arguments: tuple[str,...]
    working_directory: str
    source: str = "known_standard"


class BuildAndTestService:
    def detect(self,root:str|Path) -> list[ValidationCommand]:
        root=Path(root).resolve(strict=True); commands=[]
        python=self.python_executable(root)
        if (root/"pyproject.toml").exists() or (root/"requirements.txt").exists() or any(root.glob("*.py")):
            commands.append(ValidationCommand("Python compile",python,("-m","compileall","-q","."),str(root)))
            if (root/"tests").is_dir(): commands.append(ValidationCommand("Python unit tests",python,("-m","unittest","discover","-s","tests","-v"),str(root)))
        solutions=sorted(root.glob("*.sln")); projects=sorted(root.glob("*.csproj"))
        if solutions or projects:
            target=str((solutions or projects)[0].name); commands.extend([
                ValidationCommand(".NET restore","dotnet",("restore",target),str(root)),
                ValidationCommand(".NET build","dotnet",("build",target,"--no-restore"),str(root)),
                ValidationCommand(".NET test","dotnet",("test",target,"--no-build"),str(root))])
        if (root/"package.json").exists():
            commands.append(ValidationCommand("Node tests","npm",("test",),str(root),"user_approval_required"))
        if (root/"pom.xml").exists(): commands.append(ValidationCommand("Maven tests","mvn",("test",),str(root)))
        elif (root/"gradlew.bat").exists(): commands.append(ValidationCommand("Gradle tests","gradlew.bat",("test",),str(root)))
        elif list(root.glob('*.java')):
            sources = sorted(path.name for path in root.glob('*.java'))
            if len(sources) > 200:
                raise ValueError('Use a build manifest for projects with more than 200 root Java files')
            commands.append(ValidationCommand('Java compile', 'javac',
                ('-proc:none', '-classpath', str(root/'lib'/'*'), *sources), str(root)))
        return commands

    @staticmethod
    def python_executable(root:Path) -> str:
        for folder in (".venv","venv"):
            for relative in ("Scripts/python.exe", "bin/python"):
                candidate = root / folder / relative
                if candidate.is_file(): return str(candidate)
        if not getattr(sys, "frozen", False) and Path(sys.executable).is_file():
            return sys.executable
        return shutil.which("python") or "python.exe"

    def dotnet_template(self,root:str|Path,template:str,name:str) -> ValidationCommand:
        allowed={"console":"console","webapi":"webapi"}
        if template not in allowed: raise ValueError("Only built-in console and webapi templates are supported")
        if not name.replace("_","").replace("-","").isalnum(): raise ValueError("Invalid project name")
        return ValidationCommand(f"Create .NET {template}","dotnet",("new",allowed[template],"-n",name),str(Path(root).resolve(strict=True)),"user_approved_template")
