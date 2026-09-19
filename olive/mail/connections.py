"""Explicit user-owned connection configuration; secrets stay in the existing vault."""
import ssl
import uuid
from .mime import addresses, text
from .store import Conflict


def validate_config(body):
    allowed={'name','sender','username','smtp','imap','sync_enabled','sent_folder','sent_copy','ca_pem'}
    if not isinstance(body,dict) or set(body)-allowed:raise ValueError('Unknown Mail connection setting')
    result={'name':text(body.get('name',''),120,header=True),'sender':text(body.get('sender',''),320,header=True),
            'username':text(body.get('username',''),320,header=True),'sync_enabled':body.get('sync_enabled',False),
            'sent_folder':text(body.get('sent_folder',''),300,header=True),'sent_copy':body.get('sent_copy',False),
            'ca_pem':text(body.get('ca_pem',''),32000)}
    if not result['name']:raise ValueError('Name this connection')
    if result['sender']:result['sender']=addresses([result['sender']])[0]
    if type(result['sync_enabled']) is not bool or type(result['sent_copy']) is not bool:raise ValueError('Invalid connection preference')
    if result['ca_pem']:
        # Additional trust belongs only to this explicitly reviewed connection.
        # Verification and hostname matching cannot be disabled.
        context=ssl.create_default_context();context.load_verify_locations(cadata=result['ca_pem'])
    for protocol in ('smtp','imap'):
        endpoint=body.get(protocol)
        if endpoint is None:result[protocol]=None;continue
        if not isinstance(endpoint,dict) or set(endpoint)!={'host','port','tls'}:raise ValueError('Invalid mail endpoint')
        host=text(endpoint['host'],253,header=True)
        if not host or any(c in host for c in '/\\ @\t:#?'):raise ValueError('Use a server hostname or IPv4 address')
        if type(endpoint['port']) is not int or not 1<=endpoint['port']<=65535:raise ValueError('Invalid mail port')
        if endpoint['tls'] not in {'tls','starttls'}:raise ValueError('Certificate-validated TLS is required')
        result[protocol]={'host':host,'port':endpoint['port'],'tls':endpoint['tls']}
    if not result['smtp'] and not result['imap']:raise ValueError('Configure SMTP, IMAP or both')
    return result


def tls_context(connection):
    context=ssl.create_default_context()
    if connection.get('ca_pem'):context.load_verify_locations(cadata=connection['ca_pem'])
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    return context


class Connections:
    def __init__(self,store,vault):self.store=store;self.vault=vault;self.google=None

    def list(self):
        with self.store.transaction() as db:
            items=self.store.list(db,'connection',limit=20)
            for c in items:
                rows=db.execute("SELECT * FROM records WHERE kind IN ('sync','annotation') AND json_extract(body,'$.connection_id')=? ORDER BY updated_at DESC LIMIT 30",(c['id'],)).fetchall()
                records=[self.store.unpack(r) for r in rows]
                c['sync_status']=next(({k:r.get(k) for k in ('state','last_success','count','category','mailbox')} for r in records if r['kind']=='sync'),None)
                c['test_status']=next(({k:r.get(k) for k in ('results','configuration_revision','updated_at')} for r in records if r.get('type')=='connection_test'),None)
            return {'items':items}

    def record_test(self,connection,results):
        with self.store.transaction() as db:
            key='connection-test:'+connection['id'];found=db.execute('SELECT record_id FROM sources WHERE source=?',(key,)).fetchone()
            old=self.store.get(db,'annotation',found[0]) if found else None
            body={'type':'connection_test','connection_id':connection['id'],'configuration_revision':connection['revision'],'results':results}
            record=self.store.save(db,'annotation',body,old['id'] if old else None,old['revision'] if old else None)
            if not old:db.execute('INSERT INTO sources VALUES(?,?)',(key,record['id']))

    def get(self,identity,*,enabled=False):
        with self.store.transaction() as db:record=self.store.get(db,'connection',identity)
        if enabled and not record['enabled']:raise PermissionError('This mail connection is disconnected or requires review')
        return record

    def save(self,body,record_id=None,revision=None):
        config=validate_config(body)
        with self.store.transaction() as db:
            old=self.store.get(db,'connection',record_id) if record_id else None
            if old and old.get('auth_type')=='google_oauth':
                if any(config[k]!=old[k] for k in ('sender','username','smtp','imap','ca_pem')):
                    raise ValueError('Google identity and endpoints are provider-validated; authorize another account instead')
                config.update(auth_type='google_oauth',provider='gmail',validated_senders=old['validated_senders'])
            # Every edit invalidates submission approvals; no remembered approval
            # can silently repoint this immutable configuration revision.
            config.update(enabled=False,state='disconnected',credential_ref=old.get('credential_ref') if old else None,
                          capabilities={},last_sync=None)
            return self.store.save(db,'connection',config,record_id,revision)

    def store_secret(self,record_id,revision,secret):
        reference='mail-'+uuid.uuid4().hex;written=False;old=None
        try:
            with self.store.transaction() as db:
                old=self.store.get(db,'connection',record_id)
                if old['revision']!=revision:raise Conflict('Connection changed before credential entry')
                self.vault.put(reference,secret);written=True
                body=self.store.body(old);body.update(credential_ref=reference,enabled=False,state='disconnected')
                result=self.store.save(db,'connection',body,record_id,revision)
        except BaseException:
            if written:self.vault.remove(reference)
            raise
        if old.get('credential_ref'):self.vault.remove(old['credential_ref'])
        return result

    def secret(self,connection):
        if connection.get('auth_type')=='google_oauth':
            if not self.google:raise ValueError('Google OAuth runtime is unavailable')
            return self.google.access_token(connection)
        if not connection.get('username'):return ''
        if not connection.get('credential_ref'):raise PermissionError('Store credentials for this connection before authenticating')
        return self.vault.read_for_provider(connection['credential_ref'])

    def invalidate_access(self,connection):
        if self.google and connection.get('auth_type')=='google_oauth':
            with self.google.lock:self.google.cache.pop(connection['id'],None)

    def change_state(self,record_id,revision,enabled,remove_credentials=False):
        with self.store.transaction() as db:
            old=self.store.get(db,'connection',record_id)
            if old['revision']!=revision:raise Conflict('Connection changed')
            body=self.store.body(old)
            if remove_credentials and body.get('credential_ref'):
                self.vault.remove(body['credential_ref']);body['credential_ref']=None;enabled=False
            body.update(enabled=enabled,state='ready' if enabled else 'disconnected')
            return self.store.save(db,'connection',body,record_id,revision)

    def check_revision(self,connection):
        current=self.get(connection['id'],enabled=True)
        if current['revision']!=connection['revision']:raise Conflict('Connection changed during this operation')

    def remove_cache(self,connection_id,revision):
        with self.store.transaction() as db:
            connection=self.store.get(db,'connection',connection_id)
            if connection['revision']!=revision or connection['enabled']:raise Conflict('Disconnect this exact connection before removing cached content')
            # Keep stable source IDs/relationships as explicit uncached tombstones.
            # Native drafts, imported messages and proposal records are retained.
            count=0
            for row in db.execute("SELECT * FROM records WHERE kind='message' AND json_extract(body,'$.connection_id')=?",(connection_id,)).fetchall():
                record=self.store.unpack(row)
                if not record.get('remote'):continue
                body=self.store.body(record);body.update(text='',html='',attachments=[],raw_hash='',body_cached=False,remote_state='cache_removed')
                self.store.save(db,'message',body,record['id'],record['revision']);count+=1
            # Remove only blobs no longer referenced anywhere (draft snapshots and
            # original imported sources remain independently owned).
            referenced=set()
            for row in db.execute('SELECT body FROM records'):
                import json
                body=json.loads(row[0]);referenced.add(body.get('raw_hash',''))
                referenced.update(a.get('hash','') for a in body.get('attachments',[]))
            for row in db.execute('SELECT hash FROM blobs').fetchall():
                if row[0] not in referenced:db.execute('DELETE FROM blobs WHERE hash=?',(row[0],))
            return {'state':'completed','removed_bodies':count,'message':'Cached bodies removed; stable message references and native drafts retained.'}
