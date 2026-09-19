from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ..models import now_iso

@dataclass(frozen=True,slots=True)
class ApplicationObservation:
    run_session_id:str;process_id:int;window_title:str;captured_at:str;screenshot_path:str|None=None

class ApplicationObservationService:
    def observe(self,session,process_id,window_title,screenshot_path=None,authorized=False):
        if process_id!=session.process_id:raise PermissionError("Observation is limited to the RunSession process")
        screenshot=None
        if screenshot_path:
            if not authorized:raise PermissionError("Screenshot capture requires explicit authorization")
            screenshot=str(Path(screenshot_path))
        return ApplicationObservation(session.id,process_id,window_title,now_iso(),screenshot)

class VisionObservationValidator:
    STATUSES={"launched","expected_ui_visible","error_visible","uncertain"}
    @classmethod
    def parse(cls,value):
        if not isinstance(value,dict) or set(value)!={"status","summary","evidence"}:raise ValueError("Invalid vision observation")
        if value["status"] not in cls.STATUSES or not isinstance(value["summary"],str) or not isinstance(value["evidence"],list):raise ValueError("Invalid vision observation")
        return value
