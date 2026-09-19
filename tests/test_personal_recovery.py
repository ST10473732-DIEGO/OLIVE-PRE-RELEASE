"""Cancellation, staged references and restore recovery with controlled clocks."""
import asyncio
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from olive.personal.store import WRITE_GUARD
from olive.personal.service import PersonalService
from olive.personal.interchange import Interchange
from olive.personal.reminders import ReminderScheduler
from olive.services.backup_service import BackupService


class PersonalRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.s=PersonalService(Path(self.tmp.name)/'personal.sqlite3')

 def test_optional_recovery_preserves_valid_preferences_and_calendar(self):
  import json
  profile=self.s.profile();body={**self.s.store.body(profile),'display_name':'Synthetic','timezone':'Broken/Zone'}
  with self.s.store.transaction() as db:db.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(body),profile['id']))
  recovered=self.s.profile()
  self.assertEqual(recovered['display_name'],'Synthetic')
  self.assertEqual(recovered['default_calendar'],profile['default_calendar'])
  self.assertEqual(recovered['timezone'],'Africa/Johannesburg')
  self.assertEqual(self.s.get('profile',profile['id'])['timezone'],'Broken/Zone')

 def test_timed_deadline_views_use_profile_date_not_stored_offset_date(self):
  self.s.clock=lambda:datetime(2026,9,14,12,tzinfo=timezone.utc)
  future=self.s.save('task',{'title':'Tomorrow locally','due_kind':'time','due':'2026-09-14T23:30:00+00:00','timezone':'UTC'})
  today=self.s.save('task',{'title':'Today locally','due_kind':'time','due':'2026-09-15T00:30:00+09:00','timezone':'Asia/Tokyo'})
  self.assertEqual([x['id'] for x in self.s.search('task',view='Today')['items']],[today['id']])
  self.assertEqual([x['id'] for x in self.s.search('task',view='Upcoming')['items']],[future['id']])

 def test_cancellation_before_commit_rolls_back_actual_insert(self):
  calls=[]
  def guard():
   calls.append(True)
   if len(calls)==2:raise asyncio.CancelledError()
  token=WRITE_GUARD.set(guard)
  try:
   with self.assertRaises(asyncio.CancelledError):self.s.save('contact',{'display_name':'Never committed'})
  finally:WRITE_GUARD.reset(token)
  self.assertEqual(self.s.search('contact')['items'],[])

 def test_export_cancellation_preserves_previous_file_and_cleans_owned_temp(self):
  from olive.personal.files import save_export
  destination=Path(self.tmp.name)/'synthetic.csv';destination.write_text('previous')
  calls=[]
  def guard():
   calls.append(True)
   if len(calls)==2:raise asyncio.CancelledError()
  token=WRITE_GUARD.set(guard)
  try:
   with self.assertRaises(asyncio.CancelledError):save_export(destination,'replacement')
  finally:WRITE_GUARD.reset(token)
  self.assertEqual(destination.read_text(),'previous')
  self.assertEqual(list(Path(self.tmp.name).glob('.olive-export-*')),[])

 def test_backup_rejects_missing_and_wrong_kind_relationships(self):
  import json
  from olive.personal.store import PersonalStore
  contact=self.s.save('contact',{'display_name':'Fixture'})
  task=self.s.save('task',{'title':'Linked fixture','contact_ids':[contact['id']]})
  PersonalStore.validate_database(self.s.store.path)
  with self.s.store.transaction() as db:db.execute('DELETE FROM links WHERE source=?',(task['id'],))
  with self.assertRaisesRegex(ValueError,'links do not match'):PersonalStore.validate_database(self.s.store.path)
  body={**self.s.store.body(task),'contact_ids':[self.s.profile()['default_calendar']]}
  with self.s.store.transaction() as db:db.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(body),task['id']))
  with self.assertRaisesRegex(ValueError,'relationship target'):PersonalStore.validate_database(self.s.store.path)

 def test_partial_restore_cannot_leave_project_references_dangling(self):
  import json
  self.s.projects=lambda:{'project-fixture':object()}
  task=self.s.save('task',{'title':'Project commitment','project_id':'project-fixture'})
  backup=BackupService(Path(self.tmp.name)).create(components={'personal'})
  with tempfile.TemporaryDirectory() as target:
   with self.assertRaisesRegex(ValueError,'missing project references'):BackupService(Path(target)).restore(backup,confirmed=True)
   self.assertFalse((Path(target)/'personal.sqlite3').exists())
   (Path(target)/'projects.json').write_text(json.dumps({'schema_version':1,'projects':[{'id':'project-fixture'}]}))
   BackupService(Path(target)).restore(backup,confirmed=True)
   restored=PersonalService(Path(target)/'personal.sqlite3',projects=self.s.projects)
   self.assertEqual(restored.get('task',task['id'])['project_id'],'project-fixture')

 def test_import_preview_reports_missing_relationship_before_approval(self):
  preview=Interchange(self.s).parse('contact','csv','name,project_ids\nSynthetic,"[""missing-project""]"\n')
  self.assertEqual(preview['rows'],[])
  self.assertIn('Linked project',preview['errors'][0]['message'])
  self.assertEqual(self.s.search('contact')['items'],[])

 def test_completed_task_cannot_create_an_orphan_work_block(self):
  task=self.s.save('task',{'title':'Finished','status':'completed'})
  with self.assertRaisesRegex(ValueError,'Reopen'):
   self.s.schedule_task(task['id'],task['revision'],{'calendar_id':self.s.profile()['default_calendar'],'title':'Unexpected','start':'2026-09-14T10:00','end':'2026-09-14T11:00'})
  self.assertEqual(self.s.search('event')['items'],[])

 def test_reopening_rearms_future_cancelled_reminder_without_past_replay(self):
  now=datetime(2026,9,14,10,tzinfo=timezone.utc)
  task=self.s.save('task',{'title':'Reopened fixture'})
  self.s.save('reminder',{'target_kind':'task','target_id':task['id'],'at':(now+timedelta(hours=1)).isoformat(),'timezone':'UTC'})
  scheduler=ReminderScheduler(self.s,lambda *args:None,lambda:now);scheduler.tick()
  completed=self.s.save('task',{**self.s.store.body(task),'status':'completed'},task['id'],task['revision'])
  scheduler.changed();scheduler.tick();self.assertEqual(scheduler.history()[0]['state'],'cancelled')
  self.s.save('task',{**self.s.store.body(completed),'status':'open'},task['id'],completed['revision'])
  scheduler.changed();scheduler.tick();self.assertEqual(scheduler.history(),[])
  self.assertEqual(scheduler.tick(now+timedelta(hours=1))['new_count'],1)
  scheduler.act(scheduler.history()[0]['id'],'dismiss')
  scheduler.changed();self.assertEqual(scheduler.tick(now+timedelta(hours=2))['new_count'],0)

 def test_scheduler_reports_storage_failure_and_recovers_without_private_error(self):
  import sqlite3
  from unittest.mock import Mock,patch
  published=[];scheduler=ReminderScheduler(self.s,lambda event,data:published.append(data))
  scheduler.tick=Mock(side_effect=[sqlite3.OperationalError('private fixture path'),{'new_count':0,'state':'ready'}])
  async def advance(_):
   if scheduler.tick.call_count==2:scheduler.stopping=True
  async def exercise():
   with patch('olive.personal.reminders.asyncio.sleep',side_effect=advance):await scheduler.run()
  asyncio.run(exercise())
  self.assertEqual([x['state'] for x in published],['degraded','ready'])
  self.assertNotIn('private fixture',str(published));self.assertEqual(scheduler.error,'')

 def test_restoring_undelivered_old_reminder_does_not_replay_catchup(self):
  now=datetime.now(timezone.utc)
  task=self.s.save('task',{'title':'Restored fixture'})
  self.s.save('reminder',{'target_kind':'task','target_id':task['id'],'at':(now-timedelta(hours=1)).isoformat(),'timezone':'UTC'})
  archive=BackupService(Path(self.tmp.name)).create(components={'personal'})
  with tempfile.TemporaryDirectory() as target:
   BackupService(Path(target)).restore(archive,confirmed=True)
   restored=PersonalService(Path(target)/'personal.sqlite3')
   scheduler=ReminderScheduler(restored,lambda *args:None,lambda:now+timedelta(minutes=1))
   self.assertEqual(scheduler.tick()['new_count'],0)
   self.assertEqual(scheduler.history()[0]['state'],'restored')
   restored.save('reminder',{'target_kind':'task','target_id':task['id'],'at':now.isoformat(),'timezone':'UTC'})
   scheduler.changed()
   self.assertEqual(scheduler.tick()['new_count'],1)

 def test_non_utc_reminder_canonical_value_survives_validation_and_restore(self):
  from olive.personal.reminders import validate_reminder
  task=self.s.save('task',{'title':'Timezone fixture'})
  reminder=self.s.save('reminder',{'target_kind':'task','target_id':task['id'],'at':'2026-09-14T10:00:00+02:00','timezone':'Africa/Johannesburg'})
  self.assertEqual(reminder['at'],'2026-09-14T08:00:00+00:00')
  self.assertEqual(validate_reminder(self.s.store.body(reminder)),self.s.store.body(reminder))
  archive=BackupService(Path(self.tmp.name)).create(components={'personal'})
  with tempfile.TemporaryDirectory() as target:
   BackupService(Path(target)).restore(archive,confirmed=True)
   restored=PersonalService(Path(target)/'personal.sqlite3')
   self.assertEqual(restored.get('reminder',reminder['id'])['at'],reminder['at'])

 def test_import_source_is_durable_and_cannot_be_supplied_as_record_body(self):
  io=Interchange(self.s);preview=io.parse('contact','csv','uid,name\nsource-fixture,Synthetic Source\n')
  result=io.commit(preview['id'],{});record=self.s.get('contact',result['records'][0]['id'])
  self.assertEqual(record['provenance']['created']['source_hash'],preview['source_hash'])
  restarted=PersonalService(self.s.store.path)
  self.assertEqual(restarted.get('contact',record['id'])['provenance'],record['provenance'])
  with self.assertRaises(ValueError):self.s.save('contact',{'display_name':'Spoof','provenance':{'origin':'trusted'}})

 def test_explicit_execution_link_never_changes_agent_attempt(self):
  agent={'attempt-fixture':{'state':'paused'}}
  self.s.agent_tasks=lambda:agent
  task=self.s.save('task',{'title':'Linked personal commitment','agent_task_id':'attempt-fixture'})
  self.s.save('task',{**self.s.store.body(task),'status':'completed'},task['id'],task['revision'])
  self.assertEqual(agent,{'attempt-fixture':{'state':'paused'}})
  with self.assertRaisesRegex(ValueError,'Agent attempt'):self.s.save('task',{'title':'Unresolved','agent_task_id':'not-an-attempt'})

 def test_additive_v2_migration_retains_records_without_fabricating_provenance(self):
  import sqlite3
  from contextlib import closing
  record=self.s.save('contact',{'display_name':'Earlier fixture'})
  with closing(sqlite3.connect(self.s.store.path)) as db:
   db.execute('ALTER TABLE records DROP COLUMN provenance');db.execute('PRAGMA user_version=2');db.commit()
  migrated=PersonalService(self.s.store.path)
  restored=migrated.get('contact',record['id'])
  self.assertEqual(restored['display_name'],record['display_name']);self.assertEqual(restored['revision'],record['revision'])
  self.assertEqual(restored['provenance'],{})
