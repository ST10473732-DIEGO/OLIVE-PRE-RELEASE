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

    def summarize(self,output:str)->dict:
        """Counts parsed from real runner output only; None when no runner summary is present.

        Supported: unittest, pytest, dotnet test (VSTest and Microsoft.Testing.Platform),
        node --test, Jest/Vitest, cargo test, go test and Maven Surefire.
        """
        text=output or ""
        def total(**counts):
            counts={k:int(v or 0) for k,v in counts.items()}
            counts.setdefault("skipped",0)
            counts["total"]=counts.get("total") or counts["passed"]+counts["failed"]+counts["skipped"]
            return counts
        match=re.search(r"^Ran (\d+) tests? in [\d.]+s\s*\n+\s*(OK|FAILED)(?: \(([^)]*)\))?",text,re.M)
        if match:
            detail=dict(re.findall(r"(failures|errors|skipped|expected failures|unexpected successes)=(\d+)",match.group(3) or ""))
            failed=int(detail.get("failures",0))+int(detail.get("errors",0));skipped=int(detail.get("skipped",0))
            ran=int(match.group(1))
            return {"framework":"unittest",**total(passed=ran-failed-skipped,failed=failed,skipped=skipped,total=ran)}
        match=re.search(r"^=+ (.*?) in [\d.]+s(?: \([^)]*\))? =+$",text,re.M)
        if match and re.search(r"\b(passed|failed|error)",match.group(1)):
            parts=dict((name,int(number)) for number,name in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)",match.group(1)))
            return {"framework":"pytest",**total(passed=parts.get("passed",0)+parts.get("xpassed",0),
                    failed=parts.get("failed",0)+parts.get("error",0)+parts.get("errors",0),skipped=parts.get("skipped",0)+parts.get("xfailed",0))}
        match=re.search(r"(?:Passed|Failed)!\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+),\s*Total:\s*(\d+)",text)
        if match:
            return {"framework":"dotnet",**total(failed=match.group(1),passed=match.group(2),skipped=match.group(3),total=match.group(4))}
        match=re.search(r"total:\s*(\d+)\s+failed:\s*(\d+)\s+succeeded:\s*(\d+)\s+skipped:\s*(\d+)",text,re.I)
        if match:
            return {"framework":"dotnet",**total(total=match.group(1),failed=match.group(2),passed=match.group(3),skipped=match.group(4))}
        if re.search(r"^# tests \d+",text,re.M):
            get=lambda name:int((re.search(rf"^# {name} (\d+)",text,re.M) or [0,0])[1])
            return {"framework":"node",**total(passed=get("pass"),failed=get("fail"),skipped=get("skipped")+get("todo"))}
        match=re.search(r"^\s*Tests:\s+(.*\d+ total)",text,re.M)
        if match:
            parts=dict((name,int(number)) for number,name in re.findall(r"(\d+) (passed|failed|skipped|todo|total)",match.group(1)))
            return {"framework":"jest",**total(passed=parts.get("passed",0),failed=parts.get("failed",0),skipped=parts.get("skipped",0)+parts.get("todo",0),total=parts.get("total",0))}
        matches=re.findall(r"test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored",text)
        if matches:
            return {"framework":"cargo",**total(passed=sum(int(m[0]) for m in matches),failed=sum(int(m[1]) for m in matches),skipped=sum(int(m[2]) for m in matches))}
        matches=re.findall(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)\s*$",text,re.M)
        if matches:
            run,failures,errors,skipped=(int(v) for v in matches[-1])
            return {"framework":"maven",**total(passed=run-failures-errors-skipped,failed=failures+errors,skipped=skipped,total=run)}
        if re.search(r"^(?:ok|FAIL|---) ",text,re.M) and re.search(r"^(?:ok|FAIL)\s+\S+",text,re.M):
            passed=len(re.findall(r"^--- PASS",text,re.M));failed=len(re.findall(r"^--- FAIL",text,re.M))
            if passed or failed:return {"framework":"go",**total(passed=passed,failed=failed)}
        return {}
