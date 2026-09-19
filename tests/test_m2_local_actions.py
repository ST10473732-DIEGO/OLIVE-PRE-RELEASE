"""Local domain action parity with controlled inference and temporary storage."""
import asyncio,tempfile,unittest
from unittest.mock import AsyncMock, Mock
from olive.bridge.host import Host
from olive.application.service_container import ServiceContainer
from olive.services.memory_suggestion_service import MemorySuggestion
class LocalActionTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='olive-m2-actions-');self.host=Host(lambda event:None);self.s=ServiceContainer(self.host.publish,self.host.confirm,data_dir=self.temp.name,migrate=False);self.host.services=self.s
 async def asyncTearDown(self):
  await self.host.shutdown();self.temp.cleanup()
 async def test_suggestion_edit_approval_keeps_source_and_rejection_never_saves(self):
  suggestion=MemorySuggestion('Fixture old preference','preference',self.s.current_chat_id,0);self.s.chat.suggestions[suggestion.id]=suggestion
  await self.host.execute('data.review_suggestion',{'suggestion_id':suggestion.id,'approve':True,'content':'Fixture corrected preference'})
  memory=self.s.memory.list_all()[0];self.assertEqual(memory.content,'Fixture corrected preference');self.assertEqual(memory.source_chat_id,self.s.current_chat_id);self.assertFalse(self.s.chat.suggestions)
  rejected=MemorySuggestion('Fixture rejected preference','preference',self.s.current_chat_id,0);self.s.chat.suggestions[rejected.id]=rejected
  await self.host.execute('data.review_suggestion',{'suggestion_id':rejected.id,'approve':False})
  self.assertEqual(len(self.s.memory.list_all()),1)
 async def test_upgrade_cancel_preserves_completed_batches_and_rejects_duplicate(self):
  entered=asyncio.Event()
  async def controlled(progress):
   progress(24,48);entered.set();await asyncio.Event().wait()
  self.s.rag.reembed_missing=controlled
  running=asyncio.create_task(self.host.execute('knowledge.upgrade',{}));await entered.wait()
  with self.assertRaisesRegex(ValueError,'already active'):await self.host.execute('knowledge.upgrade',{})
  await self.host.execute('knowledge.cancel_upgrade',{});result=await running
  self.assertEqual(result['state'],'cancelled');self.assertEqual(result['completed'],24);self.assertEqual(result['total'],48);self.assertIsNone(self.s.knowledge.upgrade_task)
 async def test_unavailable_embedding_upgrade_is_blocked_not_reported_successful(self):
  self.s.rag.reembed_missing=AsyncMock(return_value=(0,12));result=await self.host.execute('knowledge.upgrade',{})
  self.assertEqual(result['state'],'blocked');self.assertIn('lexical',result['summary'])
  self.s.rag.reembed_missing=AsyncMock(return_value=(12,12));result=await self.host.execute('knowledge.upgrade',{})
  self.assertEqual(result['state'],'completed')
 async def test_offline_provider_keeps_pending_chunks_and_lexical_search(self):
  self.s.rag.store.chunks_without_embeddings=Mock(return_value=[object(),object()])
  self.s.rag.embedding_model='fixture-embedding'
  self.s.ollama.is_model_available=AsyncMock(side_effect=ConnectionError('fixture offline'))
  self.s.ollama.embed=AsyncMock()
  result=await self.host.execute('knowledge.upgrade',{})
  self.assertEqual(result['state'],'blocked');self.assertEqual(result['total'],2)
  self.s.ollama.embed.assert_not_awaited()
