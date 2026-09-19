"""Incremental cache coordinator. Successful records survive partial failures."""
import hashlib
import json
import threading
import uuid
from .imap import MailboxSyncTransport
from .smtp import check, Cancelled
from .store import now, Conflict, WRITE_GUARD
from . import mime
from .remote_outcome import remote_outcome
from .folders import resolve


class Sync:
    def __init__(self,store,local,connections):
        self.store=store;self.local=local;self.connections=connections
        self.transport=MailboxSyncTransport();self.active={};self.lock=threading.RLock()

    def _client(self,connection):
        import imaplib
        try:return self.transport.connect(connection,self.connections.secret(connection))
        except imaplib.IMAP4.error:
            self.connections.invalidate_access(connection)
            raise

    def _reconcile_folder(self,db,connection_id,folder,validity,present=None):
        rows=db.execute("""SELECT * FROM records WHERE kind='message' AND json_extract(body,'$.connection_id')=?
          AND (json_extract(body,'$.remote.mailbox')=? OR EXISTS (SELECT 1 FROM json_each(json_extract(body,'$.remote_locations'))
          WHERE json_extract(value,'$.mailbox')=?))""",(connection_id,folder,folder)).fetchall()
        for row in rows:
            record=self.store.unpack(row);body=self.store.body(record);remote=body.get('remote') or {}
            locations=body.get('remote_locations',[])
            def state(location):
                if location.get('mailbox')!=folder:return location.get('state','present')
                if location.get('uidvalidity')!=validity:return 'uidvalidity_reset'
                if present is not None and location.get('uid') not in present:return 'missing_on_server'
                if present is not None:return 'present'
                return location.get('state','present')
            body['remote_locations']=[dict(v,state=state(v)) for v in locations] if locations else []
            current_state=state(remote)
            if remote.get('mailbox')==folder and current_state in {'uidvalidity_reset','missing_on_server'}:
                alternatives=[v for v in body['remote_locations'] if v['state']=='present']
                if alternatives:
                    chosen=alternatives[0]
                    body['remote']={k:chosen[k] for k in ('mailbox','uidvalidity','uid')}
                    if body.get('folder')==remote['mailbox']:body['folder']=chosen['mailbox']
                    body['remote_state']='cached'
                else:body['remote_state']=current_state
            elif remote.get('mailbox')==folder and present is not None and body.get('remote_state')=='missing_on_server':body['remote_state']='cached'
            if body!=self.store.body(record):self.store.save(db,'message',body,record['id'],record['revision'])

    def refresh(self,connection_id,folder='INBOX',limit=50,cancel=None,policy_guard=lambda:None,progress=lambda value:None):
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('Sync batch must contain 1–100 messages')
        cancel=cancel or threading.Event()
        with self.lock:
            if connection_id in self.active:raise Conflict('A sync is already running for this connection')
            self.active[connection_id]=cancel
        client=None;completed=0;last_uid=0;validity=None;state_record=None;flag_cursor=0
        try:
            progress({'connection_id':connection_id,'state':'connecting','count':0,'message':'Connecting to the selected account.'})
            connection=self.connections.get(connection_id,enabled=True)
            def guard():policy_guard();self.connections.check_revision(connection)
            check(cancel,guard);client=self._client(connection)
            folders=self.transport.folders(client)
            folder=resolve(folder,folders)
            validity=self.transport.select(client,folder)
            source='sync:'+connection_id+':'+folder
            with self.store.transaction() as db:
                row=db.execute('SELECT record_id FROM sources WHERE source=?',(source,)).fetchone()
                state_record=self.store.get(db,'sync',row[0]) if row else None
                last_uid=state_record['last_uid'] if state_record and state_record['uidvalidity']==validity else 0
                flag_cursor=state_record.get('flag_cursor',0) if state_record and state_record['uidvalidity']==validity else 0
                for item in folders:
                    key='folder:'+connection_id+':'+item['name']
                    found=db.execute('SELECT record_id FROM sources WHERE source=?',(key,)).fetchone()
                    if not found:
                        saved=self.store.save(db,'folder',dict(item,connection_id=connection_id,remote=True))
                        db.execute('INSERT INTO sources VALUES(?,?)',(key,saved['id']))
                    else:
                        previous=self.store.get(db,'folder',found[0])
                        body=dict(item,connection_id=connection_id,remote=True)
                        if body!=self.store.body(previous):self.store.save(db,'folder',body,previous['id'],previous['revision'])
                if state_record and state_record['uidvalidity']!=validity:
                    self._reconcile_folder(db,connection_id,folder,validity)
            check(cancel,guard)
            all_uids=self.transport.uids(client)
            if len(all_uids)>100000:raise ValueError('Mailbox exceeds the supported 100,000 UID discovery bound')
            new_uids=[uid for uid in all_uids if uid>last_uid]
            # Refresh a rotating bounded page of already cached flags. A local
            # annotation is not remote truth; conflicts remain visible.
            cached=[uid for uid in all_uids if uid<=last_uid]
            progress({'connection_id':connection_id,'state':'syncing','count':0,'message':'Checking cached flags and the next bounded header batch.'})
            start=flag_cursor if flag_cursor<len(cached) else 0
            for uid in cached[start:start+limit]:
                check(cancel,guard);flags=self.transport.metadata(client,uid)
                with self.store.transaction() as db:
                    found=db.execute('SELECT record_id FROM sources WHERE source=?',(f'imap:{connection_id}:{folder}:{validity}:{uid}',)).fetchone()
                    if found:
                        current=self.store.get(db,'message',found[0]);body=self.store.body(current)
                        if current.get('local_changes') and any(current.get(k)!=v for k,v in flags.items()):
                            body.update(remote_flags=flags,remote_state='flag_conflict')
                        else:body.update(flags,remote_flags=flags)
                        if body!=self.store.body(current):self.store.save(db,'message',body,current['id'],current['revision'])
                flag_cursor=start+cached[start:start+limit].index(uid)+1
            if flag_cursor>=len(cached):flag_cursor=0
            for uid in new_uids[:limit]:
                check(cancel,guard)
                fetched=self.transport.fetch(client,uid)
                check(cancel,guard)
                record=mime.parse(fetched['raw'])
                record.update(body_cached=False,read=fetched['read'],starred=fetched['starred'],remote_size=fetched['size'])
                saved=self.local.ingest(fetched['raw'],record,source=f'imap:{connection_id}:{folder}:{validity}:{uid}',
                                       connection_id=connection_id,folder=folder,remote={'mailbox':folder,'uidvalidity':validity,'uid':uid},provider_message_id=fetched.get('provider_message_id',''))
                with self.store.transaction() as db:
                    body=self.store.body(saved);body.update(read=fetched['read'],starred=fetched['starred'],remote_state='cached')
                    if not saved.get('text'):body['body_cached']=False
                    self.store.save(db,'message',body,saved['id'],saved['revision'])
                last_uid=uid;completed+=1
                progress({'connection_id':connection_id,'state':'syncing','count':completed,'message':f'Caching headers: {completed} of {min(len(new_uids),limit)} in this batch.'})
            check(cancel,guard)
            with self.store.transaction() as db:
                self._reconcile_folder(db,connection_id,folder,validity,set(all_uids))
            more=len(new_uids)>limit
            outcome={'state':'partial' if more else 'completed','count':completed,'more':more,'last_success':now(),
                     'message':'Batch cached; refresh to continue.' if more else 'Mailbox cache refreshed.'}
        except Exception as error:
            outcome={'state':'cancelled' if isinstance(error,Cancelled) else 'partial' if completed else 'failed',
                     'count':completed,'category':type(error).__name__,'message':'Earlier cached messages remain available; this refresh is not current.'}
        finally:
            if client:self.transport.close(client)
            with self.lock:self.active.pop(connection_id,None)
        if validity is not None:
            # Cancellation must not erase the outcome of already cached batches.
            token=WRITE_GUARD.set(None)
            try:
              with self.store.transaction() as db:
                body={'connection_id':connection_id,'mailbox':folder,'uidvalidity':validity,'last_uid':last_uid,'flag_cursor':flag_cursor,**outcome}
                if state_record:
                    if 'last_success' not in body:body['last_success']=state_record.get('last_success')
                    result=self.store.save(db,'sync',body,state_record['id'],state_record['revision'])
                else:
                    result=self.store.save(db,'sync',body)
                    db.execute('INSERT INTO sources VALUES(?,?)',('sync:'+connection_id+':'+folder,result['id']))
                return result
            finally:WRITE_GUARD.reset(token)
        return outcome

    def search_server(self,connection_id,folder,query,cancel,policy_guard):
        connection=self.connections.get(connection_id,enabled=True)
        def guard():policy_guard();self.connections.check_revision(connection)
        check(cancel,guard);client=self._client(connection)
        try:
            folder=resolve(folder,self.transport.folders(client))
            validity=self.transport.select(client,folder)
            check(cancel,guard);uids=self.transport.uids(client,query=query)
            results=[]
            for uid in uids[-50:]:
                check(cancel,guard);fetched=self.transport.fetch(client,uid)
                record=mime.parse(fetched['raw'])
                saved=self.local.ingest(fetched['raw'],record,source=f'imap:{connection_id}:{folder}:{validity}:{uid}',connection_id=connection_id,folder=folder,remote={'mailbox':folder,'uidvalidity':validity,'uid':uid},provider_message_id=fetched.get('provider_message_id',''))
                if not saved.get('text'):
                    with self.store.transaction() as db:
                        body=self.store.body(saved);body['body_cached']=False
                        self.store.save(db,'message',body,saved['id'],saved['revision'])
                results.append({'id':saved['id'],'subject':saved['subject'],'from':saved['from']})
            return {'items':results,'total':len(uids),'scope':'Server TEXT search; at most 50 matching headers cached','uidvalidity':validity}
        finally:self.transport.close(client)

    def folder_action(self,connection_id,action,name,new_name,cancel,policy_guard):
        connection=self.connections.get(connection_id,enabled=True)
        def guard():policy_guard();self.connections.check_revision(connection)
        check(cancel,guard);client=self._client(connection)
        try:
            known=[f['name'] for f in self.transport.folders(client)]
            if action=='rename' and (name not in known or new_name in known):raise ValueError('Select an existing source and unused destination mailbox')
            if action=='create' and name in known:raise ValueError('Mailbox already exists')
            with remote_outcome(self.store,connection_id,action,name):
                check(cancel,guard);self.transport.folder_action(client,action,name,new_name)
                if action=='rename':
                    with self.store.transaction() as db:
                        for row in db.execute("SELECT * FROM records WHERE json_extract(body,'$.connection_id')=?",(connection_id,)).fetchall():
                            r=self.store.unpack(row);body=self.store.body(r);changed=False
                            if r['kind']=='message' and (body.get('remote') or {}).get('mailbox')==name:
                                old_key=f"imap:{connection_id}:{name}:{body['remote']['uidvalidity']}:{body['remote']['uid']}"
                                new_key=f"imap:{connection_id}:{new_name}:{body['remote']['uidvalidity']}:{body['remote']['uid']}"
                                db.execute('UPDATE sources SET source=? WHERE source=? AND record_id=?',(new_key,old_key,r['id']))
                                body['remote']['mailbox']=new_name
                                if body.get('folder')==name:body['folder']=new_name
                                changed=True
                            if r['kind']=='folder' and body.get('name')==name:body['name']=new_name;changed=True
                            if r['kind']=='message' and any(v['mailbox']==name for v in body.get('remote_locations',[])):
                                for location in body['remote_locations']:
                                    if location['mailbox']==name:
                                        old_key=f"imap:{connection_id}:{name}:{location['uidvalidity']}:{location['uid']}"
                                        new_key=f"imap:{connection_id}:{new_name}:{location['uidvalidity']}:{location['uid']}"
                                        db.execute('UPDATE sources SET source=? WHERE source=? AND record_id=?',(new_key,old_key,r['id']))
                                        location['mailbox']=new_name;changed=True
                            if r['kind']=='sync' and body.get('mailbox')==name:body['mailbox']=new_name;changed=True
                            if changed:self.store.save(db,r['kind'],body,r['id'],r['revision'])
                        for prefix in ('folder:','sync:'):
                            old=prefix+connection_id+':'+name;new=prefix+connection_id+':'+new_name
                            for source,record_id in db.execute('SELECT source,record_id FROM sources').fetchall():
                                if source==old:
                                    db.execute('UPDATE sources SET source=? WHERE source=?',(new+source[len(old):],source))
                return {'state':'completed','action':action,'name':name,'new_name':new_name,'remote':True}
        finally:self.transport.close(client)

    def fetch_body(self,record_id,cancel,policy_guard):
        record=self.local.get(record_id)
        if record.get('body_cached'):return record
        remote=record.get('remote')
        if not remote:raise ValueError('This message has no remote body')
        connection=self.connections.get(record['connection_id'],enabled=True)
        def guard():policy_guard();self.connections.check_revision(connection)
        check(cancel,guard);client=self._client(connection)
        try:
            validity=self.transport.select(client,remote['mailbox'])
            if validity!=remote['uidvalidity']:raise Conflict('Mailbox UIDVALIDITY changed; refresh before fetching')
            fetched=self.transport.fetch(client,remote['uid'],body=True)
            check(cancel,guard);parsed=mime.parse(fetched['raw'])
            with self.store.transaction() as db:
                current=self.store.get(db,'message',record_id)
                if current['revision']!=record['revision']:raise Conflict('Message changed while fetching; reload it')
                for attachment in parsed['attachments']:
                    attachment['hash']=self.store.blob(db,attachment.pop('bytes'));attachment['id']=uuid.uuid4().hex
                body=self.store.body(current);body.update(parsed,raw_hash=self.store.blob(db,fetched['raw']),body_cached=True)
                return self.store.save(db,'message',body,record_id,record['revision'])
        finally:self.transport.close(client)

    def remote_action(self,record_id,revision,action,arguments,cancel,policy_guard):
        record=self.local.get(record_id)
        if record['revision']!=revision:raise Conflict('Message changed before remote operation')
        remote=record.get('remote')
        if not remote:raise ValueError('This is a local message; use local actions')
        connection=self.connections.get(record['connection_id'],enabled=True)
        def guard():policy_guard();self.connections.check_revision(connection)
        check(cancel,guard);client=self._client(connection)
        try:
            if self.transport.select(client,remote['mailbox'],readonly=False)!=remote['uidvalidity']:raise Conflict('Mailbox identity changed')
            check(cancel,guard)
            with remote_outcome(self.store,connection['id'],action,record_id):
                if action=='flags':
                    if set(arguments)-{'read','starred'}:raise ValueError('Unknown remote flag')
                    self.transport.flags(client,remote['uid'],**arguments)
                elif action=='move':
                    if set(arguments)!={'destination'}:raise ValueError('Specify the exact destination mailbox')
                    if arguments['destination'] not in [f['name'] for f in self.transport.folders(client)]:raise ValueError('Select an actual destination mailbox')
                    moved=self.transport.move(client,remote['uid'],arguments['destination'])
                else:raise ValueError('Unsupported remote operation; permanent deletion is not enabled')
                with self.store.transaction() as db:
                    current=self.store.get(db,'message',record_id);body=self.store.body(current)
                    if action=='flags':body.update(arguments,local_changes=False,remote_state='confirmed')
                    else:
                        body['remote_state']='moved_on_server'
                        if 'remote_locations' in body:
                            body['remote_locations']=[dict(v,state='moved') if v['mailbox']==remote['mailbox'] else v for v in body['remote_locations']]
                        if moved:
                            body.update(remote=moved,folder=moved['mailbox'],remote_state='confirmed',local_changes=False)
                            if 'remote_locations' in body:body['remote_locations'].append(dict(moved,state='present'))
                            key=f"imap:{connection['id']}:{moved['mailbox']}:{moved['uidvalidity']}:{moved['uid']}"
                            found=db.execute('SELECT record_id FROM sources WHERE source=?',(key,)).fetchone()
                            if not found:db.execute('INSERT INTO sources VALUES(?,?)',(key,record_id))
                    return self.store.save(db,'message',body,record_id,current['revision'])
        finally:self.transport.close(client)

    def cancel(self,connection_id):
        with self.lock:
            event=self.active.get(connection_id)
            if event:event.set()
        return {'state':'cancellation_requested' if event else 'idle'}

    def close(self):
        with self.lock:
            for event in self.active.values():event.set()
