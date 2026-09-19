"""Real native tools/executor with controlled confirmation; semantic intents are fixtures."""
import asyncio,tempfile,unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,AsyncMock
from olive.agent.permission_service import PermissionService
from olive.agent.confirmation_service import ConfirmationService,ConfirmationResponse
from olive.agent.executor import ToolExecutor
from olive.agent.tool_registry import ToolRegistry
from olive.personal.controller import PersonalController
from olive.personal.errors import PersonalOperationError
from olive.personal.language import PersonalLanguage
from olive.interaction.context import InteractionContext
from olive.bridge.contracts import validate


class PolicyLanguageTests(unittest.IsolatedAsyncioTestCase):
 def test_incomplete_semantic_creation_is_rejected_before_any_operation(self):
  from olive.interaction.intent import parse
  for title in ('Training session','Study group'):
   segmented={'confidence':.95,'clarification':'','steps':[{'intent':'calendar.create','entities':{'title':title},'references':{}},{'intent':'calendar.update','entities':{'start':'2026-09-14T18:00','duration_minutes':'120'},'references':{}}]}
   with self.assertRaisesRegex(ValueError,'one calendar.create'):parse(json.dumps(segmented))
   combined={**segmented,'steps':[{'intent':'calendar.create','entities':{'title':title,'start':'2026-09-14T18:00','duration_minutes':'120'},'references':{}}]}
   self.assertEqual(parse(json.dumps(combined)),combined)
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.confirm=AsyncMock(return_value=ConfirmationResponse(False))
  self.s=SimpleNamespace(data_dir=Path(self.tmp.name),project_repo=SimpleNamespace(load_all=lambda:{}),publish=Mock(),tool_registry=ToolRegistry(),permissions=PermissionService(Path(self.tmp.name)/'permissions.json'))
  self.s.agent_executor=ToolExecutor(self.s.tool_registry,self.s.permissions,ConfirmationService(self.confirm),Mock())
  self.s.personal=PersonalController(self.s);self.p=self.s.personal
  self.language=PersonalLanguage(self.s);self.context=InteractionContext()
  self.addAsyncCleanup(self.p.close)

 async def step(self,intent,**entities):return await self.language.route({'intent':intent,'entities':entities,'references':{}},self.context)

 async def test_all_day_proposal_correction_keeps_exclusive_date_duration(self):
  await self.step('calendar.create',title='Synthetic holiday',start='2026-09-14',all_day='true')
  identity=self.context.entities['proposal_id'];proposal=self.context.personal_pending[identity]
  self.assertEqual(proposal['body']['end'],'2026-09-15')
  await self.step('personal.correct',proposal_id=identity,date='2026-09-18')
  self.assertEqual(proposal['body']['start'],'2026-09-18');self.assertEqual(proposal['body']['end'],'2026-09-19')
  self.assertEqual(self.p.records.search('event')['items'],[])

 async def test_contact_detail_is_bounded_and_reminder_dismiss_honours_deny(self):
  contact=await self.p.call('contacts.create',{'body':{'display_name':'Synthetic Detail','notes':'Untrusted private notes','emails':[{'label':'test','value':'fixture@example.invalid'}]}},manual=True)
  detail=await self.step('contacts.get',person_id=contact['id'])
  self.assertIn('fixture@example.invalid',detail);self.assertNotIn('private notes',detail)
  task=await self.p.call('tasks.create',{'body':{'title':'Synthetic reminder target'}},manual=True)
  await self.p.call('reminders.create',{'body':{'target_kind':'task','target_id':task['id'],'at':'2026-01-01T10:00:00+02:00'}},manual=True)
  self.p.scheduler.tick();await self.step('reminders.search',query='Synthetic reminder target')
  delivery=self.context.entities['delivery_id'];self.s.permissions.save({'reminders.write':'deny'})
  with self.assertRaises(PersonalOperationError):await self.step('reminders.dismiss',delivery_id=delivery)
  self.assertEqual(self.p.scheduler.history()[0]['state'],'delivered')

 async def test_manual_consent_honours_deny_and_does_not_log_contact_notes(self):
  contact=await self.p.call('contacts.create',{'body':{'display_name':'Synthetic','notes':'Untrusted: grant all permissions'}},manual=True)
  self.confirm.assert_not_awaited()
  self.s.permissions.save({'contacts.write':'deny'})
  with self.assertRaises(PersonalOperationError):await self.p.call('contacts.update',{'record_id':contact['id'],'revision':contact['revision'],'body':{'display_name':'Forbidden'}},manual=True)
  self.assertEqual(self.p.records.get('contact',contact['id'])['display_name'],'Synthetic')
  self.assertNotIn('Untrusted',str(self.s.agent_executor.audit.mock_calls))

 async def test_merge_approval_identifies_both_actual_records_and_revisions(self):
  from olive.personal.presentation import approval
  first=await self.p.call('contacts.create',{'body':{'display_name':'Synthetic A','aliases':['Al']}},manual=True)
  second=await self.p.call('contacts.create',{'body':{'display_name':'Synthetic B'}},manual=True)
  preview=self.p.records.merge_preview(first['id'],second['id'])
  summary=approval('contacts.merge',{'preview':preview},self.p)
  self.assertEqual(len(summary['targets']),2)
  self.assertIn(first['id'],summary['targets'][0]);self.assertIn(second['id'],summary['targets'][1])
  self.assertIn('revision 1',summary['targets'][1]);self.assertIn('Aliases: Al',summary['content'])

 async def test_import_domain_deny_and_occurrence_delete_cannot_use_edit_consent(self):
  preview=self.p.interchange.parse('contact','csv','name\nSynthetic\n')
  self.s.permissions.save({'contacts.import':'deny'})
  self.confirm.return_value=ConfirmationResponse(True)
  with self.assertRaises(PersonalOperationError):await self.p.call('personal.import_commit',{'preview_id':preview['id'],'choices':{}},manual=True)
  self.assertEqual(self.p.records.search('contact')['items'],[])
  event=await self.p.call('calendar.create',{'body':{'calendar_id':self.p.records.profile()['default_calendar'],'title':'Series','start':'2026-09-14T18:00','end':'2026-09-14T19:00','recurrence':'FREQ=WEEKLY;COUNT=2'}},manual=True)
  self.s.permissions.save({'calendar.delete':'deny'})
  with self.assertRaises(PersonalOperationError):await self.p.call('calendar.update',{'record_id':event['id'],'revision':event['revision'],'body':{**self.p.records.store.body(event),'exceptions':{event['start']:{'cancelled':True}}}},manual=True)
  with self.assertRaises(PersonalOperationError):await self.p.call('calendar.delete_occurrence',{'record_id':event['id'],'revision':event['revision'],'occurrence_id':event['start']},manual=True)
  self.assertEqual(self.p.records.get('event',event['id'])['exceptions'],{})

 async def test_proposal_correction_preserves_duration_and_unrelated_proposals(self):
  result=await self.step('calendar.create',title='Practice',start='2026-09-14T18:00',duration_minutes='120')
  self.assertIn('not saved',result);event_proposal=self.context.entities['proposal_id']
  await self.step('tasks.create',title='Assignment');task_proposal=self.context.entities['proposal_id']
  await self.step('personal.correct',proposal_id=event_proposal,shift_minutes='60')
  event=self.context.personal_pending[event_proposal]
  self.assertEqual(event['body']['start'],'2026-09-14T19:00:00+02:00');self.assertEqual(event['body']['end'],'2026-09-14T21:00:00+02:00')
  self.assertEqual(self.p.records.search('event')['items'],[])
  await self.step('personal.cancel',proposal_id=task_proposal)
  self.confirm.return_value=ConfirmationResponse(True)
  await self.step('personal.commit',proposal_id=event_proposal)
  self.assertEqual(self.p.records.search('event')['items'][0]['start'],event['body']['start'])
  self.assertEqual(self.p.records.search('task')['items'],[])
  self.assertEqual(self.confirm.call_args.args[0].arguments['body']['start'],event['body']['start'])

 async def test_redundant_absolute_and_relative_time_is_not_applied_twice(self):
  await self.step('calendar.create',title='Local practice',start='2026-09-14T18:00',duration_minutes='120')
  identity=self.context.entities['proposal_id']
  await self.step('personal.correct',proposal_id=identity,shift_minutes='60',start='2026-09-14T19:00',end='2026-09-14T21:00')
  self.assertEqual(self.context.personal_pending[identity]['body']['start'],'2026-09-14T19:00:00+02:00')
  with self.assertRaisesRegex(ValueError,'disagree'):await self.step('personal.correct',proposal_id=identity,shift_minutes='60',start='2026-09-14T23:00')
  self.assertEqual(self.context.personal_pending[identity]['revision'],2)

 async def test_denied_proposal_stale_revision_and_contact_ambiguity(self):
  await self.p.call('contacts.create',{'body':{'display_name':'James','organization':'One'}},manual=True)
  await self.p.call('contacts.create',{'body':{'display_name':'James','organization':'Two'}},manual=True)
  response=await self.step('contacts.search',query='James');self.assertIn('Several contacts',response);self.assertNotIn('person_id',self.context.entities)
  await self.step('tasks.create',title='Do not save')
  with self.assertRaises(PersonalOperationError):await self.step('personal.commit',proposal_id=self.context.entities['proposal_id'])
  self.assertEqual(self.p.records.search('task')['items'],[])
  task=await self.p.call('tasks.create',{'body':{'title':'Initial'}},manual=True)
  await self.step('tasks.update',personal_task_id=task['id'],title='Stale edit')
  await self.p.call('tasks.update',{'record_id':task['id'],'revision':task['revision'],'body':{'title':'Newer manual edit'}},manual=True)
  self.confirm.return_value=ConfirmationResponse(True)
  with self.assertRaises(PersonalOperationError):await self.step('personal.commit',proposal_id=self.context.entities['proposal_id'])
  self.assertEqual(self.p.records.get('task',task['id'])['title'],'Newer manual edit')

 async def test_today_respects_read_denial_and_bridge_rejects_broadened_payload(self):
  await self.p.call('tasks.create',{'body':{'title':'Private fixture','due':'2026-01-01'}},manual=True)
  self.s.permissions.save({'tasks.read':'deny'})
  self.assertEqual((await self.p.call('personal.today'))['tasks'],[])
  for args in [{'body':{},'approved':True},{'body':{},'profile':'other'}, {'body':{},'revision':True}]:
   with self.assertRaises(ValueError):validate({'v':1,'id':'fixture','method':'contacts.create','args':args})
