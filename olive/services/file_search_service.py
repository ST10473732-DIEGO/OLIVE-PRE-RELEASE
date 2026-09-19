from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from fnmatch import fnmatch


@dataclass(frozen=True,slots=True)
class FileSearchQuery:
    filename: str = "*"
    extension: str | None = None
    minimum_size: int | None = None
    maximum_size: int | None = None
    modified_after: float | None = None
    modified_before: float | None = None
    recursive: bool = True
    limit: int = 200


class FileSearchService:
    def search(self,root:str|Path,query:FileSearchQuery) -> list[dict]:
        root=Path(root).resolve(strict=True)
        if not root.is_dir(): raise NotADirectoryError(root)
        iterator=root.rglob("*") if query.recursive else root.glob("*"); values=[]
        extension=(query.extension or "").casefold().lstrip(".")
        for path in iterator:
            if not path.is_file() or not fnmatch(path.name.casefold(),query.filename.casefold()): continue
            if extension and path.suffix.casefold().lstrip(".")!=extension: continue
            stat=path.stat()
            if query.minimum_size is not None and stat.st_size<query.minimum_size: continue
            if query.maximum_size is not None and stat.st_size>query.maximum_size: continue
            if query.modified_after is not None and stat.st_mtime<query.modified_after: continue
            if query.modified_before is not None and stat.st_mtime>query.modified_before: continue
            values.append({"path":str(path),"name":path.name,"size":stat.st_size,"modified":stat.st_mtime})
            if len(values)>=min(1000,max(1,query.limit)): break
        return sorted(values,key=lambda item:(-item["modified"],item["path"].casefold()))
