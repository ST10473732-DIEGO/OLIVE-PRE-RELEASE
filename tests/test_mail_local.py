"""Synthetic local Mail tests; no network, accounts or fixture approval bypass."""
from email.message import EmailMessage
from email import policy
from pathlib import Path
import tempfile
import threading
import unittest
from olive.mail.store import MailStore, Conflict
from olive.mail.local import LocalMail
from olive.mail.connections import Connections, validate_config
from olive.mail.submission import Submissions
from olive.mail import mime


class DummyVault:
    def __init__(self):self.values={}
    def put(self,key,value):self.values[key]=value
    def read_for_provider(self,key):return self.values[key]
    def remove(self,key):self.values.pop(key,None)


class LocalMailTests(unittest.TestCase):
    def test_sender_filter_preserves_subject_query_and_exact_address(self):
        records=[]
        for sender,subject in [('Sarah <sarah@example.invalid>','Planning'),('other-sarah@example.invalid','Planning'),('sarah@example.invalid','Unrelated')]:
            message=EmailMessage();message['From']=sender;message['To']='diego@example.invalid';message['Subject']=subject;message.set_content('Synthetic body')
            records.append(self.local.ingest(message.as_bytes(),source='search:'+sender+subject))
        result=self.local.search(query='Planning',sender='sarah@example.invalid')
        self.assertEqual([r['id'] for r in result['items']],[records[0]['id']])
        result=self.local.search(query='Planning',sender='sarah@example.invalid',recipient='diego@example.invalid')
        self.assertEqual([r['id'] for r in result['items']],[records[0]['id']])
        self.assertEqual(self.local.search(query='Planning',recipient='other-diego@example.invalid')['items'],[])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=MailStore(self.root/'mail.sqlite3');self.local=LocalMail(self.store)
        self.connections=Connections(self.store,DummyVault());self.sends=Submissions(self.store,self.connections)

    def tearDown(self):self.temp.cleanup()

    def draft(self,**kwargs):return self.local.save_draft({'to':['alex@example.invalid'],'subject':'Fixture','text':'Local body',**kwargs})

    def connection(self):
        c=self.connections.save({'name':'Local fixture','sender':'sender@example.invalid','smtp':{'host':'127.0.0.1','port':8465,'tls':'tls'}})
        return self.connections.change_state(c['id'],c['revision'],True)

    def test_draft_revision_search_and_restart(self):
        first=self.draft()
        body={k:first[k] for k in ('to','cc','bcc','subject','text','from')};body['subject']='Revised'
        second=self.local.save_draft(body,first['id'],first['revision'])
        with self.assertRaises(Conflict):self.local.save_draft(body,first['id'],first['revision'])
        reopened=LocalMail(MailStore(self.root/'mail.sqlite3'))
        listed=reopened.search(query='Revised')['items'][0]
        self.assertEqual(listed['id'],first['id'])
        # List summaries carry recipients so drafts can be told apart without opening them.
        self.assertEqual(listed['to'],['alex@example.invalid'])
        self.assertNotIn('text',listed)
        self.assertEqual(reopened.get(first['id'])['revision'],second['revision'])
        self.assertEqual(reopened.search(query='%')['total'],0)

    def test_eml_duplicate_unicode_attachment_and_reply(self):
        message=EmailMessage();message['From']='Alice <alice@example.invalid>';message['Reply-To']='different@example.invalid'
        message['To']='sender@example.invalid';message['Cc']='other@example.invalid';message['Bcc']='hidden@example.invalid'
        message['Subject']='Café';message['Message-ID']='<fixture@example.invalid>';message.set_content('Unicode café body')
        message.add_alternative('<p>Untrusted HTML</p><img src="https://tracking.invalid/pixel">',subtype='html')
        message.add_attachment(b'fixture',maintype='application',subtype='octet-stream',filename='../../CON.txt')
        source=self.root/'fixture.eml';source.write_bytes(message.as_bytes())
        p=self.local.import_preview(source);r=self.local.import_commit(p['preview_id'],p['hash'])
        p2=self.local.import_preview(source);r2=self.local.import_commit(p2['preview_id'],p2['hash'])
        self.assertEqual(r['id'],r2['id']);self.assertEqual(r['subject'],'Café')
        self.assertNotIn('/',r['attachments'][0]['name'])
        reply=self.local.reply(r['id'],'reply_all',sender='sender@example.invalid')
        self.assertEqual(reply['to'],['different@example.invalid']);self.assertEqual(reply['cc'],['other@example.invalid'])
        self.assertEqual(reply['bcc'],[]);self.assertEqual(reply['in_reply_to'],'<fixture@example.invalid>')
        exported=self.root/'export.eml';self.local.export(r['id'],exported)
        self.assertEqual(exported.read_bytes(),source.read_bytes())

    def test_attachment_snapshot_bcc_and_stale_preparation(self):
        connection=self.connection();draft=self.draft(connection_id=connection['id'],bcc=['hidden@example.invalid'])
        file=self.root/'test.txt';file.write_bytes(b'approved snapshot')
        draft=self.local.attach(draft['id'],draft['revision'],file)
        prepared=self.sends.prepare(draft['id'],draft['revision']);file.write_bytes(b'changed outside')
        with self.store.transaction() as db:raw=self.store.read_blob(db,prepared['raw_hash'])
        parsed=mime.parse(raw)
        self.assertEqual(parsed['attachments'][0]['bytes'],b'approved snapshot')
        self.assertIn('hidden@example.invalid',prepared['envelope']['recipients'])
        self.assertNotIn(b'\r\nBcc:',raw)
        body={k:draft[k] for k in ('to','cc','bcc','subject','text','from','connection_id')};body['text']='Changed'
        self.local.save_draft(body,draft['id'],draft['revision'])
        with self.assertRaises(Conflict):self.sends.send(prepared['id'],prepared['fingerprint'],prepared['preview'],threading.Event(),lambda:None)

    def test_persistent_single_submission_and_uncertain_recovery(self):
        c=self.connection();d=self.draft(connection_id=c['id']);p=self.sends.prepare(d['id'],d['revision'])
        self.assertEqual(p['id'],self.sends.prepare(d['id'],d['revision'])['id'])
        class Accepted:
            count=0
            def submit(inner,*args):
                inner.count+=1
                return {'state':'accepted','accepted':['alex@example.invalid'],'rejected':{}}
        transport=Accepted();self.sends.transport=transport
        result=self.sends.send(p['id'],p['fingerprint'],p['preview'],threading.Event(),lambda:None)
        self.assertEqual(result['state'],'accepted')
        with self.assertRaises(Conflict):self.sends.send(p['id'],p['fingerprint'],p['preview'],threading.Event(),lambda:None)
        self.assertEqual(transport.count,1)
        with self.store.transaction() as db:
            body=self.store.body(result);body['state']='submitting';self.store.save(db,'submission',body,result['id'],result['revision'])
        self.store.recover(restored=True)
        self.assertEqual(self.sends.list()['items'][0]['state'],'outcome_uncertain')
        self.assertFalse(self.connections.get(c['id'])['enabled'])

    def test_header_injection_plaintext_and_unknown_config_rejected(self):
        with self.assertRaises(ValueError):self.draft(subject='Hello\r\nBcc: victim@example.invalid')
        with self.assertRaises(ValueError):self.draft(to=['Alex'])
        with self.assertRaises(ValueError):validate_config({'name':'Bad','smtp':{'host':'host','port':25,'tls':'none'}})
        with self.assertRaises(ValueError):validate_config({'name':'Bad','password':'secret'})
        with self.assertRaises(ValueError):mime.parse(b'x'*(mime.MAX_BYTES+1))


if __name__=='__main__':unittest.main()
