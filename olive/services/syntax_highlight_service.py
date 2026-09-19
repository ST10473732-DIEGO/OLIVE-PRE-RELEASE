from __future__ import annotations
from dataclasses import dataclass
import re

LANGUAGE_KEYWORDS={
 "python":{"def","class","return","if","else","elif","for","while","try","except","import","from","async","await","True","False","None"},
 "csharp":{"class","interface","record","public","private","protected","internal","static","async","await","return","new","using","namespace","true","false","null"},
 "javascript":{"function","class","const","let","var","return","import","export","async","await","true","false","null"},
 "typescript":{"function","class","interface","type","const","let","return","import","export","async","await","true","false","null"},
 "java":{"class","interface","enum","public","private","protected","static","final","return","new","package","import","true","false","null"},
}
@dataclass(frozen=True,slots=True)
class HighlightToken:
    text:str;kind:str
class SyntaxHighlightService:
    def tokenize(self,text,language):
        keywords=LANGUAGE_KEYWORDS.get(language,set());tokens=[]
        pattern=re.compile(r"(//[^\n]*|\#[^\n]*|/\*[\s\S]*?\*/|\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|\b\w+\b|\s+|.)")
        for match in pattern.finditer(text):
            value=match.group(0)
            kind="comment" if value.startswith(("#","//","/*")) else "string" if value[:1] in {"\"","'"} else "keyword" if value in keywords else "number" if value.isdigit() else "plain"
            tokens.append(HighlightToken(value,kind))
        return tokens
