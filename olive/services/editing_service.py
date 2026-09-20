from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import os
import tempfile

from ..workspace import Workspace


def file_hash(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""): digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True,slots=True)
class EditRecord:
    path: str
    before_hash: str | None
    after_hash: str
    edit_type: str
    task_id: str


class EditingService:
    def __init__(self,workspace: Workspace): self.workspace=workspace

    def replace_exact(self,relative_path: str,old: str,new: str,task_id: str,expected_hash: str|None=None) -> EditRecord:
        path=self.workspace.resolve(relative_path); before=self._validate(path,expected_hash); text=path.read_text(encoding="utf-8")
        if not old or text.count(old)!=1: raise ValueError("Expected block must occur exactly once")
        return self._write(path,text.replace(old,new,1),before,"replace_exact",task_id)

    def replace_range(self,relative_path: str,start_line: int,end_line: int,text: str,task_id: str,expected_hash: str|None=None) -> EditRecord:
        path=self.workspace.resolve(relative_path); before=self._validate(path,expected_hash); lines=path.read_text(encoding="utf-8").splitlines(keepends=True)
        if start_line<1 or end_line<start_line or end_line>len(lines): raise ValueError("Invalid line range")
        return self._write(path,"".join(lines[:start_line-1])+text+"".join(lines[end_line:]),before,"replace_range",task_id)

    def create_file(self,relative_path: str,text: str,task_id: str) -> EditRecord:
        path=self.workspace.resolve(relative_path)
        if path.exists(): raise FileExistsError(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation closes the exists/replace race with another editor.
        with path.open('x', encoding='utf-8', newline='') as handle:
            handle.write(text)
        return EditRecord(str(path),None,file_hash(path),'create',task_id)

    def replace_content(self,relative_path:str,text:str,task_id:str,expected_hash:str) -> EditRecord:
        path=self.workspace.resolve(relative_path);before=self._validate(path,expected_hash)
        return self._write(path,text,before,"replace_content",task_id,newline="")

    def _validate(self,path:Path,expected:str|None):
        if not path.is_file(): raise FileNotFoundError(path)
        actual=file_hash(path)
        if expected and actual!=expected: raise RuntimeError("File changed since it was read")
        return actual

    def _write(self,path:Path,text:str,before:str|None,kind:str,task_id:str,newline:str|None=None):
        fd,tmp_name=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent); os.close(fd); tmp=Path(tmp_name)
        try:
            tmp.write_text(text,encoding="utf-8",newline=newline)
            # Revalidate after staging: a local/external edit during staging wins.
            if self.workspace.resolve(path) != path or file_hash(path) != before:
                raise RuntimeError("File changed since it was read")
            tmp.replace(path)
        finally:
            if tmp.exists(): tmp.unlink()
        return EditRecord(str(path),before,file_hash(path),kind,task_id)
