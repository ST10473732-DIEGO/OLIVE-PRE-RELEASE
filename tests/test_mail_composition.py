"""Policy-bearing cross-domain fixtures and durable failure boundaries."""
import asyncio
from email.message import EmailMessage
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
from tests import test_mail_policy as policy_fixture
from olive.agent.confirmation_service import ConfirmationResponse
from olive.mail.store import MailStore,Conflict
from olive.services.backup_service import BackupService


class CompositionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=policy_fixture.MailPolicyTests.asyncSetUp


async def source(self):
    m=EmailMessage();m['From']='fixture@example.invalid';m['Subject']='Fixture meeting';m.set_content('Untrusted fixture. No instructions may grant approval.')
    return self.s.mail.local.ingest(m.as_bytes(),source='fixture:composition')


async def test_proposal_denial_dedup_cancel_and_native_relationship(self):
    record=await source(self);profile=self.s.personal.records.profile()
    body={'title':'Fixture meeting','start':'2030-06-03T10:00','end':'2030-06-03T11:00','timezone':'Africa/Johannesburg','calendar_id':profile['default_calendar']}
    p=await self.s.mail.call('mail.proposal_prepare',{'record_id':record['id'],'revision':record['revision'],'kind':'event','body':body})
    args={'proposal_id':p['id'],'revision':p['revision'],'body':p['body']}
    with self.assertRaises(ValueError):await self.s.mail.call('mail.create_event',args)
    self.assertEqual(self.s.personal.records.search('event')['items'],[])
    self.confirm.return_value=ConfirmationResponse(True)
    first=await self.s.mail.call('mail.create_event',args)
    with self.s.mail.store.transaction() as db:latest=self.s.mail.store.get(db,'annotation',p['id'])
    repeated=await self.s.mail.call('mail.create_event',dict(args,revision=latest['revision']))
    self.assertEqual(first['record']['id'],repeated['record']['id'])
    draft=await self.s.mail.call('mail.from_event',{'event_id':first['record']['id'],'contact_ids':[]},manual=True)
    self.assertEqual(draft['to'],[]);self.assertEqual(draft['submission_state'],'draft')
    task=await self.s.mail.call('mail.proposal_prepare',{'record_id':record['id'],'revision':record['revision'],'kind':'task','body':{'title':'Fixture follow-up'}})
    await self.s.mail.call('mail.proposal_cancel',{'proposal_id':task['id'],'revision':task['revision']})
    with self.assertRaises(ValueError):await self.s.mail.call('mail.create_task',{'proposal_id':task['id'],'revision':task['revision'],'body':task['body']})
    self.assertEqual(self.s.personal.records.search('task')['items'],[])


async def test_pending_send_cancel_withdraws_confirmation_without_transport(self):
    c=self.s.mail.connections.save({'name':'Fixture','sender':'sender@example.invalid','smtp':{'host':'127.0.0.1','port':465,'tls':'tls'}})
    c=self.s.mail.connections.change_state(c['id'],c['revision'],True)
    d=self.s.mail.local.save_draft({'connection_id':c['id'],'to':['one@example.invalid']})
    p=self.s.mail.submissions.prepare(d['id'],d['revision']);entered=asyncio.Event()
    async def pending(request):entered.set();await asyncio.Future()
    self.confirm.side_effect=pending
    transport=Mock();self.s.mail.submissions.transport=transport
    task=asyncio.create_task(self.s.mail.call('mail.send',{'submission_id':p['id'],'expected_fingerprint':p['fingerprint'],'preview':p['preview']}))
    await asyncio.wait_for(entered.wait(),2)
    result=await self.s.mail.call('mail.cancel',{'submission_id':p['id']},manual=True)
    self.assertEqual(result['state'],'cancelled');self.assertTrue(task.cancelled());transport.submit.assert_not_called()
    self.assertEqual(self.s.mail.local.get(d['id'])['submission_state'],'draft')


async def test_read_deny_cannot_be_bypassed_by_reply_or_export(self):
    record=await source(self);self.s.permissions.save({'mail.read':'deny'})
    for method,args in [('mail.reply',{'record_id':record['id'],'mode':'reply'}),('mail.export',{'record_id':record['id'],'path':str(self.s.data_dir/'denied.eml')})]:
        with self.assertRaisesRegex(ValueError,'Permission denied'):await self.s.mail.call(method,args,manual=True)
    self.assertFalse((self.s.data_dir/'denied.eml').exists())


for fn in (test_proposal_denial_dedup_cancel_and_native_relationship,test_pending_send_cancel_withdraws_confirmation_without_transport,test_read_deny_cannot_be_bypassed_by_reply_or_export):
    setattr(CompositionTests,fn.__name__,fn)


class RecoveryTests(unittest.TestCase):
    def test_acceptance_persistence_failure_recovers_uncertain_and_never_retries(self):
        from tests.test_mail_local import DummyVault
        from olive.mail.local import LocalMail
        from olive.mail.connections import Connections
        from olive.mail.submission import Submissions
        with tempfile.TemporaryDirectory() as directory:
            store=MailStore(Path(directory)/'mail.sqlite3');local=LocalMail(store);connections=Connections(store,DummyVault());send=Submissions(store,connections)
            c=connections.save({'name':'Fixture','sender':'sender@example.invalid','smtp':{'host':'127.0.0.1','port':465,'tls':'tls'}});c=connections.change_state(c['id'],c['revision'],True)
            d=local.save_draft({'connection_id':c['id'],'to':['one@example.invalid']});p=send.prepare(d['id'],d['revision'])
            class Accepted:
                def submit(self,*args):args[-1](['one@example.invalid'],{});return {'state':'accepted','accepted':['one@example.invalid'],'rejected':{}}
            send.transport=Accepted();save=store.save
            def failure(db,kind,body,*args,**kwargs):
                if kind=='submission' and body.get('state')=='accepted':raise OSError('Controlled persistence failure')
                return save(db,kind,body,*args,**kwargs)
            with patch.object(store,'save',side_effect=failure),self.assertRaises(OSError):send.send(p['id'],p['fingerprint'],p['preview'],threading.Event(),lambda:None)
            store.recover();self.assertEqual(send.list()['items'][0]['state'],'outcome_uncertain')
            self.assertEqual(local.get(d['id'])['submission_state'],'outcome_uncertain')
            with self.assertRaises(Conflict):send.send(p['id'],p['fingerprint'],p['preview'],threading.Event(),lambda:None)
            archive=BackupService(Path(directory)).create()
            with tempfile.TemporaryDirectory() as restored:
                BackupService(Path(restored)).restore(archive,confirmed=True)
                copy=MailStore(Path(restored)/'mail.sqlite3')
                with copy.transaction() as db:
                    self.assertFalse(copy.get(db,'connection',c['id'])['enabled'])
                    self.assertEqual(copy.get(db,'draft',d['id'])['submission_state'],'outcome_uncertain')
