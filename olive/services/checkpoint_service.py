from __future__ import annotations

from pathlib import Path
import json
import shutil

from ..utils.files import content_hash
from ..workspace import Workspace


class CheckpointService:
    def __init__(self,root: Path): self.root=root

    def create(self,workspace: Workspace,task_id: str,relative_paths:list[str]) -> dict:
        folder=self.root/task_id; folder.mkdir(parents=True,exist_ok=True); manifest_path=folder/"manifest.json"
        if manifest_path.exists():
            manifest=json.loads(manifest_path.read_text(encoding="utf-8")); files=list(manifest.get("files",[]))
            if manifest.get("workspace_id")!=workspace.id: raise PermissionError("Task checkpoint belongs to another workspace")
        else: files=[]
        existing={entry["relative_path"] for entry in files}
        for relative in sorted(set(relative_paths)):
            if relative in existing: continue
            path=workspace.resolve(relative); entry={"relative_path":relative,"existed":path.exists()}
            if path.is_file():
                snapshot=folder/"files"/relative; snapshot.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,snapshot)
                entry["before_hash"]=content_hash(path)
            files.append(entry)
        manifest={"task_id":task_id,"workspace_id":workspace.id,"workspace_root":workspace.root_path,"files":files}
        temporary=folder/"manifest.json.tmp"
        temporary.write_text(json.dumps(manifest,indent=2),encoding="utf-8");temporary.replace(manifest_path);return manifest

    def rollback(self,workspace:Workspace,task_id:str) -> list[str]:
        folder=self.root/task_id; manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8")); restored=[]
        if manifest["workspace_id"]!=workspace.id or Path(manifest["workspace_root"])!=Path(workspace.root_path): raise PermissionError("Checkpoint belongs to another workspace")
        for entry in manifest["files"]:
            path=workspace.resolve(entry["relative_path"]); snapshot=folder/"files"/entry["relative_path"]
            if entry["existed"]:
                path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(snapshot,path)
            elif path.exists() and path.is_file(): path.unlink()
            restored.append(entry["relative_path"])
        return restored

    def cleanup(self,task_id:str):
        folder=self.root/task_id
        if folder.exists(): shutil.rmtree(folder)

    def exists(self,task_id:str) -> bool: return (self.root/task_id/"manifest.json").is_file()
