"""Versioned selective-sync boundary; execution and credentials are never records."""
from dataclasses import dataclass
import hashlib
import json
import uuid

COLLECTIONS=frozenset({'chat_messages','notes','calendar_events','tasks','research_sessions','document_references'})
LOCAL_CAPABILITIES=frozenset({'chat.local_inference','chat.remote_inference','documents.read_selected','studio.run_local','browser.read_selected','mail.compose_local','desktop.control_local'})
FORBIDDEN=frozenset({'credentials','vault','access_token','refresh_token','password','cookie','outbox','pending_approval','execution_queue','terminal_command','live_database'})

def stable_id(profile_namespace,collection,source_id):
    if collection not in COLLECTIONS or not isinstance(source_id,str) or not 1<=len(source_id)<=200:raise ValueError('Unsupported sync identity')
    return str(uuid.uuid5(uuid.UUID(profile_namespace),collection+':'+source_id))

def bounded_data(value):
    def inspect(item,depth=0):
        if depth>16:raise ValueError('Sync data nesting exceeds limit')
        if isinstance(item,dict):
            if any(str(key).casefold() in FORBIDDEN for key in item):raise ValueError('Device-local authority or credentials cannot be synchronized')
            for child in item.values():inspect(child,depth+1)
        elif isinstance(item,list):
            for child in item:inspect(child,depth+1)
        elif item is not None and type(item) not in (str,int,float,bool):raise ValueError('Invalid portable value')
    inspect(value)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    if len(raw)>256_000:raise ValueError('Sync record exceeds 256 KB; attachments use separately authorized blob transfer')
    return raw

@dataclass(frozen=True)
class RecordEnvelope:
    collection:str
    record_id:str
    revision:int
    base_revision:int
    device_id:str
    deleted:bool
    data:dict
    schema_version:int=1
    # Additive v1 fields: legacy records have an unknown update instant (0).
    # device_id is the updating device; collection is the record kind.
    updated_at:int=0
    payload_version:int=1

    def validate(self):
        if type(self.updated_at) is not int or not 0<=self.updated_at<=253402300799:raise ValueError('Invalid update instant')
        if type(self.payload_version) is not int or self.payload_version!=1:raise ValueError('Unsupported payload version')
        if self.schema_version!=1 or self.collection not in COLLECTIONS:raise ValueError('Unsupported sync record schema')
        uuid.UUID(self.record_id);uuid.UUID(self.device_id)
        if type(self.revision) is not int or type(self.base_revision) is not int or self.base_revision<0 or self.revision<=self.base_revision:raise ValueError('Invalid revision ancestry')
        if type(self.deleted) is not bool or not isinstance(self.data,dict):raise ValueError('Invalid sync record')
        if self.deleted and self.data:raise ValueError('Deletion tombstones contain no user payload')
        bounded_data(self.data);return self

    def content_hash(self):
        self.validate();return hashlib.sha256(bounded_data({'collection':self.collection,'id':self.record_id,'deleted':self.deleted,'data':self.data})).hexdigest()

def reconcile(current,incoming):
    """Return a decision, never perform storage or side effects."""
    incoming.validate()
    if current is None:return 'apply' if incoming.base_revision==0 else 'missing_history'
    current.validate()
    if (current.collection,current.record_id)!=(incoming.collection,incoming.record_id):raise ValueError('Different record identities')
    if current.revision==incoming.revision and current.content_hash()==incoming.content_hash():return 'duplicate'
    if current.revision==incoming.base_revision:return 'apply'
    # No last-writer-wins loss: edits/deletes from diverging offline histories require review.
    return 'conflict'

@dataclass(frozen=True)
class DeviceGrant:
    device_id:str
    public_key_fingerprint:str
    collections:frozenset[str]
    capabilities:frozenset[str]
    revoked:bool=False

    def allows(self,collection,capability=None):
        uuid.UUID(self.device_id)
        if not self.collections<=COLLECTIONS or not self.capabilities<=LOCAL_CAPABILITIES:raise ValueError('Unsupported device grant')
        if len(self.public_key_fingerprint)!=64 or any(c not in '0123456789abcdef' for c in self.public_key_fingerprint):raise ValueError('Invalid device key fingerprint')
        return not self.revoked and collection in self.collections and (capability is None or capability in self.capabilities)
