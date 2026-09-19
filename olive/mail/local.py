"""Local authoritative drafts/imports, bounded queries and provenance links."""
from copy import deepcopy
import hashlib
import json
import mimetypes
from pathlib import Path
import uuid
from . import mime
from .store import MailStore, Conflict, now

from .folders import FOLDERS, ROLE_SQL, role, match_sql


class LocalMail:
    def __init__(self, store):
        self.store=store
        self.previews={}

    def folders(self, connection_id=''):
        mime.text(connection_id,80)
        with self.store.transaction() as db:
            custom=self.store.list(db,'folder')
            counts={name:0 for name in FOLDERS}
            where="kind IN ('message','draft')";args=[]
            if connection_id:
                where+=" AND json_extract(body,'$.connection_id')=?";args.append(connection_id)
            for folder,count in db.execute('SELECT '+ROLE_SQL+',COUNT(*) FROM records WHERE '+where+' GROUP BY '+ROLE_SQL,args):
                counts[folder]=count
            for name in FOLDERS:
                counts[name]=db.execute('SELECT COUNT(*) FROM records WHERE '+where+' AND '+match_sql(),[*args,*([name]*4)]).fetchone()[0]
            counts['Outbox']=db.execute("SELECT COUNT(*) FROM records WHERE kind='submission' AND json_extract(body,'$.state') IN ('prepared','submitting','outcome_uncertain')"+(" AND json_extract(body,'$.connection_id')=?" if connection_id else ''),args).fetchone()[0]
            for item in custom:
                item['role']=role(item['name'],item.get('flags',()))
                item['count']=db.execute("SELECT COUNT(*) FROM records WHERE kind IN ('message','draft') AND json_extract(body,'$.connection_id')=? AND "+match_sql(),[item.get('connection_id',''),*([item['name']]*4)]).fetchone()[0]
            return {'items':[{'id':name,'name':name,'connection_id':'','count':counts.get(name,0)} for name in FOLDERS]+custom}

    def search(self, query='', folder='', connection_id='', limit=50, offset=0, **filters):
        mime.text(query,500);mime.text(folder,300);mime.text(connection_id,80)
        if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or not 0<=offset<=100000:
            raise ValueError('Invalid Mail page')
        if set(filters)-{'read','starred','has_attachments','after','before','project_id','thread_id','sender','recipient'}:
            raise ValueError('Unknown Mail filter')
        clauses=["kind IN ('message','draft')"];args=[]
        if query:
            clauses.append("(casefold(json_extract(body,'$.subject')||' '||json_extract(body,'$.from')||' '||json_extract(body,'$.to')||' '||json_extract(body,'$.cc')||' '||json_extract(body,'$.text')) LIKE ? ESCAPE '\\')")
            args.append('%'+query.casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        for key,value in [('folder',folder),('connection_id',connection_id),*filters.items()]:
            if value=='' or value is None:continue
            if key in {'read','starred','has_attachments'}:
                if type(value) is not bool:raise ValueError('Invalid Mail flag')
                clauses.append("json_array_length(json_extract(body,'$.attachments'))"+('>0' if value else '=0') if key=='has_attachments' else f"json_extract(body,'$.{key}')=?")
                if key!='has_attachments':args.append(int(value))
            elif key in {'after','before'}:
                mime.text(value,50);clauses.append("COALESCE(json_extract(body,'$.sent_at'),json_extract(body,'$.received_at'))"+('>=?' if key=='after' else '<?'));args.append(value)
            elif key=='sender':
                address=mime.addresses([value])[0]
                clauses.append("mail_sender(json_extract(body,'$.from'))=?")
                args.append(address.casefold())
            elif key=='recipient':
                address=mime.addresses([value])[0]
                clauses.append("EXISTS (SELECT 1 FROM json_each(json_extract(body,'$.to')) WHERE casefold(value)=?)")
                args.append(address.casefold())
            elif key=='folder':
                clauses.append(match_sql());args.extend([value]*4)
            else:
                mime.text(value,300);clauses.append(f"json_extract(body,'$.{key}')=?");args.append(value)
        where=' AND '.join(clauses)
        with self.store.transaction() as db:
            total=db.execute('SELECT count(*) FROM records WHERE '+where,args).fetchone()[0]
            rows=db.execute('SELECT * FROM records WHERE '+where+' ORDER BY updated_at DESC,id LIMIT ? OFFSET ?',[*args,limit,offset])
            items=[]
            for row in rows:
                item=self.store.unpack(row)
                summary={key:value for key,value in item.items() if key in {'id','kind','revision','subject','from','to','folder','read','starred','connection_id','project_id','thread_id','remote_state','submission_state'}}
                summary['attachments']=[{k:a[k] for k in ('id','name','size')} for a in item['attachments']]
                if items and len(json.dumps(items+[summary]).encode())>650000:break
                items.append(summary)
        return {'items':items,'total':total,'scope':'Local imports, drafts and cached mail only'}

    def get(self, identity):
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM records WHERE id=? AND kind IN ('message','draft')",(identity,)).fetchone()
            record=self.store.unpack(row)
            operation=db.execute("SELECT body FROM records WHERE kind='annotation' AND json_extract(body,'$.type')='remote_operation' AND json_extract(body,'$.target')=? ORDER BY updated_at DESC LIMIT 1",(identity,)).fetchone()
            if operation:
                detail=json.loads(operation[0])
                record['remote_operation']={'state':detail['state'],'action':detail['action']}
            return record

    def recipients(self,query,connection_id=''):
        from email.utils import getaddresses
        mime.text(query,200);mime.text(connection_id,80)
        if len(query.strip())<2:return {'items':[]}
        where="kind IN ('message','draft')";args=[]
        if connection_id:
            where+=" AND json_extract(body,'$.connection_id')=?";args.append(connection_id)
        items={}
        with self.store.transaction() as db:
            # Only bounded participant headers are examined; BCC and bodies are not suggestions.
            rows=db.execute("SELECT json_extract(body,'$.from'),json_extract(body,'$.to'),json_extract(body,'$.cc') FROM records WHERE "+where+' ORDER BY updated_at DESC LIMIT 200',args)
            for sender,to,cc in rows:
                for name,address in getaddresses([sender or '',*(json.loads(to or '[]')),*(json.loads(cc or '[]'))]):
                    try:validated=mime.addresses([address])
                    except ValueError:continue
                    if validated and query.casefold() in (name+' '+address).casefold():
                        items.setdefault(address.casefold(),{'address':address,'name':name,'origin':'Recent message participant'})
                    if len(items)>=20:return {'items':list(items.values())}
        return {'items':list(items.values())}

    def thread(self,record_id):
        record=self.get(record_id)
        return self.search(connection_id=record['connection_id'],thread_id=record['thread_id'],limit=30)

    def create_folder(self,name):
        mime.text(name,100,header=True)
        name=name.strip()
        if not name or name in FOLDERS:raise ValueError('Choose a distinct local folder name')
        with self.store.transaction() as db:
            existing=db.execute("SELECT id FROM records WHERE kind='folder' AND json_extract(body,'$.name')=? AND json_extract(body,'$.connection_id')=''",(name,)).fetchone()
            if existing:raise ValueError('This local folder already exists')
            return self.store.save(db,'folder',{'name':name,'connection_id':'','remote':False})

    def discard(self,record_id,revision):
        with self.store.transaction() as db:
            record=self.store.get(db,'draft',record_id)
            if record['submission_state'] in {'submitting','outcome_uncertain'}:raise Conflict('Resolve or retain the uncertain submission before discarding this draft')
            body=self.store.body(record);body.update(folder='Trash',discarded=True)
            return self.store.save(db,'draft',body,record_id,revision)

    def save_draft(self, body, record_id=None, revision=None):
        allowed={'from','to','cc','bcc','subject','text','attachments','connection_id','project_id','references','in_reply_to','source_id','thread_id'}
        if not isinstance(body,dict) or set(body)-allowed:raise ValueError('Unknown draft fields')
        result={key:body.get(key,'') for key in allowed-{'to','cc','bcc','attachments'}}
        for key in ('from','subject','references','in_reply_to'):mime.text(result[key],4000 if key in {'references','in_reply_to'} else 1000,header=True)
        mime.text(result['text'],mime.MAX_TEXT)
        for key in ('connection_id','project_id','source_id','thread_id'):mime.text(result[key],80)
        for key in ('to','cc','bcc'):result[key]=mime.addresses(body.get(key,[]))
        attachments=body.get('attachments',[])
        if not isinstance(attachments,list) or len(attachments)>30 or any(not isinstance(k,str) or len(k)!=32 for k in attachments):
            raise ValueError('Invalid attachment selection')
        with self.store.transaction() as db:
            previous=self.store.get(db,'draft',record_id) if record_id else None
            source=self.store.get(db,'message',result['source_id']) if result['source_id'] else None
            if result['connection_id']:self.store.get(db,'connection',result['connection_id'])
            # Thread identity comes from an actual source/account relationship.
            permitted_thread=(previous or {}).get('thread_id')
            if source and result['in_reply_to'] and source['connection_id']==result['connection_id'] and result['in_reply_to']==source.get('message_id'):
                permitted_thread=source['thread_id']
            if result['thread_id'] and result['thread_id']!=permitted_thread:
                raise ValueError('Thread identity does not match the selected source/account')
            if previous and previous['connection_id']!=result['connection_id']:result['thread_id']=''
            if previous and previous.get('submission_state') in {'submitting','accepted','partially_accepted','outcome_uncertain'}:
                raise Conflict('Duplicate this draft before preparing another message; the earlier submission cannot be edited')
            selected=[]
            for identity in attachments:
                # Attachment ownership is the exact draft, or one explicit source message
                # for reply/forward. Arbitrary private blob hashes are never a file API.
                sources=[previous] if previous else []
                if result['source_id']:
                    sources.append(self.store.get(db,'message',result['source_id']))
                matches=[a for source in sources if source for a in source['attachments'] if a['id']==identity]
                if not matches or len({a['hash'] for a in matches})!=1:raise ValueError('Attachment does not belong unambiguously to this draft or its selected source')
                selected.append(matches[0])
            result.update(attachments=selected,folder='Drafts',read=True,starred=False,html='',received_at=now(),submission_state='draft')
            if not result['thread_id']:result['thread_id']=previous['thread_id'] if previous and previous['connection_id']==result['connection_id'] else uuid.uuid4().hex
            return self.store.save(db,'draft',result,record_id,revision)

    def attach(self, record_id, revision, path):
        path=Path(path)
        if not path.is_file() or path.stat().st_size>10_000_000:raise ValueError('Choose a file no larger than 10 MB')
        data=path.read_bytes()
        if len(data)>10_000_000:raise ValueError('Attachment grew beyond the supported size')
        with self.store.transaction() as db:
            draft=self.store.get(db,'draft',record_id)
            if draft['submission_state'] not in {'draft','cancelled','failed'}:raise Conflict('Edit or duplicate the draft before changing attachments')
            if len(draft['attachments'])>=30 or sum(a['size'] for a in draft['attachments'])+len(data)>15_000_000:raise ValueError('Draft attachment limit exceeded')
            body=self.store.body(draft)
            body['attachments'].append({'id':uuid.uuid4().hex,'name':mime.filename(path.name),'type':mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                                       'size':len(data),'hash':self.store.blob(db,data),'untrusted':True,'cid':''})
            body['submission_state']='draft'
            return self.store.save(db,'draft',body,record_id,revision)

    def update(self, record_id, revision, changes):
        if not isinstance(changes,dict) or not changes or set(changes)-{'folder','read','starred','project_id'}:raise ValueError('Unknown Mail update')
        for flag in {'read','starred'}&changes.keys():
            if type(changes[flag]) is not bool:raise ValueError('Invalid Mail flag')
        with self.store.transaction() as db:
            row=db.execute("SELECT * FROM records WHERE id=? AND kind IN ('message','draft')",(record_id,)).fetchone()
            record=self.store.unpack(row);body=self.store.body(record)
            if 'folder' in changes and changes['folder'] not in FOLDERS:
                found=db.execute("SELECT id FROM records WHERE kind='folder' AND json_extract(body,'$.name')=? AND json_extract(body,'$.connection_id')=''",(changes['folder'],)).fetchone()
                if not found:raise ValueError('Select a local folder; remote moves require their separate operation')
            if 'project_id' in changes:mime.text(changes['project_id'],80)
            body.update(changes)
            body['local_changes']=True
            return self.store.save(db,record['kind'],body,record_id,revision)

    def import_preview(self,path):
        path=Path(path)
        if not path.is_file() or path.stat().st_size>mime.MAX_BYTES:raise ValueError('Choose an EML no larger than 20 MB')
        raw=path.read_bytes();record=mime.parse(raw);digest=hashlib.sha256(raw).hexdigest()
        with self.store.transaction() as db:
            duplicate=db.execute('SELECT record_id FROM sources WHERE source=?',('eml:'+digest,)).fetchone()
        identity=uuid.uuid4().hex
        if len(self.previews)>=8:self.previews.pop(next(iter(self.previews)))
        self.previews[identity]=(raw,record)
        return {'preview_id':identity,'hash':digest,'subject':record['subject'],'from':record['from'],'size':len(raw),
                'attachments':[{k:v for k,v in a.items() if k!='bytes'} for a in record['attachments']],
                'warnings':record['warnings'],'duplicate_id':duplicate[0] if duplicate else None,'count':1}

    def import_commit(self,preview_id,expected_hash):
        if preview_id not in self.previews:raise ValueError('Import preview expired')
        raw,record=self.previews[preview_id]
        if hashlib.sha256(raw).hexdigest()!=expected_hash:raise Conflict('Import contents changed')
        result=self.ingest(raw,deepcopy(record),source='eml:'+expected_hash)
        self.previews.pop(preview_id,None)
        return result

    def ingest(self,raw,record=None,*,source,connection_id='',folder='Inbox',remote=None,provider_message_id=''):
        record=record or mime.parse(raw)
        with self.store.transaction() as db:
            existing=db.execute('SELECT record_id FROM sources WHERE source=?',(source,)).fetchone()
            if existing:return self.store.get(db,'message',existing[0])
            provider_key='gmail:'+connection_id+':'+provider_message_id if provider_message_id else None
            if provider_key:
                if not remote or not connection_id or not provider_message_id.isdigit() or len(provider_message_id)>20:raise ValueError('Invalid account-scoped Gmail identity')
                existing=db.execute('SELECT record_id FROM sources WHERE source=?',(provider_key,)).fetchone()
                if existing:
                    previous=self.store.get(db,'message',existing[0]);body=self.store.body(previous)
                    locations=body.get('remote_locations',[body['remote']])
                    locations=[v for v in locations if v['mailbox']!=remote['mailbox']]
                    if len(locations)>=200:raise ValueError('Message label count exceeds its bound')
                    locations.append(dict(remote,state='present'));body['remote_locations']=locations
                    if body.get('remote_state') in {'moved_on_server','missing_on_server','uidvalidity_reset'}:
                        body.update(remote=remote,folder=folder,remote_state='cached')
                    result=self.store.save(db,'message',body,previous['id'],previous['revision'])
                    db.execute('INSERT INTO sources VALUES(?,?)',(source,result['id']))
                    return result
            for attachment in record['attachments']:
                attachment['hash']=self.store.blob(db,attachment.pop('bytes'));attachment['id']=uuid.uuid4().hex
            thread=uuid.uuid4().hex
            # Only actual reference links within this account can join a thread.
            parent=record['in_reply_to']
            if parent:
                matches=db.execute("SELECT body FROM records WHERE kind='message' AND json_extract(body,'$.connection_id')=? AND json_extract(body,'$.message_id')=? LIMIT 2",(connection_id,parent)).fetchall()
                if len(matches)==1:thread=json.loads(matches[0][0])['thread_id']
            record.update(raw_hash=self.store.blob(db,raw),connection_id=connection_id,folder=folder,remote=remote,body_cached=True,
                          read=False,starred=False,project_id='',thread_id=thread,received_at=now(),provenance={'origin':'imap' if remote else 'eml_import','source_hash':hashlib.sha256(raw).hexdigest()})
            if provider_key:record.update(provider_message_id=provider_message_id,remote_locations=[dict(remote,state='present')])
            result=self.store.save(db,'message',record)
            db.execute('INSERT INTO sources VALUES(?,?)',(source,result['id']))
            if provider_key:db.execute('INSERT INTO sources VALUES(?,?)',(provider_key,result['id']))
            return result

    def reply(self,record_id,mode,connection_id='',sender=''):
        if mode not in {'reply','reply_all','forward','duplicate'}:raise ValueError('Unknown draft action')
        record=self.get(record_id)
        if not connection_id:connection_id=record.get('connection_id','')
        if connection_id and not sender:
            with self.store.transaction() as db:sender=self.store.get(db,'connection',connection_id).get('sender','')
        if mode=='duplicate':
            body={k:record.get(k,'') for k in ('from','to','cc','bcc','subject','text','connection_id','project_id','references','in_reply_to')}
            body['attachments']=[]
        else:
            actual=record.get('reply_to') or [a for _,a in __import__('email.utils',fromlist=['getaddresses']).getaddresses([record['from']]) if a]
            to=[] if mode=='forward' else actual
            cc=[] if mode!='reply_all' else [a for a in record['to']+record['cc'] if a not in to and a!=sender]
            body={'from':sender,'to':to,'cc':cc,'bcc':[], 'subject':('Fwd: ' if mode=='forward' else 'Re: ')+record['subject'],
                  'text':'\n\n--- Original message ---\n'+record['text'], 'connection_id':connection_id,'project_id':record.get('project_id',''),
                  'in_reply_to':'' if mode=='forward' else record.get('message_id',''),
                  'references':('' if mode=='forward' else (record.get('references','')+' '+record.get('message_id','')).strip()),
                  'source_id':record_id,'thread_id':record['thread_id'] if mode!='forward' and record.get('message_id') and connection_id==record.get('connection_id') else '',
                  'attachments':[a['id'] for a in record['attachments']] if mode=='forward' else []}
        result=self.save_draft(body)
        if mode=='duplicate' and record['attachments']:
            with self.store.transaction() as db:
                duplicate=self.store.body(result)
                duplicate['attachments']=[dict(a,id=uuid.uuid4().hex) for a in record['attachments']]
                result=self.store.save(db,'draft',duplicate,result['id'],result['revision'])
        return result

    def export(self,record_id,path):
        record=self.get(record_id)
        if record['kind']=='draft':
            from email.message import EmailMessage
            from email import policy
            message=EmailMessage(policy=policy.SMTP)
            message['X-Unsent']='1';message['Message-ID']='<draft.'+record_id+'@olive.local>'
            message['Subject']=record['subject']
            if record['from']:message['From']=record['from']
            for key,header in [('to','To'),('cc','Cc'),('bcc','Bcc')]:
                if record[key]:message[header]=', '.join(record[key])
            message.set_content(record['text'])
            with self.store.transaction() as db:
                for a in record['attachments']:
                    message.add_attachment(self.store.read_blob(db,a['hash']),maintype='application',subtype='octet-stream',filename=a['name'])
            raw=message.as_bytes()
        else:
            with self.store.transaction() as db:raw=self.store.read_blob(db,record['raw_hash'])
        Path(path).write_bytes(raw)
        return {'status':'saved','bytes':len(raw)}

    def save_attachment(self,record_id,attachment_id,path):
        record=self.get(record_id);matches=[a for a in record['attachments'] if a['id']==attachment_id]
        if len(matches)!=1:raise ValueError('Attachment no longer belongs to this message')
        with self.store.transaction() as db:data=self.store.read_blob(db,matches[0]['hash'])
        Path(path).write_bytes(data)
        return {'status':'saved','bytes':len(data),'untrusted':True}
