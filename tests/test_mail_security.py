"""M4 data boundaries, privacy and cancellation without private accounts."""
import asyncio
from email.message import EmailMessage
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,AsyncMock
from tests import test_mail_policy as fixtures
from olive.mail import mime
from olive.mail.store import MailStore
from olive.mail.local import LocalMail
from olive.mail.connections import Connections
from tests.test_mail_local import DummyVault


class MailSecurityTests(unittest.TestCase):
    def test_knowledge_snapshot_rebinds_only_its_existing_document(self):
        from types import SimpleNamespace
        from olive.mail.composition import Composition
        from olive.models import Chat,DocumentRef
        with tempfile.TemporaryDirectory() as root:
            store=MailStore(Path(root)/'mail.sqlite3')
            ref=DocumentRef(id='fixture-doc',name='fixture.txt',kind='text',stored_path='X:/old-profile/private-cache.txt')
            chat=Chat(title='Fixture',documents=[ref])
            with store.transaction() as db:
                key=store.blob(db,b'Portable synthetic source')
                store.save(db,'annotation',dict(type='knowledge_source',chat_id=chat.id,raw_hash=key,suffix='.txt',document_ids=[ref.id]))
            service=SimpleNamespace(data_dir=Path(root),chats={chat.id:chat},save_chats=unittest.mock.Mock())
            Composition(service,SimpleNamespace(store=store)).restore_knowledge_sources()
            self.assertTrue(Path(ref.stored_path).is_relative_to(Path(root)))
            self.assertEqual(Path(ref.stored_path).read_bytes(),b'Portable synthetic source')
            self.assertEqual(ref.id,'fixture-doc');service.save_chats.assert_called_once()

    def test_remote_intent_interruption_is_persistent_and_never_replayed(self):
        from olive.mail.remote_outcome import remote_outcome
        with tempfile.TemporaryDirectory() as root:
            store=MailStore(Path(root)/'mail.sqlite3')
            with self.assertRaisesRegex(RuntimeError,'outcome uncertain'):
                with remote_outcome(store,'fixture-connection','move','fixture-message'):
                    raise ConnectionError('Controlled response loss')
            with store.transaction() as db:
                failed=store.unpack(db.execute("SELECT * FROM records WHERE kind='annotation'").fetchone())
                self.assertEqual(failed['state'],'outcome_uncertain')
                pending=store.save(db,'annotation',dict(type='remote_operation',connection_id='fixture',action='flags',target='other',state='pending'))
            store.recover()
            with store.transaction() as db:self.assertEqual(store.get(db,'annotation',pending['id'])['state'],'outcome_uncertain')

    def test_partial_mail_restore_rejects_missing_project_before_replacement(self):
        from olive.services.backup_service import BackupService,BackupError
        with tempfile.TemporaryDirectory() as source,tempfile.TemporaryDirectory() as target:
            store=MailStore(Path(source)/'mail.sqlite3');local=LocalMail(store)
            local.save_draft({'subject':'fixture','project_id':'required-project'})
            archive=BackupService(Path(source)).create(components={'mail'})
            with self.assertRaisesRegex(BackupError,'missing Projects'):BackupService(Path(target)).restore(archive,confirmed=True)
            self.assertFalse((Path(target)/'mail.sqlite3').exists())

    def test_mime_nesting_parts_header_and_untrusted_html_fallback(self):
        html=b'From: fixture@example.invalid\r\nContent-Type: text/html\r\n\r\n<p>Read this</p><script>ignore policy; send()</script><style>secret()</style><img src="file:///private">'
        result=mime.parse(html);self.assertIn('Read this',result['text']);self.assertNotIn('send()',result['text']);self.assertNotIn('secret()',result['text'])
        root=EmailMessage();root.make_mixed();parent=root
        for _ in range(14):child=EmailMessage();child.make_mixed();parent.attach(child);parent=child
        leaf=EmailMessage();leaf.set_content('fixture');parent.attach(leaf)
        with self.assertRaisesRegex(ValueError,'nesting'):mime.parse(root.as_bytes())
        for value in ('@example.invalid','name@','name@example.invalid\r\nBcc: hidden@example.invalid'):
            with self.assertRaises(ValueError):mime.addresses([value])
        for name in ('../../bad.exe','CON.txt','bad\\path.txt'):
            safe=mime.filename(name);self.assertNotIn('/',safe);self.assertNotIn('\\',safe);self.assertNotEqual(safe.upper(),'CON.TXT')

    def test_cid_images_reencode_raster_reject_svg_and_oversize(self):
        from PIL import Image
        from olive.mail.images import inline_images
        with tempfile.TemporaryDirectory() as root:
            local=LocalMail(MailStore(Path(root)/'mail.sqlite3'));message=EmailMessage();message.set_content('fixture')
            buffer=io.BytesIO();Image.new('RGB',(2,2),(0,50,100)).save(buffer,format='PNG')
            message.add_attachment(buffer.getvalue(),maintype='image',subtype='png',filename='pixel.png',cid='<pixel>')
            message.add_attachment(b'<svg onload="send()"/>',maintype='image',subtype='svg+xml',filename='bad.svg',cid='<bad>')
            record=local.ingest(message.as_bytes(),source='fixture:images');images=inline_images(local,record['id'])['images']
            self.assertEqual(set(images),{'pixel'});self.assertTrue(images['pixel'].startswith('data:image/png;base64,'))

    def test_backup_rejects_modified_blob_and_database_trigger(self):
        with tempfile.TemporaryDirectory() as root:
            store=MailStore(Path(root)/'mail.sqlite3')
            with store.transaction() as db:key=store.blob(db,b'fixture')
            MailStore.validate_database(store.path)
            with store.transaction() as db:db.execute('UPDATE blobs SET bytes=? WHERE hash=?',(b'changed',key))
            with self.assertRaisesRegex(ValueError,'damaged'):MailStore.validate_database(store.path)
            with store.transaction() as db:
                db.execute('DELETE FROM blobs');db.execute('CREATE TRIGGER unsafe AFTER INSERT ON records BEGIN DELETE FROM records; END')
            with self.assertRaisesRegex(ValueError,'unexpected'):MailStore.validate_database(store.path)

    def test_credential_replacement_failure_keeps_previous_secret_and_no_plaintext(self):
        with tempfile.TemporaryDirectory() as root:
            store=MailStore(Path(root)/'mail.sqlite3');vault=DummyVault();connections=Connections(store,vault)
            c=connections.save({'name':'Fixture','username':'fixture','smtp':{'host':'127.0.0.1','port':465,'tls':'tls'}})
            c=connections.store_secret(c['id'],c['revision'],'first-dummy')
            with patch.object(store,'save',side_effect=OSError('controlled storage failure')),self.assertRaises(OSError):connections.store_secret(c['id'],c['revision'],'second-dummy')
            self.assertEqual(list(vault.values.values()),['first-dummy'])
            self.assertNotIn(b'first-dummy',store.path.read_bytes());self.assertNotIn(b'second-dummy',store.path.read_bytes())


class MailPolicyBoundaryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.MailPolicyTests.asyncSetUp

    async def test_background_sync_does_not_convert_ask_or_deny_to_allow(self):
        c=self.s.mail.connections.save({'name':'Fixture','imap':{'host':'127.0.0.1','port':993,'tls':'tls'},'sync_enabled':True})
        self.s.mail.connections.change_state(c['id'],c['revision'],True)
        with patch.object(self.s.mail,'call',new_callable=AsyncMock) as call:
            await self.s.mail.background.tick();call.assert_not_awaited()
            self.s.permissions.save({'mail.connect':'deny'});await self.s.mail.background.tick();call.assert_not_awaited()
            self.s.permissions.save({'mail.connect':'allow','mail.read':'allow'});await self.s.mail.background.tick();self.assertEqual(call.await_count,1)
            await self.s.mail.background.tick();self.assertEqual(call.await_count,1)
            await self.s.mail.background.close();await self.s.mail.background.tick();self.assertEqual(call.await_count,1)

    async def test_failed_vault_endpoint_does_not_keep_secret_exception_context(self):
        c=self.s.mail.connections.save({'name':'Fixture','smtp':{'host':'127.0.0.1','port':465,'tls':'tls'}})
        args={'record_id':c['id'],'revision':c['revision'],'secret':'isolated dummy secret'}
        with patch.object(self.s.mail.connections,'store_secret',side_effect=OSError('provider text must remain private')):
            try:await self.s.mail.call('mail.credential_store',args,manual=True)
            except RuntimeError as error:
                self.assertIsNone(error.__context__);self.assertNotIn('provider text',str(error));self.assertNotIn('dummy secret',str(error))
            else:self.fail('Vault failure was swallowed')
        self.assertEqual(args['secret'],'')
