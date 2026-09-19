"""Controlled model responses validate semantic scope contracts, not model quality."""
import json,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock
from olive.interaction.native_pending import native_pending_request,native_request_shape,native_lookup_before_disambiguation,native_record_links

class NativePendingTests(unittest.IsolatedAsyncioTestCase):
 async def test_coarse_task_calendar_hint_does_not_exclude_reminders(self):
  from olive.interaction.interpreter import SemanticInterpreter
  model=SimpleNamespace(chat_measured=AsyncMock(side_effect=[
   {'content':'{"single_operation":true}'},
   {'content':json.dumps({'confidence':1.,'clarification':'','steps':[{'intent':'reminders.create','entities':{'offset_minutes':'30'},'references':{'event_id':'event_id'}}]})},
   {'content':'{"links":[{"project":"","person_id":"","event_id":"event-fixture","personal_task_id":""}]}'}]))
  interpreter=SemanticInterpreter(model,SimpleNamespace(route=Mock(return_value=SimpleNamespace(name='fixture-model'))))
  interpreter.speech_act=AsyncMock(return_value={'mode':'action','domains':['task','calendar']})
  result=await interpreter.interpret('Alert me half an hour before that appointment',{'entities':{'event_id':'event-fixture'}})
  self.assertEqual(result['steps'][0]['intent'],'reminders.create')
  variants=model.chat_measured.call_args_list[1].kwargs['format']['properties']['steps']['items']['anyOf']
  self.assertIn('reminders.create',[x['properties']['intent']['const'] for x in variants])
  self.assertNotIn('task.correct',[x['properties']['intent']['const'] for x in variants])
  self.assertNotIn('personal.commit',[x['properties']['intent']['const'] for x in variants])
  self.assertNotIn('personal.correct',[x['properties']['intent']['const'] for x in variants])
 def test_native_schema_separates_scalar_content_from_selected_identity(self):
  from olive.interaction.intent import schema
  for intent in ('tasks.create','calendar.create'):
   step=schema({'title','person_id','project'},[intent])['properties']['steps']['items']['anyOf'][0]['properties']
   self.assertIn('title',step['entities']['properties'])
   self.assertNotIn('title',step['references']['properties'])
   self.assertNotIn('person_id',step['references']['properties'])
   self.assertNotIn('person_id',step['entities']['properties'])
   self.assertIn('project',step['references']['properties'])
  from olive.interaction.intent import entity_schema,parse
  self.assertEqual(entity_schema('record_id')['pattern'],r'^[0-9a-f]{32}$')
  for intent,key in [('contacts.get','person_id'),('tasks.update','personal_task_id')]:
   value={'confidence':1.,'clarification':'','steps':[{'intent':intent,'entities':{key:'a'*32,'record_id':'A human name'},'references':{}}]}
   with self.assertRaisesRegex(ValueError,'Conflicting target ID'):parse(json.dumps(value))
 def test_only_equivalent_known_native_id_references_are_canonicalised(self):
  from olive.interaction.intent import parse
  value={'confidence':1.,'clarification':'','steps':[{'intent':'tasks.create','entities':{'title':'Synthetic','event_id':'selected-event'},'references':{'event_id':'event_id'}}]}
  raw=json.dumps(value)
  self.assertEqual(parse(raw,{'event_id':'selected-event'})['steps'][0]['references'],{})
  for context in ({},{'event_id':'different-event'}):
   with self.assertRaisesRegex(ValueError,'unresolved reference'):parse(raw,context)
  value['steps'][0]['references']['event_id']='person_id'
  with self.assertRaises(ValueError):parse(json.dumps(value),{'event_id':'selected-event','person_id':'selected-event'})
 async def test_project_link_extraction_retains_other_fields_and_rejects_invention(self):
  router=SimpleNamespace(route=Mock(return_value=SimpleNamespace(name='fixture-model')))
  model=SimpleNamespace(chat_measured=AsyncMock(return_value={'content':'{"links":[{"project":"Coursework","person_id":"","event_id":"","personal_task_id":""}]}'}))
  value={'confidence':1.,'clarification':'','steps':[{'intent':'tasks.create','entities':{'title':'Read chapter'},'references':{'event_id':'event_id'}}]}
  result=await native_record_links(model,router,'Add this commitment to Coursework',value,{})
  self.assertEqual(result['steps'][0]['entities'],{'title':'Read chapter','project':'Coursework'})
  self.assertEqual(result['steps'][0]['references'],{'event_id':'event_id'})
  model.chat_measured.return_value={'content':'{"links":[{"project":"Invented","person_id":"","event_id":"","personal_task_id":""}]}'}
  with self.assertRaises(ValueError):await native_record_links(model,router,'Add this to Coursework',value,{})
 def test_literal_read_uses_repository_but_ambiguous_operations_are_not_rewritten(self):
  gate={'mode':'action','domains':['contacts']}
  for text,name in [('Find Alex Example in Contacts','Alex Example'),('Look up the contact Morgan Fixture','Morgan Fixture')]:
   value={'confidence':.9,'clarification':'Does this person exist?','steps':[{'intent':'contacts.search','entities':{'query':name},'references':{}}]}
   resolved=native_lookup_before_disambiguation(value,text,gate)
   self.assertEqual(resolved['clarification'],'');self.assertEqual(resolved['steps'],value['steps'])
   self.assertEqual(native_lookup_before_disambiguation(value,text,{'mode':'answer','domains':['contacts']}),value)
   self.assertEqual(native_lookup_before_disambiguation(value,'Find someone else',gate),value)
   value['steps'][0]['intent']='contacts.delete'
   self.assertEqual(native_lookup_before_disambiguation(value,text,gate),value)
 async def test_correction_requires_separate_field_extraction_without_commit(self):
  for text in ('Move the appointment an hour later.','Push that study session back by sixty minutes.'):
   model=SimpleNamespace(chat_measured=AsyncMock(side_effect=[{'content':json.dumps({'disposition':'correct','proposal_id':'proposal-fixture','clarification':''})},{'content':json.dumps({'shift_minutes':'60'})}]))
   router=SimpleNamespace(route=Mock(return_value=SimpleNamespace(name='fixture-model')))
   result=await native_pending_request(model,router,text,{'native_proposals':[{'id':'proposal-fixture','body':{'title':'Synthetic'}}]})
   self.assertEqual(result['steps'][0]['intent'],'personal.correct')
   self.assertEqual(result['steps'][0]['entities'],{'proposal_id':'proposal-fixture','shift_minutes':'60'})
   self.assertEqual(model.chat_measured.await_count,2)
   self.assertEqual(model.chat_measured.call_args.kwargs['format']['properties']['duration_minutes']['pattern'],r'^[0-9]+$')

 async def test_unrelated_message_and_invalid_identity_do_not_commit(self):
  router=SimpleNamespace(route=Mock(return_value=SimpleNamespace(name='fixture-model')))
  model=SimpleNamespace(chat_measured=AsyncMock(return_value={'content':json.dumps({'disposition':'unrelated','proposal_id':'','clarification':''})}))
  context={'native_proposals':[{'id':'actual-proposal'}]}
  self.assertIsNone(await native_pending_request(model,router,'Explain this algorithm',context))
  model.chat_measured.return_value={'content':json.dumps({'disposition':'commit','proposal_id':'invented','clarification':''})}
  with self.assertRaises(ValueError):await native_pending_request(model,router,'Save it',context)

 async def test_compound_scope_is_validated_not_coerced(self):
  router=SimpleNamespace(route=Mock(return_value=SimpleNamespace(name='fixture-model')))
  model=SimpleNamespace(chat_measured=AsyncMock(return_value={'content':'{"single_operation": false}'}))
  self.assertEqual(await native_request_shape(model,router,'Create an event and a reminder'),12)
  model.chat_measured.return_value={'content':'{"single_operation": "false"}'}
  with self.assertRaises(ValueError):await native_request_shape(model,router,'Create a task')
