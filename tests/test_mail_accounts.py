"""Account provenance and folder semantics, with synthetic records only."""
import unittest
from tests import test_mail_local as fixture
from olive.mail.folders import resolve


class MailAccountTests(unittest.TestCase):
    setUp=fixture.LocalMailTests.setUp
    tearDown=fixture.LocalMailTests.tearDown
    connection=fixture.LocalMailTests.connection
    draft=fixture.LocalMailTests.draft
    def test_overlapping_remote_identifiers_roles_and_reply(self):
        first=self.connection();second=self.connection()
        raw=b'From: Friend <friend@example.invalid>\r\nTo: sender@example.invalid\r\nSubject: same\r\nMessage-ID: <same@example.invalid>\r\n\r\nhello'
        records=[]
        for connection in (first,second):
            records.append(self.local.ingest(raw,source='imap:'+connection['id']+':INBOX:1:1',connection_id=connection['id'],folder='INBOX',remote={'mailbox':'INBOX','uidvalidity':1,'uid':1}))
        self.assertNotEqual(records[0]['id'],records[1]['id'])
        self.assertEqual(self.local.search(folder='Inbox')['total'],2)
        self.assertEqual(self.local.search(folder='Inbox',connection_id=first['id'])['total'],1)
        self.assertEqual(self.local.folders(first['id'])['items'][0]['count'],1)
        reply=self.local.reply(records[1]['id'],'reply')
        self.assertEqual(reply['connection_id'],second['id']);self.assertEqual(reply['from'],second['sender'])
        other=self.local.reply(records[1]['id'],'reply',connection_id=first['id'])
        self.assertNotEqual(other['thread_id'],records[1]['thread_id'])
        with self.store.transaction() as db:
            self.store.save(db,'folder',{'name':'[Provider]/Deleted','flags':['\\Trash'],'connection_id':first['id'],'remote':True})
        self.local.ingest(raw,source='trash-first',connection_id=first['id'],folder='[Provider]/Deleted',remote={'mailbox':'[Provider]/Deleted','uidvalidity':1,'uid':2})
        self.assertEqual(self.local.search(folder='Trash')['total'],1)
        self.assertEqual(self.local.search(folder='Trash',connection_id=second['id'])['total'],0)
        # Compatibility lookup is read-only: the original wire folder is retained.
        self.assertEqual(self.local.get(records[0]['id'])['folder'],'INBOX')

    def test_roles_require_one_advertised_target_and_suggestions_exclude_bcc(self):
        self.assertEqual(resolve('Trash',[{'name':'Papierkorb','flags':['\\Trash']}]),'Papierkorb')
        with self.assertRaises(ValueError):resolve('Trash',[{'name':'a','flags':['\\Trash']},{'name':'b','flags':['\\Trash']}])
        with self.assertRaises(ValueError):resolve('Trash',[{'name':'Archives','flags':[]}])
        self.draft(to=['public@example.invalid'],bcc=['hidden@example.invalid'])
        self.assertEqual(self.local.recipients('hidden')['items'],[])
        self.assertEqual(self.local.recipients('public')['items'][0]['address'],'public@example.invalid')

    def test_gmail_labels_deduplicate_only_within_account_and_keep_bodies(self):
        from olive.mail.sync import Sync
        c=self.connection();other=self.connection();raw=b'From: a@example.invalid\r\nSubject: same\r\n\r\nCached body'
        first=self.local.ingest(raw,source='label-inbox',connection_id=c['id'],folder='INBOX',remote={'mailbox':'INBOX','uidvalidity':1,'uid':1},provider_message_id='123456')
        second=self.local.ingest(raw,source='label-project',connection_id=c['id'],folder='Project',remote={'mailbox':'Project','uidvalidity':2,'uid':7},provider_message_id='123456')
        self.assertEqual(first['id'],second['id']);self.assertTrue(second['body_cached']);self.assertIn('Cached body',second['text'])
        self.assertEqual(self.local.search(connection_id=c['id'])['total'],1)
        self.assertEqual(self.local.search(folder='Inbox')['total'],1);self.assertEqual(self.local.search(folder='Project')['total'],1)
        foreign=self.local.ingest(raw,source='other-inbox',connection_id=other['id'],folder='INBOX',remote={'mailbox':'INBOX','uidvalidity':1,'uid':1},provider_message_id='123456')
        self.assertNotEqual(foreign['id'],first['id'])
        sync=Sync(self.store,self.local,self.connections)
        with self.store.transaction() as db:sync._reconcile_folder(db,c['id'],'INBOX',1,set())
        self.assertEqual(self.local.search(folder='Inbox',connection_id=c['id'])['total'],0)
        self.assertEqual(self.local.search(folder='Project',connection_id=c['id'])['total'],1)
        retained=self.local.get(first['id']);self.assertEqual(retained['remote']['mailbox'],'Project')
        self.assertEqual(retained['id'],first['id'])
