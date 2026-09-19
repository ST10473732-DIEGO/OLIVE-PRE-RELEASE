from __future__ import annotations

from dataclasses import dataclass,field
import hashlib
import time


@dataclass(slots=True)
class CodingTaskState:
    workspace_id:str
    phase:str="understand"
    iterations:int=0
    repeated_failures:int=0
    last_failure_fingerprint:str=""
    files_changed:list[str]=field(default_factory=list)
    validation_status:str="not_run"


class CodingAgentGuard:
    """Deterministic lifecycle limits around future/local-model coding plans."""
    PHASES=("understand","inspect","plan","edit","validate","diff","complete")

    def __init__(self,max_iterations:int=12,max_runtime_seconds:float=600):
        self.max_iterations=min(30,max(1,max_iterations));self.max_runtime_seconds=max(1,max_runtime_seconds)

    def may_continue(self,state:CodingTaskState,started:float,cancelled:bool=False) -> tuple[bool,str]:
        if cancelled:return False,"cancelled"
        if state.iterations>=self.max_iterations:return False,"iteration_limit"
        if time.monotonic()-started>=self.max_runtime_seconds:return False,"runtime_limit"
        if state.repeated_failures>=3:return False,"repeated_failure"
        return True,"continue"

    @staticmethod
    def observe_failure(state:CodingTaskState,output:str) -> None:
        fingerprint=hashlib.sha256(output.strip().encode("utf-8",errors="replace")).hexdigest()
        state.repeated_failures=state.repeated_failures+1 if fingerprint==state.last_failure_fingerprint else 1
        state.last_failure_fingerprint=fingerprint

    @staticmethod
    def untrusted_workspace_context(text:str) -> str:
        return "<workspace_content trust=\"untrusted\">\n"+text+"\n</workspace_content>"
