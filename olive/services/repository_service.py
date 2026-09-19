from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess


@dataclass(frozen=True, slots=True)
class GitResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int


class RepositoryService:
    SAFE_READ = {"status", "diff", "log", "branch"}
    FORBIDDEN = {("reset", "--hard"), ("clean", "-fd"), ("push", "--force"), ("push", "-f")}

    def root(self, path: str | Path) -> Path | None:
        result = self._run(Path(path), "rev-parse", "--show-toplevel", check=False)
        return Path(result.stdout.strip()).resolve() if result.returncode == 0 and result.stdout.strip() else None

    def status(self, path: str | Path) -> dict:
        root = self._require_root(path)
        result = self._run(root, "status", "--porcelain=v1", "--branch")
        lines=result.stdout.splitlines(); branch=lines[0][3:] if lines and lines[0].startswith("## ") else ""
        entries=[]
        for line in lines[1:]:
            if len(line)>=3: entries.append({"index":line[0],"worktree":line[1],"path":line[3:]})
        return {"root":str(root),"branch":branch,"entries":entries,"clean":not entries}

    def diff(self, path: str | Path, staged: bool = False, max_bytes: int = 512_000) -> str:
        args=["diff"]; args += ["--cached"] if staged else []
        return self._run(self._require_root(path), *args).stdout[:max_bytes]

    def log(self, path: str | Path, limit: int = 20) -> list[dict]:
        fmt="%H%x1f%h%x1f%an%x1f%aI%x1f%s"
        result=self._run(self._require_root(path),"log",f"--max-count={min(100,max(1,limit))}",f"--format={fmt}")
        return [dict(zip(("hash","short_hash","author","date","subject"),line.split("\x1f",4)))
                for line in result.stdout.splitlines() if line.count("\x1f")==4]

    def branches(self, path: str | Path) -> list[dict]:
        value=self._run(self._require_root(path),"branch","--format=%(HEAD) %(refname:short)").stdout
        return [{"name":line[2:].strip(),"current":line.startswith("*")} for line in value.splitlines() if len(line)>=2]

    def remotes(self, path: str | Path) -> list[dict]:
        value=self._run(self._require_root(path),"remote","-v").stdout; result=[]
        for line in value.splitlines():
            parts=line.split()
            if len(parts)>=2: result.append({"name":parts[0],"url":_redact_url(parts[1]),"direction":parts[2].strip("()") if len(parts)>2 else ""})
        return result

    def add(self, path: str | Path, files: list[str]) -> GitResult:
        if not files: raise ValueError("At least one file is required")
        return self._run(self._require_root(path),"add","--",*files)

    def commit(self, path: str | Path, message: str) -> GitResult:
        if not message.strip(): raise ValueError("Commit message is required")
        return self._run(self._require_root(path),"commit","-m",message.strip())

    def create_branch(self, path: str | Path, name: str) -> GitResult:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}",name) or ".." in name:
            raise ValueError("Invalid branch name")
        return self._run(self._require_root(path),"switch","-c",name)

    def checkout(self, path: str | Path, name: str) -> GitResult:
        if name.startswith("-"): raise ValueError("Invalid branch name")
        return self._run(self._require_root(path),"switch",name)

    def _require_root(self, path) -> Path:
        root=self.root(path)
        if not root: raise ValueError("Path is not inside a Git repository")
        return root

    def _run(self, cwd: Path, *args: str, check: bool = True) -> GitResult:
        lowered=tuple(item.casefold() for item in args)
        if any(all(token in lowered for token in forbidden) for forbidden in self.FORBIDDEN):
            raise PermissionError("Destructive Git operation is not supported")
        completed=subprocess.run(["git",*args],cwd=str(cwd.resolve()),capture_output=True,text=True,stdin=subprocess.DEVNULL,
                                 timeout=30,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        result=GitResult(tuple(args),completed.stdout,completed.stderr,completed.returncode)
        if check and completed.returncode: raise RuntimeError(completed.stderr.strip() or "Git command failed")
        return result


def _redact_url(value: str) -> str:
    return re.sub(r"(https?://)[^/@\s]+@",r"\1",value)
