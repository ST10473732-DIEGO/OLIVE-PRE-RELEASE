from __future__ import annotations
from pathlib import Path
import hashlib,json
from .code_index_service import CodeIndexService,IGNORED_PARTS

class RepositoryMapService:
    def __init__(self,code_index:CodeIndexService,cache_path:Path|None=None,repository=None):
        self.code_index=code_index;self.cache_path=cache_path;self.repository=repository;self._memory={};self._indexes={}
    def build(self,root:str|Path) -> dict:
        root=Path(root).resolve(strict=True);fingerprint=self._fingerprint(root)
        cached=self._memory.get(str(root))
        if cached and cached["fingerprint"]==fingerprint:return cached["map"]
        index=self.code_index.index(root);files=index.get("files",[]);languages={}
        self._indexes[str(root)]=index
        for item in files:languages[item["language"]]=languages.get(item["language"],0)+1
        important=[item["relative_path"] for item in files if Path(item["relative_path"]).name.casefold() in {"readme.md","pyproject.toml","package.json","main.py"} or Path(item["relative_path"]).suffix in {".sln",".csproj"}][:50]
        git_state=None
        if self.repository:
            try:git_state=self.repository.status(root)
            except (ValueError,OSError):git_state=None
        result={"root_name":root.name,"directories":sorted({Path(item["relative_path"]).parts[0] for item in files if len(Path(item["relative_path"]).parts)>1})[:100],"languages":languages,"important_files":important,"symbols":[symbol for item in files for symbol in item.get("symbols",[])][:300],"file_count":len(files),"fingerprint":fingerprint,"git":git_state}
        self._memory[str(root)]={"fingerprint":fingerprint,"map":result};return result
    def invalidate(self,root:str|Path):self._memory.pop(str(Path(root).resolve(strict=False)),None)
    def index(self,root:str|Path):
        resolved=str(Path(root).resolve(strict=True))
        self.build(resolved)
        return self._indexes[resolved]
    @staticmethod
    def _fingerprint(root:Path):
        values=[]
        for path in root.rglob("*"):
            if any(part in IGNORED_PARTS for part in path.relative_to(root).parts) or not path.is_file():continue
            try:stat=path.stat();values.append(f"{path.relative_to(root)}:{stat.st_size}:{stat.st_mtime_ns}")
            except OSError:continue
        return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()
