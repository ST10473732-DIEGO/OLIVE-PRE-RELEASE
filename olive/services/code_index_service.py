from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import ast
import hashlib
import json
import re

IGNORED_PARTS={".git",".venv","venv","node_modules","bin","obj","dist","build","__pycache__",".idea",".vs"}
CODE_SUFFIXES={".py":"python",".cs":"csharp",".js":"javascript",".ts":"typescript",".java":"java",".rs":"rust",
               ".json":"json",".toml":"toml",".yaml":"yaml",".yml":"yaml",".md":"markdown",".txt":"text"}


@dataclass(frozen=True,slots=True)
class CodeSymbol:
    name: str
    symbol_type: str
    relative_path: str
    language: str
    line_start: int
    line_end: int


@dataclass(slots=True)
class IndexedCodeFile:
    relative_path: str
    language: str
    content_hash: str
    modified_ns: int
    size: int
    symbols: list[CodeSymbol]


class CodeIndexService:
    SCHEMA_VERSION=1

    def __init__(self,index_path: Path | None=None): self.index_path=index_path

    def index(self,root: str|Path) -> dict:
        root=Path(root).resolve(strict=True); previous=self._load(); old={x["relative_path"]:x for x in previous.get("files",[])}
        files=[]; changed=0
        for path in self.iter_source_files(root):
            if self.index_path and path.resolve()==self.index_path.resolve(): continue
            rel=path.relative_to(root).as_posix(); stat=path.stat(); cached=old.get(rel)
            if cached and cached.get("modified_ns")==stat.st_mtime_ns and cached.get("size")==stat.st_size:
                files.append(cached); continue
            raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest(); text=raw.decode("utf-8",errors="replace")
            symbols=[asdict(item) for item in extract_symbols(text,rel,CODE_SUFFIXES[path.suffix.lower()])]
            files.append(asdict(IndexedCodeFile(rel,CODE_SUFFIXES[path.suffix.lower()],digest,stat.st_mtime_ns,stat.st_size,
                                                [CodeSymbol(**item) for item in symbols]))); changed+=1
        result={"schema_version":self.SCHEMA_VERSION,"root":str(root),"files":files,"changed_files":changed}
        if self.index_path:
            self.index_path.parent.mkdir(parents=True,exist_ok=True); tmp=self.index_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(result,indent=2),encoding="utf-8"); tmp.replace(self.index_path)
        return result

    def search_symbols(self,query: str,index: dict|None=None) -> list[dict]:
        words=set(re.findall(r"[a-z0-9_]+",query.casefold())); results=[]
        for file in (index or self._load()).get("files",[]):
            for symbol in file.get("symbols",[]):
                score=len(words & set(re.findall(r"[a-z0-9_]+",symbol["name"].casefold())))
                if score or query.casefold() in symbol["name"].casefold(): results.append((score,symbol))
        return [item for _,item in sorted(results,key=lambda pair:(-pair[0],pair[1]["relative_path"],pair[1]["line_start"]))]

    @staticmethod
    def iter_source_files(root: Path):
        for path in root.rglob("*"):
            if any(part in IGNORED_PARTS for part in path.relative_to(root).parts): continue
            if path.is_file() and path.suffix.lower() in CODE_SUFFIXES and path.stat().st_size<=2_000_000: yield path

    def _load(self):
        if not self.index_path or not self.index_path.exists(): return {"schema_version":self.SCHEMA_VERSION,"files":[]}
        try: return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError): return {"schema_version":self.SCHEMA_VERSION,"files":[]}


def extract_symbols(text: str,relative_path: str,language: str) -> list[CodeSymbol]:
    if language=="python":
        try:
            tree=ast.parse(text); result=[]
            for node in ast.walk(tree):
                if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
                    kind="class" if isinstance(node,ast.ClassDef) else "function"
                    result.append(CodeSymbol(node.name,kind,relative_path,language,node.lineno,getattr(node,"end_lineno",node.lineno)))
            return sorted(result,key=lambda item:item.line_start)
        except SyntaxError: return []
    patterns={"csharp":r"^\s*(?:public|private|internal|protected|static|async|sealed|abstract|partial|\s)+\s*(class|interface|record|enum|[\w<>\[\],?]+)\s+(\w+)\s*[({]",
              "javascript":r"^\s*(?:export\s+)?(?:async\s+)?(class|function)\s+(\w+)",
              "typescript":r"^\s*(?:export\s+)?(?:async\s+)?(class|function|interface|type)\s+(\w+)",
              "java":r"^\s*(?:public|private|protected|static|final|abstract|\s)*(class|interface|enum|[\w<>\[\]]+)\s+(\w+)\s*[({]"}
    pattern=patterns.get(language)
    if not pattern:return []
    results=[]
    for number,line in enumerate(text.splitlines(),1):
        match=re.match(pattern,line)
        if match: results.append(CodeSymbol(match.group(2),match.group(1),relative_path,language,number,number))
    return results
