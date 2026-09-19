"""Conversation options preserve context boundaries and cancellable model work."""
import asyncio
import tempfile
import unittest
from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host


class ChatBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-m2-chat-')
        self.host = Host(lambda event: None)
        self.s = ServiceContainer(self.host.publish, self.host.confirm, data_dir=self.temp.name, migrate=False)
        self.host.services = self.s
        self.chat_id = self.s.current_chat_id

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.temp.cleanup()

    async def test_metadata_checks_project_and_pending_context(self):
        args = dict(chat_id=self.chat_id,title='Fixture conversation',notes='Local fixture notes',project_id='unknown')
        with self.assertRaises(ValueError):
            await self.host.execute('chat.metadata',args)
        project = self.s.data.create_project('Fixture project')
        args['project_id'] = project['id']
        context = self.s.interaction.context(self.chat_id)
        context.pending = {'state':'prepared','entities':{'message':'Fixture draft'}}
        with self.assertRaises(ValueError):
            await self.host.execute('chat.metadata',args)
        context.pending = None
        saved = await self.host.execute('chat.metadata',args)
        self.assertEqual(saved['project_id'],project['id'])
        self.assertEqual(context.project_id,project['id'])
        self.assertEqual(saved['notes'],'Local fixture notes')

    async def test_search_finds_message_content_with_bounded_excerpt(self):
        chat = self.s.chats[self.chat_id]
        chat.add_message('user','prefix '*100 + 'uniquefixturequery' + ' suffix'*100)
        records = await self.host.execute('chat.search',{'query':'uniquefixturequery'})
        self.assertEqual(records[0]['id'],self.chat_id)
        self.assertIn('uniquefixturequery',records[0]['excerpt'])
        self.assertLessEqual(len(records[0]['excerpt']),200)
        self.assertEqual(await self.host.execute('chat.search',{'query':'not-in-fixture'}),[])

    async def test_summary_cancellation_reaches_task_and_preserves_previous_summary(self):
        entered = asyncio.Event()
        async def blocked(chat):
            entered.set()
            await asyncio.Event().wait()
        self.s.chat_service.summarize = blocked
        self.s.chats[self.chat_id].summary = 'Existing fixture summary'
        task = asyncio.create_task(self.host.execute('chat.summarize',{'chat_id':self.chat_id}))
        await asyncio.wait_for(entered.wait(),5)
        self.assertTrue((await self.host.execute('chat.summary_state',{'chat_id':self.chat_id}))['active'])
        with self.assertRaises(ValueError):
            await self.host.execute('chat.delete',{'chat_id':self.chat_id})
        await self.host.execute('chat.cancel_summary',{'chat_id':self.chat_id})
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.s.chats[self.chat_id].summary,'Existing fixture summary')
        self.assertFalse((await self.host.execute('chat.summary_state',{'chat_id':self.chat_id}))['active'])
