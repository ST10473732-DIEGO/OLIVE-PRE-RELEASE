from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json,math,re

@dataclass(frozen=True,slots=True)
class CodeSearchResult:
    relative_path:str;language:str;symbol:str|None;symbol_type:str|None;line_start:int;line_end:int;score:float;method:str;content_hash:str

class CodeRetrievalService:
    def __init__(self,ollama=None,embedding_model=None,cache_path=None):
        self.ollama=ollama;self.embedding_model=embedding_model;self.cache_path=Path(cache_path) if cache_path else None;self._vectors={};self._text={};self._load()
    async def embed_index(self,workspace_id,index):
        pending=[];keys=[];root=Path(index.get("root","."))
        for file in index.get("files",[]):
            for symbol in file.get("symbols",[]) or [{"name":None,"symbol_type":None,"line_start":1,"line_end":1}]:
                key=(workspace_id,file["relative_path"],file["content_hash"],symbol.get("name"))
                if key not in self._vectors:
                    lines=(root/file["relative_path"]).read_text(encoding="utf-8",errors="replace").splitlines()
                    start=max(1,int(symbol.get("line_start",1)));end=min(len(lines),max(start,int(symbol.get("line_end",start))))
                    content=f"{file['relative_path']}\n{file['language']} {symbol.get('symbol_type','module')} {symbol.get('name') or ''}\n"+"\n".join(lines[start-1:end])[:12000]
                    self._text[key]=content;keys.append(key);pending.append(content)
        if pending and self.ollama and self.embedding_model:
            vectors=await self.ollama.embed_batched(self.embedding_model,pending)
            self._vectors.update(zip(keys,vectors));self._save()
        return len(pending)
    async def search(self,workspace_id,query,index,limit=8,use_semantic=True):
        tokens=set(re.findall(r"[a-z0-9_]+",query.casefold()));query_vector=None
        if use_semantic and self.ollama and self.embedding_model and self._vectors:query_vector=(await self.ollama.embed(self.embedding_model,[query]))[0]
        results=[]
        for file in index.get("files",[]):
            symbols=file.get("symbols",[]) or [{"name":None,"symbol_type":None,"line_start":1,"line_end":1}]
            for symbol in symbols:
                key=(workspace_id,file["relative_path"],file["content_hash"],symbol.get("name"))
                text=self._text.get(key,f"{file['relative_path']} {symbol.get('name') or ''}").casefold();words=set(re.findall(r"[a-z0-9_]+",text))
                exact=1.0 if query.casefold() in text else len(tokens&words)/max(1,len(tokens))
                semantic=_cosine(query_vector,self._vectors.get(key)) if query_vector else 0
                score=max(exact,.55*exact+.45*semantic)
                if score>0:results.append(CodeSearchResult(file["relative_path"],file["language"],symbol.get("name"),symbol.get("symbol_type"),symbol.get("line_start",1),symbol.get("line_end",1),round(score,6),"hybrid" if query_vector else "exact_symbol",file["content_hash"]))
        return sorted(results,key=lambda item:(-item.score,item.relative_path,item.line_start))[:limit]
    def _save(self):
        if not self.cache_path:return
        self.cache_path.parent.mkdir(parents=True,exist_ok=True);tmp=self.cache_path.with_suffix(".tmp")
        rows=[{"key":list(key),"vector":vector,"text":self._text.get(key,"")} for key,vector in self._vectors.items()]
        tmp.write_text(json.dumps({"schema_version":1,"rows":rows}),encoding="utf-8");tmp.replace(self.cache_path)
    def _load(self):
        if not self.cache_path or not self.cache_path.exists():return
        try:
            value=json.loads(self.cache_path.read_text(encoding="utf-8"))
            for row in value.get("rows",[]):key=tuple(row["key"]);self._vectors[key]=row["vector"];self._text[key]=row.get("text","")
        except (OSError,json.JSONDecodeError,KeyError,TypeError):self._vectors={};self._text={}

def _cosine(a,b):
    if not a or not b or len(a)!=len(b):return 0.0
    dot=sum(x*y for x,y in zip(a,b));den=math.sqrt(sum(x*x for x in a))*math.sqrt(sum(y*y for y in b))
    return dot/den if den else 0.0
