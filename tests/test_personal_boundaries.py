"""Focused recurrence, relationship, import and restore regressions; no model calls."""
import unittest,tempfile,sqlite3
from pathlib import Path
from datetime import datetime,timezone,timedelta
from tests import test_personal_core
from olive.personal.calendar import occurrences
from olive.personal.interchange import Interchange
from olive.personal.reminders import ReminderScheduler
from olive.personal.service import PersonalService
from olive.services.backup_service import BackupService


class BoundaryTests(unittest.TestCase):
 def setUp(self):
  fixture=test_personal_core.PersonalCoreTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  self.s=fixture.s;self.calendar=fixture.calendar

 def test_invalid_dst_instance_does_not_consume_count(self):
  event=self.s.save('event',{'calendar_id':self.calendar,'title':'DST series','start':'2026-03-07T02:30','end':'2026-03-07T03:30','timezone':'America/New_York','recurrence':'FREQ=DAILY;COUNT=3'})
  values=occurrences(event,datetime(2026,3,1,tzinfo=timezone.utc),datetime(2026,3,15,tzinfo=timezone.utc))
  self.assertEqual([r['start'][:10] for r in values],['2026-03-07','2026-03-09','2026-03-10'])

 def test_all_day_until_month_end_and_leap_recurrence(self):
  event=self.s.save('event',{'calendar_id':self.calendar,'title':'Date series','all_day':True,'start':'2026-01-31','end':'2026-02-01','recurrence':'FREQ=MONTHLY;UNTIL=20260531'})
  values=occurrences(event,datetime(2026,1,1,tzinfo=timezone.utc),datetime(2026,6,1,tzinfo=timezone.utc))
  self.assertEqual([r['start'] for r in values],['2026-01-31','2026-03-31','2026-05-31'])
  leap=self.s.save('event',{'calendar_id':self.calendar,'title':'Leap','all_day':True,'start':'2024-02-29','end':'2024-03-01','recurrence':'FREQ=YEARLY;COUNT=2'})
  self.assertEqual(occurrences(leap,datetime(2028,1,1,tzinfo=timezone.utc),datetime(2028,4,1,tzinfo=timezone.utc))[0]['start'],'2028-02-29')

 def test_fabricated_occurrence_rejected_and_ics_override_keeps_date(self):
  body={'calendar_id':self.calendar,'title':'Weekly','start':'2026-09-14T18:00','end':'2026-09-14T19:00','recurrence':'FREQ=WEEKLY;COUNT=3'}
  with self.assertRaisesRegex(ValueError,'original occurrence'):self.s.save('event',{**body,'exceptions':{'2026-09-15T18:00:00+02:00':{'title':'Not in series'}}})
  event=self.s.save('event',{**body,'exceptions':{'2026-09-21T18:00:00+02:00':{'title':'One changed'}}})
  io=Interchange(self.s);parsed=io.parse('event','ics',io.export('event','ics'))
  self.assertFalse(parsed['errors'])
  values=occurrences(parsed['rows'][0]['body'],datetime(2026,9,1,tzinfo=timezone.utc),datetime(2026,10,1,tzinfo=timezone.utc))
  self.assertEqual([(r['title'],r['start'][:10]) for r in values],[('Weekly','2026-09-14'),('One changed','2026-09-21'),('Weekly','2026-09-28')])
  changed=self.s.delete_occurrence(event['id'],event['revision'],values[1]['occurrence_id'])
  self.assertEqual(len(occurrences(changed,datetime(2026,9,1,tzinfo=timezone.utc),datetime(2026,10,1,tzinfo=timezone.utc))),2)

 def test_task_schedule_is_atomic_and_link_cleanup_is_bidirectional(self):
  task=self.s.save('task',{'title':'Work','project_id':'project-fixture'})
  event={'calendar_id':self.calendar,'title':'Work block','start':'2026-09-14T10:00','end':'2026-09-14T12:00'}
  with self.assertRaises(ValueError):self.s.schedule_task(task['id'],99,event)
  self.assertEqual(self.s.search('event')['items'],[])
  result=self.s.schedule_task(task['id'],task['revision'],event)
  self.assertEqual(result['task']['event_id'],result['event']['id'])
  self.assertEqual(result['event']['project_id'],'project-fixture')
  self.s.delete('event',result['event']['id'],result['event']['revision'])
  self.assertEqual(self.s.get('task',task['id'])['event_id'],'')

 def test_merge_cannot_drop_identifiers_or_skip_conflict_review(self):
  a=self.s.save('contact',{'display_name':'A','notes':'First'})
  b=self.s.save('contact',{'display_name':'B','notes':'Second','aliases':['Other']})
  preview=self.s.merge_preview(a['id'],b['id']);preview['conflicts']=[]
  with self.assertRaisesRegex(ValueError,'conflicting'):self.s.merge(preview)
  preview['conflicts_reviewed']=True;preview['proposed']['aliases']=[]
  with self.assertRaisesRegex(ValueError,'preserves'):self.s.merge(preview)
  self.assertEqual(self.s.get('contact',b['id'])['display_name'],'B')

 def test_backup_live_wal_and_dismissed_reminder_restored_without_replay(self):
  now=datetime(2026,9,14,10,tzinfo=timezone.utc)
  task=self.s.save('task',{'title':'Backup task'})
  self.s.save('reminder',{'target_kind':'task','target_id':task['id'],'at':now.isoformat(),'timezone':'UTC'})
  scheduler=ReminderScheduler(self.s,lambda *a:None,lambda:now);scheduler.tick();scheduler.act(scheduler.history()[0]['id'],'dismiss')
  # Hold a live connection so the backup must include committed WAL content.
  db=sqlite3.connect(self.s.store.path);self.addCleanup(db.close);db.execute('PRAGMA journal_mode=WAL')
  contact=self.s.save('contact',{'display_name':'Committed WAL fixture'})
  backup=BackupService(self.s.store.path.parent).create(components={'personal'})
  with tempfile.TemporaryDirectory() as target:
   BackupService(Path(target)).restore(backup,confirmed=True)
   restored=PersonalService(Path(target)/'personal.sqlite3')
   self.assertEqual(restored.get('contact',contact['id'])['display_name'],'Committed WAL fixture')
   self.assertEqual(ReminderScheduler(restored,lambda *a:None,lambda:now).tick()['new_count'],0)

 def test_catchup_is_one_summary_and_task_completion_cancels_pending(self):
  now=datetime(2026,9,14,10,tzinfo=timezone.utc);task=self.s.save('task',{'title':'Catchup'})
  for i in range(55):self.s.save('reminder',{'target_kind':'task','target_id':task['id'],'at':(now-timedelta(minutes=i)).isoformat(),'timezone':'UTC'})
  scheduler=ReminderScheduler(self.s,lambda *a:None,lambda:now)
  self.assertEqual(scheduler.tick()['new_count'],55);self.assertEqual(scheduler.tick()['new_count'],0)
  self.s.save('reminder',{'target_kind':'task','target_id':task['id'],'at':(now+timedelta(hours=1)).isoformat(),'timezone':'UTC'})
  scheduler.changed();scheduler.tick()
  self.s.save('task',{**self.s.store.body(task),'status':'completed'},task['id'],task['revision'])
  self.assertEqual(scheduler.tick(now+timedelta(hours=2))['new_count'],0)
