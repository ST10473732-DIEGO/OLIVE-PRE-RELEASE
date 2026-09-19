from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True,slots=True)
class CodeProblem:
    file:str|None
    line:int|None
    column:int|None
    severity:str
    message:str
    tool:str
    error_code:str|None=None


class ProblemService:
    PATTERNS=(
        ("dotnet",re.compile(r"^(.*?\.(?:cs|fs|vb))\((\d+),(\d+)\):\s*(error|warning)\s+([A-Z]+\d+):\s*(.*?)(?:\s+\[.*)?$",re.I)),
        ("python",re.compile(r'^\s*File "([^"]+)", line (\d+)(?:, in .*)?$')),
        ("generic",re.compile(r"^(.+?):(\d+):(\d+):\s*(error|warning):\s*(.*)$",re.I)),)

    def parse(self,output:str) -> list[CodeProblem]:
        problems=[];lines=output.splitlines()
        for index,line in enumerate(lines):
            match=self.PATTERNS[0][1].match(line)
            if match:problems.append(CodeProblem(match[1],int(match[2]),int(match[3]),match[4].lower(),match[6].strip(),"dotnet",match[5]));continue
            match=self.PATTERNS[1][1].match(line)
            if match:
                message=lines[index+1].strip() if index+1<len(lines) else "Python error"
                problems.append(CodeProblem(match[1],int(match[2]),None,"error",message,"python"));continue
            match=self.PATTERNS[2][1].match(line)
            if match:problems.append(CodeProblem(match[1],int(match[2]),int(match[3]),match[4].lower(),match[5].strip(),"compiler"))
        unique={}
        for problem in problems:
            key=(problem.file,problem.line,problem.column,problem.severity,problem.message,problem.tool,problem.error_code)
            unique.setdefault(key,problem)
        return list(unique.values())
