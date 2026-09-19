import unittest
from tests import test_personal_core
from olive.personal.interchange import Interchange


class InterchangeTests(unittest.TestCase):
    def setUp(self):
        fixture=test_personal_core.PersonalCoreTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.s=fixture.s;self.calendar=fixture.calendar;self.io=Interchange(self.s)

    def test_csv_preview_commit_reimport_and_formula_export(self):
        preview=self.io.parse('contact','csv','name,email,notes\nAlex Fixture,alex@example.test,"=1+1"\n')
        self.assertEqual(self.s.search('contact')['items'],[])
        result=self.io.commit(preview['id'],{});self.assertEqual(result['saved_count'],1)
        second=self.io.parse('contact','csv','name,email,notes\nAlex Fixture,alex@example.test,"=1+1"\n')
        self.assertEqual(second['rows'][0]['action'],'skip')
        exported=self.io.export('contact','csv');self.assertIn("'=1+1",exported)
        preview=self.io.parse('contact','csv',exported);self.assertFalse(preview['errors'])

    def test_vcard_multiple_identifiers_and_external_metadata(self):
        c=self.s.save('contact',{'display_name':'Synthetic Person','emails':[{'label':'work','value':'fixture@example.test'}],
                               'aliases':['Fixture'],'external_ids':[{'label':'example','value':'local-handle'}]})
        text=self.io.export('contact','vcf');preview=self.io.parse('contact','vcf',text)
        self.assertEqual(preview['rows'][0]['uid'],c['uid'])
        self.assertEqual(preview['rows'][0]['body']['external_ids'],c['external_ids'])
        self.assertFalse(preview['errors'])

    def test_ics_roundtrip_recurrence_and_occurrence_override(self):
        e=self.s.save('event',{'calendar_id':self.calendar,'title':'Local recurring','start':'2026-09-14T18:00','end':'2026-09-14T19:00',
                             'recurrence':'FREQ=WEEKLY;COUNT=3','exceptions':{'2026-09-21T18:00:00+02:00':{'title':'Changed'}}})
        exported=self.io.export('event','ics');preview=self.io.parse('event','ics',exported,self.calendar)
        self.assertFalse(preview['errors'],preview['errors'])
        self.assertEqual(preview['rows'][0]['uid'],e['uid'])
        self.assertIn('2026-09-21T18:00:00+02:00',preview['rows'][0]['body']['exceptions'])

    def test_invalid_import_staged_and_deleted_uid_not_reactivated(self):
        preview=self.io.parse('contact','csv','name,email\nBad,not-an-email\n')
        self.assertTrue(preview['errors'])
        with self.assertRaises(ValueError):self.io.commit(preview['id'],{})
        c=self.s.save('contact',{'display_name':'Delete fixture'});text=self.io.export('contact','vcf')
        self.s.delete('contact',c['id'],c['revision'])
        again=self.io.parse('contact','vcf',text)
        self.assertEqual(again['rows'][0]['action'],'skip')
        with self.assertRaises(ValueError):self.io.commit(again['id'],{'0':'create'})

    def test_stale_import_update_cannot_overwrite_newer_edit(self):
        c=self.s.save('contact',{'display_name':'Initial'});text=self.io.export('contact','csv').replace('Initial','Imported')
        preview=self.io.parse('contact','csv',text)
        self.s.save('contact',{'display_name':'Newer'},c['id'],c['revision'])
        with self.assertRaises(ValueError):self.io.commit(preview['id'],{})
        self.assertEqual(self.s.get('contact',c['id'])['display_name'],'Newer')
