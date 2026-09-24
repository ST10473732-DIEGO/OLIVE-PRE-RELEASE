"""Bounded multi-effect requests, preserving literal local-user provenance.

Splitting is only an optimization for explicit sequential clauses. Each clause
still requires normal scope validation or semantic interpretation. Quoted text
and source blocks are never promoted to commands. A failed/uncertain effect ends
this plan; no replanning can silently replay it through another application.
"""
from dataclasses import dataclass
import re
from .task_authority import direct_scope

@dataclass(frozen=True)
class DesktopPlan:
    original: str
    clauses: tuple[str,...]


def explicit_plan(request):
    if not isinstance(request,str) or not 1 <= len(request) <= 4000 or '```' in request:
        return None
    parts=[];start=0;quote=None;i=0
    while i<len(request):
        char=request[i]
        if quote:
            if char==quote and (i==0 or request[i-1]!='\\'):quote=None
        elif char in {'"',"'"} and (i==0 or not request[i-1].isalnum()):quote=char
        else:
            match=re.match(r'(?:;\s*(?:then\s+)?|,\s*then\s+|\s+and then\s+)',request[i:],re.I)
            if match:
                parts.append(request[start:i].strip());i+=len(match.group());start=i;continue
        i+=1
    if quote:return None
    parts.append(request[start:].strip())
    if not 2 <= len(parts) <= 8 or any(not p for p in parts):return None
    try:direct_scope(parts[0])
    except ValueError:return None
    return DesktopPlan(request,tuple(parts))
