"""Read-only inventory. Never deletes or traverses directory links."""
import json
import os
from pathlib import Path
import shutil
import time
import httpx

root=Path(__file__).resolve().parents[1]
def measure(path):
    total=count=0;errors=[];stack=[path]
    while stack:
        directory=stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink() or getattr(entry,'is_junction',lambda:False)():continue
                        if entry.is_dir(follow_symlinks=False):stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):total+=entry.stat(follow_symlinks=False).st_size;count+=1
                    except OSError:errors.append(entry.path)
        except OSError:errors.append(str(directory))
    return {'path':str(path),'bytes':total,'files':count,'unreadable_count':len(errors)}
records=[measure(p) for p in root.iterdir() if p.is_dir() and not p.is_symlink()]
models=Path(os.environ.get('OLLAMA_MODELS',str(Path.home()/'.ollama/models')))
if models.is_dir():records.append(measure(models))
tags=httpx.get('http://127.0.0.1:11434/api/tags',timeout=10).json()['models']
output={'time':time.time(),'measurement':'logical file bytes; links skipped; not allocated-cluster or unique-model-blob counts',
        'root_free_bytes':shutil.disk_usage(root).free,'directories':records,'models':[{'tag':m['name'],'bytes':m['size'],'digest':m['digest'],'details':m.get('details',{})} for m in tags]}
(root/'.functionality-storage-inventory.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
print(json.dumps(output,indent=2))
