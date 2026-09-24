"""Explicit owner-requested setup, never invoked by a model or ordinary startup."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import uuid
from ..storage.settings_repository import SettingsRepository
from .owner import owner_identity

VERSION=1

def migrate(profile,receipt,restore=False):
    profile=Path(profile).resolve();receipt=Path(receipt)
    repository=SettingsRepository(profile/'settings.json');settings=repository.load()
    if restore:
        saved=json.loads(receipt.read_text())
        if saved['profile']!=str(profile) or saved['owner_identity']!=owner_identity():raise PermissionError('Migration belongs to another installation owner')
        if settings.get('owner_installation')!=saved['new_installation'] or settings.get('owner_mode') is not True:raise ValueError('Owner configuration changed after migration; preserve current state')
        for key,value in saved['previous'].items():
            if value is None:settings.pop(key,None)
            else:settings[key]=value
        repository.save(settings)
        return {'version':VERSION,'state':'restored'}
    if receipt.exists():
        saved=json.loads(receipt.read_text())
        if saved['profile']!=str(profile) or saved['owner_identity']!=owner_identity():raise PermissionError('Migration receipt mismatch')
        return {'version':VERSION,'state':'already_recorded','enabled':settings.get('owner_mode') is True}
    identity=settings.get('owner_installation') or {'id':uuid.uuid4().hex,'owner':owner_identity()}
    if identity.get('owner')!=owner_identity():raise PermissionError('Installation belongs to another owner')
    saved={'migration_version':VERSION,'profile':str(profile),'owner_identity':owner_identity(),
           'timestamp':datetime.now(timezone.utc).isoformat(),'previous':{k:settings.get(k) for k in ('owner_mode','owner_installation')},
           'new_value':True,'new_installation':identity,'authority':'Explicit installation owner request'}
    receipt.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(saved,f,indent=2);f.flush();os.fsync(f.fileno())
    settings.update(owner_mode=True,owner_installation=identity);repository.save(settings)
    return {'version':VERSION,'state':'enabled','installation_id':identity['id']}
