from __future__ import annotations
from dataclasses import dataclass,field
from ..models import now_iso
import time,uuid

@dataclass(slots=True)
class BuildSession:
    workspace_id:str;state:str="idle";id:str=field(default_factory=lambda:str(uuid.uuid4()));started_at:str|None=None;ended_at:str|None=None;duration_ms:float|None=None;_started:float=field(default=0,repr=False)
class BuildSessionService:
    def __init__(self):self.active={};self.history=[]
    def start(self,workspace_id):
        if workspace_id in self.active:raise RuntimeError("A build is already running for this workspace")
        session=BuildSession(workspace_id,"building",started_at=now_iso());session._started=time.perf_counter();self.active[workspace_id]=session;return session
    def finish(self,session,succeeded):
        session.state="succeeded" if succeeded else "failed";session.ended_at=now_iso();session.duration_ms=round((time.perf_counter()-session._started)*1000,2)
        self.active.pop(session.workspace_id,None);self.history.append(session);return session
