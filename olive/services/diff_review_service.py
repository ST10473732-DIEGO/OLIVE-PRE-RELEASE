from __future__ import annotations
from dataclasses import dataclass
import re

@dataclass(frozen=True,slots=True)
class FileDiffSummary:
    path:str;added:int;removed:int
class DiffReviewService:
    def summarize(self,diff):
        results=[];current=None;added=removed=0
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                if current:results.append(FileDiffSummary(current,added,removed))
                current=line[6:];added=removed=0
            elif current and line.startswith("+") and not line.startswith("+++"):added+=1
            elif current and line.startswith("-") and not line.startswith("---"):removed+=1
        if current:results.append(FileDiffSummary(current,added,removed))
        return results
    def action_preview(self,modify=(),create=(),validation=()):
        return {"modify":sorted(set(modify)),"create":sorted(set(create)),"validation":list(validation)}
