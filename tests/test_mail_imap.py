"""Actual TLS sockets with a scripted protocol peer; interoperability unclaimed."""
from pathlib import Path
import tempfile
import threading
import unittest
from olive.mail.store import MailStore,Conflict
from olive.mail.local import LocalMail
from olive.mail.connections import Connections
from olive.mail.sync import Sync
from tests.test_mail_local import DummyVault
from tests.mail_imap_fixture import IMAPFixture


class IMAPTests(unittest.TestCase):
    def test_two_accounts_gmail_labels_trash_and_xoauth2_on_real_tls_sockets(self):
        from olive.mail.imap import MailboxSyncTransport
        with tempfile.TemporaryDirectory() as directory,IMAPFixture(Path(directory)/'one') as first,IMAPFixture(Path(directory)/'two') as second:
            store=MailStore(Path(directory)/'mail.sqlite3');local=LocalMail(store);connections=Connections(store,DummyVault());sync=Sync(store,local,connections)
            accounts=[]
            for server in (first,second):
                server.mailboxes=['INBOX','Project','Deleted'];server.folder_flags={'Deleted':['\\Trash']}
                server.mailbox_messages={'INBOX':dict(server.messages),'Project':{7:server.messages[1]},'Deleted':{}}
                server.gmail_ids={('INBOX',1):123456,('Project',7):123456}
                c=connections.save(server.config);c=connections.store_secret(c['id'],c['revision'],'fixture-secret');c=connections.change_state(c['id'],c['revision'],True);accounts.append(c)
                self.assertEqual(sync.refresh(c['id'],'Inbox')['state'],'completed')
                self.assertEqual(sync.refresh(c['id'],'Project')['state'],'completed')
            self.assertEqual(local.search(folder='Inbox')['total'],2);self.assertEqual(local.search()['total'],2)
            record=local.get(local.search(connection_id=accounts[0]['id'])['items'][0]['id'])
            record=sync.remote_action(record['id'],record['revision'],'move',{'destination':'Deleted'},threading.Event(),lambda:None)
            self.assertEqual(record['folder'],'Deleted');self.assertEqual(record['remote']['mailbox'],'Deleted')
            self.assertEqual(local.search(folder='Trash',connection_id=accounts[0]['id'])['total'],1)
            self.assertEqual(local.search(folder='Inbox',connection_id=accounts[1]['id'])['total'],1)
            sync.refresh(accounts[0]['id'],'Trash');self.assertEqual(local.search()['total'],2)
            transport=MailboxSyncTransport()
            result=transport.test(dict(first.config,auth_type='google_oauth'),'synthetic-access')
            self.assertFalse(result['sent_message']);self.assertEqual(first.auth_methods,['XOAUTH2'])
            self.assertNotIn('EXPUNGE',first.commands);self.assertEqual(first.body_fetches,0)

    def test_server_search_flag_conflict_move_folder_rename_and_cache_removal(self):
        with tempfile.TemporaryDirectory() as directory,IMAPFixture(Path(directory)/'tls') as server:
            store=MailStore(Path(directory)/'mail.sqlite3');local=LocalMail(store);connections=Connections(store,DummyVault())
            c=connections.save(server.config);c=connections.store_secret(c['id'],c['revision'],'fixture-secret');c=connections.change_state(c['id'],c['revision'],True)
            sync=Sync(store,local,connections);sync.refresh(c['id']);record=local.get(local.search()['items'][0]['id'])
            record=local.update(record['id'],record['revision'],{'read':True,'folder':'Archive'})
            sync.refresh(c['id']);self.assertEqual(local.get(record['id'])['remote_state'],'flag_conflict')
            result=sync.search_server(c['id'],'INBOX','fixture',threading.Event(),lambda:None)
            self.assertEqual(result['items'][0]['id'],record['id']);self.assertEqual(local.search()['total'],1)
            sync.folder_action(c['id'],'rename','INBOX','FixtureRenamed',threading.Event(),lambda:None)
            self.assertEqual(local.get(record['id'])['remote']['mailbox'],'FixtureRenamed')
            sync.refresh(c['id'],'FixtureRenamed');self.assertEqual(local.search()['total'],1)
            record=sync.fetch_body(record['id'],threading.Event(),lambda:None)
            c=connections.change_state(c['id'],c['revision'],False)
            result=connections.remove_cache(c['id'],c['revision']);self.assertEqual(result['removed_bodies'],1)
            retained=local.get(record['id']);self.assertEqual(retained['text'],'');self.assertFalse(retained['body_cached']);self.assertEqual(retained['folder'],'Archive')
            self.assertNotIn('EXPUNGE',server.commands)

    def test_smtp_acceptance_and_separate_sent_append_failure_never_resubmit(self):
        from tests.mail_fixture import Sink
        from olive.mail.submission import Submissions
        for lose_response in (False,True):
          with self.subTest(lose_response=lose_response),tempfile.TemporaryDirectory() as directory,IMAPFixture(Path(directory)/'imap') as incoming,Sink(Path(directory)/'smtp',starttls=True) as outgoing:
            incoming.mailboxes.append('Sent');incoming.fail_append=lose_response
            store=MailStore(Path(directory)/'mail.sqlite3');local=LocalMail(store);connections=Connections(store,DummyVault());sends=Submissions(store,connections)
            config={**outgoing.connection,'imap':incoming.config['imap'],'ca_pem':outgoing.connection['ca_pem']+'\n'+incoming.pem,'sent_copy':True,'sent_folder':'Sent'}
            config={k:v for k,v in config.items() if k not in {'id','revision','enabled'}}
            c=connections.save(config);c=connections.store_secret(c['id'],c['revision'],'fixture-secret');c=connections.change_state(c['id'],c['revision'],True)
            d=local.save_draft({'to':['one@example.invalid'],'connection_id':c['id'],'text':'Independent submission; scripted IMAP copy'});p=sends.prepare(d['id'],d['revision'])
            result=sends.send(p['id'],p['fingerprint'],p['preview'],threading.Event(),lambda:None);self.assertEqual(result['state'],'accepted')
            result=sends.sent_copy(p['id'],threading.Event(),lambda:None)
            self.assertEqual(result['state'],'accepted');self.assertEqual(result['sent_copy_state'],'outcome_uncertain' if lose_response else 'copied')
            self.assertEqual(len(outgoing.records),1);self.assertEqual(len(incoming.appended),1)
            with self.assertRaises(Conflict):sends.sent_copy(p['id'],threading.Event(),lambda:None)
            self.assertEqual(len(outgoing.records),1)

    def test_incremental_body_peek_flags_uidvalidity_and_partial_batches(self):
        with tempfile.TemporaryDirectory() as directory,IMAPFixture(Path(directory)/'tls') as server:
            store=MailStore(Path(directory)/'mail.sqlite3');local=LocalMail(store);connections=Connections(store,DummyVault())
            c=connections.save(server.config);c=connections.store_secret(c['id'],c['revision'],'fixture-secret');c=connections.change_state(c['id'],c['revision'],True)
            sync=Sync(store,local,connections)
            result=sync.refresh(c['id']);self.assertEqual(result['state'],'completed',result)
            rows=local.search()['items'];self.assertEqual(len(rows),1);identity=rows[0]['id']
            self.assertFalse(local.get(identity)['body_cached']);self.assertEqual(server.body_fetches,0)
            record=sync.fetch_body(identity,threading.Event(),lambda:None)
            self.assertIn('on demand',record['text']);self.assertEqual(server.body_fetches,1);self.assertFalse(record['read'])
            record=sync.remote_action(identity,record['revision'],'flags',{'read':True},threading.Event(),lambda:None)
            self.assertTrue(record['read']);self.assertIn(b'\\Seen',server.flags[1]);self.assertNotIn('EXPUNGE',server.commands)
            sync.refresh(c['id']);self.assertEqual(local.search()['total'],1)
            server.messages[2]=server.messages[1].replace(b'one@',b'two@');server.messages[3]=server.messages[1].replace(b'one@',b'three@');server.fail_uid=3
            result=sync.refresh(c['id']);self.assertEqual(result['state'],'partial');self.assertEqual(result['count'],1);self.assertEqual(local.search()['total'],2)
            server.fail_uid=None;result=sync.refresh(c['id']);self.assertEqual(result['state'],'completed');self.assertEqual(local.search()['total'],3)
            server.validity=102;sync.refresh(c['id']);self.assertEqual(local.search()['total'],6)
            self.assertEqual(local.get(identity)['remote_state'],'uidvalidity_reset')
            connections.change_state(c['id'],c['revision'],False)
            result=sync.refresh(c['id']);self.assertEqual(result['state'],'failed');self.assertIn('on demand',local.get(identity)['text'])

    def test_wrong_uid_response_and_unsupported_move_do_not_guess(self):
        from olive.mail.imap import MailboxSyncTransport
        class Wrong:
            capabilities=()
            def uid(self,*args):
                return ('OK',[b'* 1 FETCH (UID 1 RFC822.SIZE 10)']) if 'RFC822.SIZE' in args[-1] else ('OK',[(b'1 (UID 999 BODY[] {4}',b'nope'),b')'])
        transport=MailboxSyncTransport()
        with self.assertRaises(ValueError):transport.fetch(Wrong(),1,True)
        with self.assertRaises(ValueError):transport.move(Wrong(),1,'Trash')
