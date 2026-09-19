from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from .code_index_service import CODE_SUFFIXES,extract_symbols

@dataclass(frozen=True,slots=True)
class EditorLocation:
    line:int;column:int

class EditorIntelligenceService:
    def language(self,path):return CODE_SUFFIXES.get(Path(path).suffix.casefold(),"text")
    def location(self,text,offset):
        offset=max(0,min(len(text),offset));before=text[:offset];return EditorLocation(before.count("\n")+1,len(before.rsplit("\n",1)[-1])+1)
    def go_to_line(self,text,line):return sum(len(part) for part in text.splitlines(keepends=True)[:max(0,line-1)])
    def find(self,text,query,case_sensitive=False):
        flags=0 if case_sensitive else re.IGNORECASE
        return [(m.start(),m.end()) for m in re.finditer(re.escape(query),text,flags)]
    def replace(self,text,query,replacement,case_sensitive=False):return re.sub(re.escape(query),replacement,text,flags=0 if case_sensitive else re.IGNORECASE)
    def symbols(self,text,path):return extract_symbols(text,str(path),self.language(path))
    def auto_indent(self,previous_line,language):
        indent=previous_line[:len(previous_line)-len(previous_line.lstrip())]
        if (language=="python" and previous_line.rstrip().endswith(":")) or previous_line.rstrip().endswith(("{","[","(")):indent+="    "
        return indent
