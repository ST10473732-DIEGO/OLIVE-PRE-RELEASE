from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid
import hashlib
import os
from threading import RLock

from .editing_service import EditingService
from .checkpoint_service import CheckpointService
from ..workspace import Workspace


@dataclass(slots=True)
class StudioFileState:
    relative_path:str
    text:str
    loaded_hash:str
    saved_text:str
    cursor_line:int=1

    @property
    def unsaved(self):return self.text!=self.saved_text


class StudioService:
    def __init__(self,workspace:Workspace,checkpoints:CheckpointService, *, write_lock=None):
        self.write_lock = write_lock or RLock()
        self.workspace=workspace;self.checkpoints=checkpoints;self.open_files:dict[str,StudioFileState]={};self.active_path=None

    def tree(self,limit=2000, *, max_depth=None, exclude_hidden=False):
        root=Path(self.workspace.root_path);values=[]
        ignored={".git",".venv","venv","node_modules","bin","obj","dist","build","__pycache__"}
        if limit <= 0:return values
        for directory, directories, files in os.walk(root, followlinks=False):
            directories[:] = sorted(name for name in directories if name.casefold() not in ignored
                                    and not (exclude_hidden and name.startswith("."))
                                    and not (Path(directory) / name).is_symlink()
                                    and not getattr(Path(directory) / name, "is_junction", lambda: False)())
            if max_depth is not None and len(Path(directory).relative_to(root).parts) >= max_depth:
                directories[:] = []
                continue
            for name in [*directories, *sorted(files)]:
                if exclude_hidden and name.startswith("."):continue
                path = Path(directory) / name
                try:self.workspace.resolve(path)
                except (PermissionError, OSError):continue
                values.append({"path":path.relative_to(root).as_posix(),"directory":path.is_dir()})
                if len(values)>=limit:return sorted(values,key=lambda item:(not item["directory"],item["path"].casefold()))
        return sorted(values,key=lambda item:(not item["directory"],item["path"].casefold()))

    def open_file(self,relative_path:str) -> StudioFileState:
        path=self.workspace.resolve(relative_path)
        if not path.is_file():raise FileNotFoundError(path)
        with path.open("rb") as handle:raw=handle.read(2 * 1024 * 1024 + 1)
        if len(raw)>2 * 1024 * 1024:raise ValueError("Files larger than 2 MB cannot be opened in the editor")
        if b"\0" in raw:raise ValueError("Binary files cannot be edited as source text")
        text=raw.decode("utf-8")
        state=StudioFileState(relative_path,text,hashlib.sha256(raw).hexdigest(),text)
        self.open_files[relative_path]=state;self.active_path=relative_path;return state

    def update(self,relative_path:str,text:str):self.open_files[relative_path].text=text

    def save(self,relative_path:str,task_id:str|None=None):
        with self.write_lock:
            state=self.open_files[relative_path];task_id=task_id or f"studio-{uuid.uuid4()}";self.checkpoints.create(self.workspace,task_id,[relative_path])
            record=EditingService(self.workspace).replace_content(relative_path,state.text,task_id,state.loaded_hash)
            state.loaded_hash=record.after_hash;state.saved_text=state.text;return record

    def search_file(self,relative_path:str,query:str):
        return [{"line":i,"text":line} for i,line in enumerate(self.open_files[relative_path].text.splitlines(),1) if query.casefold() in line.casefold()]

    def search_workspace(self, query: str, limit: int = 200):
        needle = query.strip().casefold()
        if not needle or limit <= 0:return []
        matches = []
        for item in self.tree():
            if item["directory"]:continue
            try:
                path = self.workspace.resolve(item["path"])
                with path.open("rb") as handle:raw = handle.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024 or b"\0" in raw:continue
                text = raw.decode("utf-8")
            except (OSError, UnicodeError, PermissionError):continue
            for number, line in enumerate(text.splitlines(), 1):
                if needle in line.casefold():matches.append((item["path"], number, line.strip()))
                if len(matches) >= min(limit, 200):return matches
        return matches
