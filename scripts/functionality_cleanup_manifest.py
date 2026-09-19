"""Prepare a read-only local disposal manifest; never delete model blobs or data."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
inventory=json.loads((root/'.functionality-storage-inventory.json').read_text(encoding='utf-8'))
model_store=next(item['path'] for item in inventory['directories'] if item['path'].replace('\\','/').endswith('/.ollama/models'))
optional=[]
for model in inventory['models']:
    if model['tag'] in {'llava:34b','dolphin-mixtral:8x7b'}:
        optional.append({**model,'store_path':model_store,'approval':'required; not approved',
                         'command':['ollama','rm',model['tag']],
                         'reason':'Not selected by any current public preset or active coding policy; retained as an optional legacy model.',
                         'dependencies':'Old chat/model choices may still name this model. No such user records are deleted or rewritten. Shared blobs are managed only by Ollama.',
                         'limitation':'Not benchmarked for replacement parity. Tag size is not a promise of reclaimed physical bytes.'})
manifest={'version':1,'status':'proposal only; no deletion performed','inventory_time':inventory['time'],
          'optional_model_disposal':optional,
          'keep':{item['path']:item['bytes'] for item in inventory['directories']},
          'protected':'All profiles, credentials, source, active toolchains, embedding/vision components, current evidence, Git and recovery copies remain.',
          'reclaimed_bytes':0}
(root/'.functionality-cleanup-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'manifest':str(root/'.functionality-cleanup-manifest.json'),'optional_model_tags':[item['tag'] for item in optional],'reclaimed_bytes':0}))
