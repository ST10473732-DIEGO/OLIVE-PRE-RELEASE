from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True,slots=True)
class DependencyPlan:
    ecosystem:str;manifest:str;command:tuple[str,...];permission:str="dependencies.install"

class DependencyService:
    def inspect(self,root):
        root=Path(root).resolve(strict=True);plans=[]
        if (root/"requirements.txt").is_file():plans.append(DependencyPlan("python","requirements.txt",(".venv/Scripts/python.exe","-m","pip","install","-r","requirements.txt")))
        if (root/"pyproject.toml").is_file():plans.append(DependencyPlan("python","pyproject.toml",(".venv/Scripts/python.exe","-m","pip","install","-e",".")))
        if (root/"package.json").is_file():plans.append(DependencyPlan("node","package.json",("npm","install")))
        targets=sorted(root.glob("*.sln"))+sorted(root.glob("*.csproj"))
        if targets:plans.append(DependencyPlan("dotnet",targets[0].name,("dotnet","restore",targets[0].name)))
        return plans
