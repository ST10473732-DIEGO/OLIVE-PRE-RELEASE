from __future__ import annotations
from dataclasses import dataclass
import re

@dataclass(frozen=True,slots=True)
class TestResult:
    name:str;state:str;duration_seconds:float|None=None;message:str="";file:str|None=None;line:int|None=None

class TestResultService:
    def parse_unittest(self,output):
        results=[]
        for line in output.splitlines():
            match=re.match(r"(test_\S+) \([^)]*\) \.\.\. (ok|FAIL|ERROR|skipped.*)",line.strip())
            if match:results.append(TestResult(match.group(1),"passed" if match.group(2)=="ok" else "skipped" if match.group(2).startswith("skipped") else "failed"))
        return results
