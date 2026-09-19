from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True,slots=True)
class LanguageServerCapability:
    language:str;provider:str;available:bool;features:tuple[str,...]=()
class LanguageServerProvider(Protocol):
    name:str
    def available(self)->bool:...
    def languages(self)->tuple[str,...]:...
class LanguageServerService:
    def __init__(self,providers=()):self.providers=list(providers)
    def capabilities(self):
        return [LanguageServerCapability(language,p.name,p.available(),("diagnostics","completion","definition")) for p in self.providers for language in p.languages()]
    def provider_for(self,language):
        return next((p for p in self.providers if p.available() and language in p.languages()),None)
