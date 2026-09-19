from __future__ import annotations

from dataclasses import asdict,dataclass,field
from pathlib import Path
import uuid

from ..models import now_iso
from ..storage.json_store import JsonStore
from ..workspace import Workspace


@dataclass(slots=True)
class TerminalSession:
    workspace_id:str
    working_directory:str
    environment:str="powershell"
    id:str=field(default_factory=lambda:str(uuid.uuid4()))
    created_at:str=field(default_factory=now_iso)
    updated_at:str=field(default_factory=now_iso)
    commands:list[dict]=field(default_factory=list)


class TerminalSessionService:
    def __init__(self,path:Path):self.store=JsonStore(path)

    def create(self,workspace:Workspace,working_directory:str=".",environment:str="powershell") -> TerminalSession:
        if environment not in {"powershell","cmd","python"}:raise ValueError("Unsupported terminal environment")
        session=TerminalSession(workspace.id,str(workspace.resolve(working_directory)),environment); self._save(session); return session

    def record(self,session_id:str,command_name:str,exit_code:int,duration_ms:float) -> TerminalSession:
        values=self.load_all(); session=values[session_id]
        session.commands.append({"command":command_name[:100],"exit_code":exit_code,"duration_ms":duration_ms,"time":now_iso()})
        session.updated_at=now_iso(); self._write(values.values()); return session

    def load_all(self):
        value=self.store.read({"schema_version":1,"sessions":[]}); result={}
        for item in value.get("sessions",[]):
            session=TerminalSession(**{key:item[key] for key in TerminalSession.__dataclass_fields__ if key in item}); result[session.id]=session
        return result

    def _save(self,session): values=self.load_all();values[session.id]=session;self._write(values.values())
    def _write(self,values):self.store.write({"schema_version":1,"sessions":[asdict(item) for item in values]})
