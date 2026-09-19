"""Native transactional services and calendar arithmetic; isolated synthetic data."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from olive.personal.service import PersonalService
from olive.personal.store import RevisionConflict
from olive.personal.calendar import occurrences
from olive.personal.reminders import ReminderScheduler


class PersonalCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'personal.sqlite3'
        self.s=PersonalService(self.path,lambda:{'project-fixture':object()})
        self.calendar=self.s.profile()['default_calendar']

    def event(self,**changes):
        return self.s.save('event',dict(calendar_id=self.calendar,title='Fixture event',start='2026-09-14T18:00',end='2026-09-14T20:00',timezone='Africa/Johannesburg',**changes))

    def test_profile_restart_revision_and_invalid_timezone(self):
        p=self.s.profile();body=self.s.store.body(p);body['display_name']='Fixture person'
        self.s.save('profile',body,p['id'],p['revision'])
        self.assertEqual(PersonalService(self.path).profile()['display_name'],'Fixture person')
        with self.assertRaises(RevisionConflict):self.s.save('profile',body,p['id'],p['revision'])
        with self.assertRaises(ValueError):self.s.save('profile',{**body,'timezone':'Not/AZone'},p['id'],2)

    def test_contacts_ambiguity_aliases_merge_and_relationships(self):
        a=self.s.save('contact',{'display_name':'James Fixture','aliases':['Jay'],'project_ids':['project-fixture']})
        b=self.s.save('contact',{'display_name':'James Fixture','organization':'Different fixture'})
        self.assertEqual(self.s.resolve_contact('James Fixture')['status'],'ambiguous')
        self.assertEqual(self.s.resolve_contact('Jay')['candidates'][0]['id'],a['id'])
        e=self.event(contact_ids=[b['id']])
        preview=self.s.merge_preview(a['id'],b['id']);preview['conflicts_reviewed']=True
        self.s.merge(preview)
        self.assertEqual(self.s.get('event',e['id'])['contact_ids'],[a['id']])
        with self.assertRaises(LookupError):self.s.get('contact',b['id'])
        with self.assertRaises(LookupError):self.s.merge(preview)

    def test_event_revision_all_day_overnight_and_exceptions(self):
        e=self.event(recurrence='FREQ=WEEKLY;COUNT=3')
        start=datetime(2026,9,1,tzinfo=timezone.utc);end=datetime(2026,10,1,tzinfo=timezone.utc)
        values=occurrences(e,start,end);self.assertEqual(len(values),3)
        body=self.s.store.body(e);key=values[1]['occurrence_id'];body['exceptions']={key:{'title':'Changed occurrence'}}
        changed=self.s.save('event',body,e['id'],e['revision'])
        self.assertEqual([x['title'] for x in occurrences(changed,start,end)],['Fixture event','Changed occurrence','Fixture event'])
        all_day=self.s.save('event',{'calendar_id':self.calendar,'title':'All day','all_day':True,'start':'2026-09-20','end':'2026-09-21'})
        self.assertEqual(occurrences(all_day,start,end)[0]['end'],'2026-09-21')
        overnight=self.s.save('event',{'calendar_id':self.calendar,'title':'Overnight','start':'2026-09-20T23:00','end':'2026-09-21T01:00'})
        self.assertEqual(len(occurrences(overnight,start,end)),1)
        with self.assertRaises(RevisionConflict):self.s.save('event',body,e['id'],e['revision'])

    def test_dst_gap_overlap_invalid_end_and_calendar_reference(self):
        data={'calendar_id':self.calendar,'title':'DST','timezone':'America/New_York','start':'2026-03-08T02:30','end':'2026-03-08T04:00'}
        with self.assertRaisesRegex(ValueError,'does not exist'):self.s.save('event',data)
        data.update(start='2026-11-01T01:30',end='2026-11-01T03:00')
        with self.assertRaisesRegex(ValueError,'occurs twice'):self.s.save('event',data)
        data['start_fold']=1;self.assertIn('-05:00',self.s.save('event',data)['start'])
        with self.assertRaises(ValueError):self.s.save('event',{**data,'end':'2026-10-31T10:00'})
        with self.assertRaises(LookupError):self.s.save('event',{**data,'calendar_id':'unrelated'})

    def test_free_time_merges_overlaps_and_adjacent_intervals(self):
        for start,end in [('09:00','10:00'),('09:30','11:00'),('11:00','12:00')]:
            self.s.save('event',{'calendar_id':self.calendar,'title':'Busy','start':'2026-09-14T'+start,'end':'2026-09-14T'+end})
        slots=self.s.availability('2026-09-14T00:00:00+02:00','2026-09-15T00:00:00+02:00',120)
        self.assertEqual(slots[0]['start'],'2026-09-14T12:00:00+02:00')
        self.assertEqual(slots[0]['status'],'proposed')

    def test_tasks_reminders_snooze_dismiss_restart_and_deletion(self):
        now=datetime(2026,9,14,10,tzinfo=timezone.utc)
        t=self.s.save('task',{'title':'Fixture task','project_id':'project-fixture'})
        self.s.save('reminder',{'target_kind':'task','target_id':t['id'],'at':'2026-09-14T12:00:00+02:00'})
        scheduler=ReminderScheduler(self.s,lambda *a:None,lambda:now)
        self.assertEqual(scheduler.tick()['new_count'],1)
        delivery=scheduler.history()[0];scheduler.act(delivery['id'],'snooze',10)
        self.assertEqual(scheduler.tick()['new_count'],0)
        now+=timedelta(minutes=10);self.assertEqual(scheduler.tick()['new_count'],1)
        scheduler.act(delivery['id'],'dismiss')
        restarted=ReminderScheduler(PersonalService(self.path),lambda *a:None,lambda:now)
        self.assertEqual(restarted.tick()['new_count'],0)
        self.assertEqual(self.s.get('task',t['id'])['status'],'open')
        self.s.delete('task',t['id'],t['revision'])
        self.assertEqual(self.s.search('reminder')['items'],[])
