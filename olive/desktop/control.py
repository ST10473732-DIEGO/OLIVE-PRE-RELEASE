from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True,slots=True)
class DesktopTarget:
    application:str
    window:str|None=None
    role:str|None=None
    name:str|None=None


@dataclass(frozen=True,slots=True)
class Observation:
    target:DesktopTarget
    state:dict
    untrusted_content:bool=True


class DesktopControlProvider(Protocol):
    name:str
    async def observe(self,target:DesktopTarget)->Observation:...
    async def act(self,target:DesktopTarget,action:str,arguments:dict)->dict:...


class DesktopControlService:
    """Compatibility contract. The live Qt runtime uses DesktopController and DesktopWorkflow."""
    def __init__(self,provider:DesktopControlProvider):self.provider=provider
    async def act_observe_verify(self,target:DesktopTarget,action:str,arguments:dict,verify):
        action_result=await self.provider.act(target,action,arguments)
        observation=await self.provider.observe(target)
        return {"action":action_result,"observation":observation,"verified":bool(verify(observation))}
