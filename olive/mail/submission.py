"""Revision-bound preparation and durable one-way submission transitions."""
import hashlib
import json
import threading
from .mime import compose
from .store import Conflict, now, WRITE_GUARD
from .smtp import SMTPSubmissionTransport


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


class Submissions:
    def __init__(self,store,connections):
        self.store=store;self.connections=connections
        self.transport=SMTPSubmissionTransport()
        self.active={};self.lock=threading.RLock()

    def prepare(self,record_id,revision):
        with self.store.transaction() as db:
            draft=self.store.get(db,'draft',record_id)
            if draft['revision']!=revision:raise Conflict('Draft changed before submission preparation')
            if draft['submission_state'] not in {'draft','cancelled','failed'}:
                raise Conflict('This draft already has a consequential submission. Review its outcome before duplicating it.')
            connection=self.store.get(db,'connection',draft['connection_id']) if draft['connection_id'] else None
            if not connection or not connection['enabled'] or not connection['smtp']:
                raise ValueError('Mail delivery is not configured or the connection is disconnected')
            if not connection['sender']:raise ValueError('Configure a sending identity before submission')
            if draft['from'] and draft['from']!=connection['sender']:raise ValueError('Draft From must match the selected sending identity')
            key='submission:'+record_id+':'+str(revision)+':'+connection['id']+':'+str(connection['revision'])
            existing=db.execute('SELECT record_id FROM sources WHERE source=?',(key,)).fetchone()
            if existing:
                previous=self.store.get(db,'submission',existing[0])
                if previous['state'] not in {'cancelled','failed'}:return previous
                db.execute('DELETE FROM sources WHERE source=?',(key,))
            attachments=[(a,self.store.read_blob(db,a['hash'])) for a in draft['attachments']]
            raw,envelope=compose(draft,attachments,sender=connection['sender'])
            preview={'action':'Submit email','connection_id':connection['id'],'connection_name':connection['name'],
                     'connection_revision':connection['revision'],'server':connection['smtp'],
                     'from':connection['sender'],'to':draft['to'],'cc':draft['cc'],'bcc':draft['bcc'],
                     'subject':draft['subject'],'body':draft['text'],'attachments':draft['attachments'],
                     'size':len(raw),'draft_id':record_id,'draft_revision':revision,
                     'consequence':'Submit these exact bytes and recipients to the configured mail server. Acceptance is not delivery or reading.'}
            body={'draft_id':record_id,'draft_revision':revision,'connection_id':connection['id'],
                  'connection_revision':connection['revision'],'state':'prepared','preview':preview,
                  'fingerprint':fingerprint(preview),'raw_hash':self.store.blob(db,raw),'envelope':envelope,
                  'accepted':[],'rejected':{},'created':now(),'expires_at_seconds':__import__('time').time()+900}
            record=self.store.save(db,'submission',body)
            db.execute('INSERT INTO sources VALUES(?,?)',(key,record['id']))
            return record

    def list(self):
        with self.store.transaction() as db:
            items=self.store.list(db,'submission',limit=50)
        for item in items:
            item.pop('envelope',None);item.pop('raw_hash',None)
            item['preview']={k:item['preview'][k] for k in ('subject','connection_name','size')}
        return {'items':items}

    def _validate(self,db,record,expected_fingerprint,preview):
        if record['fingerprint']!=expected_fingerprint or fingerprint(preview)!=expected_fingerprint or preview!=record['preview']:
            raise Conflict('Submission preview changed. Prepare and review it again.')
        if __import__('time').time()>record['expires_at_seconds']:raise Conflict('Submission preparation expired')
        draft=self.store.get(db,'draft',record['draft_id']);connection=self.store.get(db,'connection',record['connection_id'])
        if draft['revision']!=record['draft_revision'] or connection['revision']!=record['connection_revision'] or not connection['enabled']:
            raise Conflict('Draft or connection changed after preparation. Renew the approval.')
        for attachment in draft['attachments']:self.store.read_blob(db,attachment['hash'])
        return draft,connection

    def send(self,submission_id,expected_fingerprint,preview,cancel,policy_guard):
        with self.lock:
            if submission_id in self.active:raise Conflict('This submission is already active')
            self.active[submission_id]=cancel
        try:
            with self.store.transaction() as db:
                record=self.store.get(db,'submission',submission_id)
                if record['state']!='prepared':raise Conflict('Submission is no longer prepared; it will not be repeated')
                draft,connection=self._validate(db,record,expected_fingerprint,preview)
                policy_guard()
                body=self.store.body(record);body['state']='submitting'
                record=self.store.save(db,'submission',body,record['id'],record['revision'])
                draft_body=self.store.body(draft);draft_body['submission_state']='submitting'
                draft=self.store.save(db,'draft',draft_body,draft['id'],draft['revision'])
                raw=self.store.read_blob(db,record['raw_hash'])
            def guard():
                policy_guard();self.connections.check_revision(connection)
                with self.store.transaction() as db:
                    current=self.store.get(db,'draft',draft['id'])
                    if current['revision']!=draft['revision']:raise Conflict('Draft changed during submission')
            def before_data(accepted,rejected):
                guard()
                with self.store.transaction() as db:
                    current=self.store.get(db,'submission',submission_id)
                    body=self.store.body(current);body.update(possible_submission=True,envelope_accepted=accepted,rejected=rejected)
                    self.store.save(db,'submission',body,current['id'],current['revision'])
            try:
                password=self.connections.secret(connection)
                outcome=self.transport.submit(connection,password,raw,record['envelope'],cancel,guard,before_data)
                if outcome.get('category')=='authentication':self.connections.invalidate_access(connection)
            except Exception as error:
                outcome={'state':'failed','category':type(error).__name__,'accepted':[],'rejected':{}}
            finally:password=None
            # If this persistence transaction itself fails, the durable earlier
            # state remains submitting and recovery marks uncertainty, not retry.
            # Recording an already attempted operation must survive cancellation
            # or a subsequent Deny. This cannot authorise another network action.
            token=WRITE_GUARD.set(None)
            try:
                with self.store.transaction() as db:
                    current=self.store.get(db,'submission',submission_id)
                    body=self.store.body(current);body.update(outcome,finished=now())
                    result=self.store.save(db,'submission',body,current['id'],current['revision'])
                    current_draft=self.store.get(db,'draft',draft['id']);body=self.store.body(current_draft)
                    body['submission_state']=outcome['state']
                    body['folder']='Sent' if outcome['state'] in {'accepted','partially_accepted'} else 'Outbox' if outcome['state']=='outcome_uncertain' else 'Drafts'
                    self.store.save(db,'draft',body,current_draft['id'],current_draft['revision'])
            finally:WRITE_GUARD.reset(token)
            return result
        finally:
            with self.lock:self.active.pop(submission_id,None)

    def cancel(self,submission_id):
        with self.lock:
            active=self.active.get(submission_id)
            if active:
                active.set()
                return {'state':'cancellation_requested','message':'If bytes have reached the server, cancellation cannot retract them.'}
        with self.store.transaction() as db:
            record=self.store.get(db,'submission',submission_id)
            if record['state']=='prepared':
                body=self.store.body(record);body['state']='cancelled'
                return self.store.save(db,'submission',body,record['id'],record['revision'])
            return record

    def close(self):
        with self.lock:
            for event in self.active.values():event.set()

    def sent_copy(self,submission_id,cancel,policy_guard):
        from .imap import MailboxSyncTransport
        from .smtp import check
        with self.store.transaction() as db:
            record=self.store.get(db,'submission',submission_id)
            if record['state'] not in {'accepted','partially_accepted'}:raise Conflict('Only server-accepted submissions have a Sent copy')
            if record.get('sent_copy_state') in {'copying','copied','outcome_uncertain'}:raise Conflict('Sent copy may already exist; it will not be appended again')
            connection=self.store.get(db,'connection',record['connection_id'])
            if not connection['enabled'] or not connection.get('imap') or not connection.get('sent_copy') or not connection.get('sent_folder'):
                raise ValueError('Explicitly configure client-managed Sent copies and a mailbox first')
            if connection['revision']!=record['connection_revision']:raise Conflict('Connection changed after submission; review the Sent copy separately')
            raw=self.store.read_blob(db,record['raw_hash'])
        def guard():policy_guard();self.connections.check_revision(connection)
        check(cancel,guard);transport=MailboxSyncTransport();client=None;possible=False
        try:
            client=transport.connect(connection,self.connections.secret(connection))
            if connection['sent_folder'] not in [f['name'] for f in transport.folders(client)]:raise ValueError('Configured Sent mailbox is unavailable')
            check(cancel,guard)
            with self.store.transaction() as db:
                current=self.store.get(db,'submission',submission_id);body=self.store.body(current)
                if current.get('sent_copy_state') in {'copying','copied','outcome_uncertain'}:raise Conflict('Sent copy already started')
                body['sent_copy_state']='copying';self.store.save(db,'submission',body,current['id'],current['revision'])
            possible=True;transport.append_sent(client,connection['sent_folder'],raw)
            outcome={'sent_copy_state':'copied'}
        except Exception as error:
            outcome={'sent_copy_state':'outcome_uncertain' if possible else 'failed','sent_copy_error':type(error).__name__}
        finally:
            if client:transport.close(client)
        token=WRITE_GUARD.set(None)
        try:
            with self.store.transaction() as db:
                current=self.store.get(db,'submission',submission_id);body=self.store.body(current);body.update(outcome)
                return self.store.save(db,'submission',body,current['id'],current['revision'])
        finally:WRITE_GUARD.reset(token)

    def retry_rejected(self,submission_id):
        # Creates an unsent draft for rejected recipients only. A fresh snapshot
        # and approval are still mandatory; this method never opens a socket.
        from .local import LocalMail
        with self.store.transaction() as db:
            record=self.store.get(db,'submission',submission_id)
            if record['state'] not in {'partially_accepted','failed'} or not record['rejected']:
                raise Conflict('No definitely rejected recipients are available for this retry')
            draft=self.store.get(db,'draft',record['draft_id'])
        local=LocalMail(self.store);copy=local.reply(draft['id'],'duplicate')
        rejected=set(record['rejected'])-set(record['accepted'])
        body={k:copy[k] for k in ('from','subject','text','connection_id','project_id','references','in_reply_to')}
        body.update({key:[v for v in draft[key] if v in rejected] for key in ('to','cc','bcc')})
        body['attachments']=[a['id'] for a in copy['attachments']]
        return local.save_draft(body,copy['id'],copy['revision'])
