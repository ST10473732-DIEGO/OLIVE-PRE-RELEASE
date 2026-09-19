"""Reviewed source-linked native records, using existing Personal Core services."""
import hashlib
import json
from .store import Conflict


class Composition:
    def __init__(self,services,mail):self.s=services;self.m=mail

    def prepare(self,record_id,revision,kind,body):
        if kind not in {'event','task'}:raise ValueError('Choose Calendar event or Personal Task')
        source=self.m.local.get(record_id)
        if source['revision']!=revision:raise Conflict('Source message changed; review it again')
        body=self.s.personal.records.validate(kind,body)
        signature=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        key=f'proposal:{record_id}:{kind}:{signature}'
        with self.m.store.transaction() as db:
            old=db.execute('SELECT record_id FROM sources WHERE source=?',(key,)).fetchone()
            if old:
                previous=self.m.store.get(db,'annotation',old[0])
                if previous['state']!='cancelled':return previous
                db.execute('DELETE FROM sources WHERE source=?',(key,))
            result=self.m.store.save(db,'annotation',{'type':'native_proposal','native_kind':kind,'body':body,'source_id':record_id,
                'source_revision':revision,'state':'proposed','target_id':None,'signature':signature})
            db.execute('INSERT INTO sources VALUES(?,?)',(key,result['id']))
            return result

    def commit(self,proposal_id,revision,body,kind,guard):
        with self.m.store.transaction() as db:proposal=self.m.store.get(db,'annotation',proposal_id)
        if proposal['native_kind']!=kind or proposal['revision']!=revision or proposal['body']!=body:
            raise Conflict('Proposal changed; review the current fields')
        if proposal['state']=='cancelled':raise Conflict('Proposal was cancelled')
        source=self.m.local.get(proposal['source_id'])
        if source['revision']!=proposal['source_revision']:raise Conflict('Source message changed after proposal preparation')
        from ..personal.store import WRITE_GUARD,WRITE_SOURCE
        token=WRITE_GUARD.set(guard);origin=WRITE_SOURCE.set({'origin':'mail_proposal','mail_id':source['id'],'proposal_id':proposal_id})
        uid='olive-mail-proposal-'+proposal_id
        try:
            p=self.s.personal.records
            with p.store.transaction() as db:
                existing=db.execute('SELECT id,deleted FROM records WHERE kind=? AND uid=?',(kind,uid)).fetchone()
                if existing:
                    if existing['deleted']:raise Conflict('The linked native record was deleted; it will not be resurrected')
                    record=p.store.get(db,kind,existing['id'])
                else:record=p._save(db,kind,body,uid=uid,source={'origin':'mail_proposal','mail_id':source['id'],'proposal_id':proposal_id})
        finally:WRITE_GUARD.reset(token);WRITE_SOURCE.reset(origin)
        with self.m.store.transaction() as db:
            current=self.m.store.get(db,'annotation',proposal_id)
            fields=self.m.store.body(current);fields.update(state='created',target_id=record['id'])
            self.m.store.save(db,'annotation',fields,current['id'],current['revision'])
        self.s.personal.scheduler.changed()
        return {'state':'saved','record':record,'source_id':source['id'],'message':'Created locally. No invitation or message was sent.'}

    def cancel(self,proposal_id,revision):
        with self.m.store.transaction() as db:
            p=self.m.store.get(db,'annotation',proposal_id)
            if p['state']!='proposed':raise Conflict('This proposal is no longer pending')
            body=self.m.store.body(p);body['state']='cancelled'
            return self.m.store.save(db,'annotation',body,proposal_id,revision)

    def from_event(self,event_id,contact_ids,connection_id=''):
        p=self.s.personal.records;event=p.get('event',event_id)
        if not isinstance(contact_ids,list) or len(contact_ids)>50:raise ValueError('Select a bounded contact list')
        recipients=[]
        for identity in contact_ids:
            person=p.get('contact',identity)
            if len(person['emails'])!=1:raise ValueError('Choose an exact address for '+person['display_name'])
            recipients.append(person['emails'][0]['value'])
        return self.m.local.save_draft({'to':recipients,'subject':event['title'],'text':event['title']+'\n'+event['start']+' — '+event['end']+'\n'+event['location']+'\n\n'+event['description'],
             'connection_id':connection_id,'project_id':event['project_id']})

    def calendar_draft(self,event_id,recipients,connection_id=''):
        from .mime import addresses
        validated=addresses(recipients)
        event=self.s.personal.records.get('event',event_id)
        return self.m.local.save_draft({'to':validated,'subject':event['title'],
            'text':event['title']+'\n'+event['start']+' — '+event['end']+'\n'+event['location']+'\n\n'+event['description'],
            'connection_id':connection_id,'project_id':event['project_id']})

    async def add_knowledge(self,record_id,revision,guard,attachment_id=''):
        import asyncio
        from pathlib import Path
        from ..models import Chat
        record=self.m.local.get(record_id)
        if record['revision']!=revision:raise Conflict('Mail source changed; review the current content')
        if record.get('body_cached') is False:raise ValueError('Fetch the selected content before adding it to Knowledge')
        if attachment_id:
            matches=[a for a in record['attachments'] if a['id']==attachment_id]
            if len(matches)!=1:raise ValueError('Select an attachment belonging to this exact message')
            attachment=matches[0];suffix=Path(attachment['name']).suffix.lower()
            if suffix not in {'.txt','.md','.pdf','.docx','.csv','.json'}:raise ValueError('This attachment type is not supported for safe document indexing')
            with self.m.store.transaction() as db:data=self.m.store.read_blob(db,attachment['hash'])
        else:suffix='.txt';data=('Untrusted imported mail evidence\nSubject: '+record['subject']+'\nFrom: '+record['from']+'\n\n'+record['text']).encode('utf-8')
        if len(data)>10_000_000:raise ValueError('Selected Knowledge source exceeds 10 MB')
        digest=hashlib.sha256(data).hexdigest();key='knowledge:'+record_id+':'+digest
        guard()
        with self.m.store.transaction() as db:
            existing=db.execute('SELECT record_id FROM sources WHERE source=?',(key,)).fetchone()
            annotation=self.m.store.get(db,'annotation',existing[0]) if existing else None
        if annotation and annotation['chat_id'] in self.s.chats:chat_id=annotation['chat_id']
        else:
            chat=Chat(title='Mail source: '+record['subject'][:100],project_id=record.get('project_id') or None)
            self.s.chats[chat.id]=chat;self.s.save_chats();chat_id=chat.id
            with self.m.store.transaction() as db:
                snapshot=self.m.store.blob(db,data)
                annotation=self.m.store.save(db,'annotation',{'type':'knowledge_source','source_id':record_id,'source_revision':revision,'chat_id':chat_id,'hash':digest,'raw_hash':snapshot,'suffix':suffix,'state':'staged'})
                db.execute('INSERT INTO sources VALUES(?,?)',(key,annotation['id']))
        directory=self.s.data_dir/'attachments'/'mail-knowledge';directory.mkdir(parents=True,exist_ok=True)
        target=directory/(digest+suffix)
        await asyncio.to_thread(target.write_bytes,data)
        guard()
        await self.s.knowledge.attach(chat_id,[str(target)],permanent=True)
        guard()
        documents=[r for r in self.s.knowledge.list() if r['chat_id']==chat_id]
        with self.m.store.transaction() as db:
            current=self.m.store.get(db,'annotation',annotation['id']);body=self.m.store.body(current)
            body.update(state='saved',document_ids=[r['id'] for r in documents])
            self.m.store.save(db,'annotation',body,current['id'],current['revision'])
        return {'state':'saved','chat_id':chat_id,'source_id':record_id,'documents':documents,'message':'Selected untrusted source added to local Knowledge; inspect indexing status for semantic availability.'}

    def restore_knowledge_sources(self):
        """Rebind only explicit Mail source snapshots; no indexing or network."""
        from pathlib import Path
        changed=False
        with self.m.store.transaction() as db:
            rows=db.execute("SELECT * FROM records WHERE kind='annotation' AND json_extract(body,'$.type')='knowledge_source'").fetchall()
            for row in rows:
                record=self.m.store.unpack(row);chat=self.s.chats.get(record.get('chat_id'))
                if not chat or not record.get('raw_hash'):continue
                suffix=record.get('suffix')
                if suffix not in {'.txt','.md','.pdf','.docx','.csv','.json'}:raise ValueError('Invalid Mail Knowledge snapshot type')
                target=self.s.data_dir/'attachments'/'mail-knowledge'/(record['raw_hash']+suffix)
                refs=[r for r in chat.documents if r.id in record.get('document_ids',[])]
                for ref in refs:
                    # Never probe/read a path from a different restored profile.
                    if ref.stored_path!=str(target) or not target.exists():
                        data=self.m.store.read_blob(db,record['raw_hash'])
                        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                        ref.stored_path=str(target);ref.original_path=str(target);changed=True
        if changed:self.s.save_chats()
