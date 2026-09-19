"""Real runtime/router and native records; semantic interpretation is controlled."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host
from olive.personal.service import PersonalService
from olive.personal.errors import PersonalOperationError


class NativeCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='olive-m3-composition-')
        self.host=Host(lambda event:None)
        self.s=ServiceContainer(self.host.publish,self.host.confirm,data_dir=self.temp.name,migrate=False)
        self.host.services=self.s

    async def asyncTearDown(self):
        await self.host.shutdown();self.temp.cleanup()

    async def test_compound_proposals_stay_separate_and_cancel_only_selected_revision(self):
        chat_id=self.s.current_chat_id
        self.s.interaction.interpreter.interpret=AsyncMock(return_value={
            'confidence':1.,'clarification':'','steps':[
                {'intent':'tasks.create','entities':{'title':title},'references':{}}
                for title in ('Read the fixture chapter','Review the fixture notes')]})
        await self.host.execute('interaction.submit',{'chat_id':chat_id,'text':'Plan reading the chapter and reviewing the notes as separate tasks.'})
        proposals=self.s.interaction.context(chat_id).personal_pending
        self.assertEqual(len(proposals),2)
        self.assertEqual(self.s.personal.records.search('task')['items'],[])
        first,second=list(proposals.values())
        with self.assertRaisesRegex(ValueError,'proposal changed'):
            await self.host.execute('personal.review',{'chat_id':chat_id,'proposal_id':first['id'],'revision':first['revision']+1,'decision':'cancel'})
        await self.host.execute('personal.review',{'chat_id':chat_id,'proposal_id':first['id'],'revision':first['revision'],'decision':'cancel'})
        self.assertEqual(list(proposals),[second['id']])
        self.assertEqual(self.s.personal.records.search('task')['items'],[])

    async def test_native_id_from_another_profile_cannot_be_read(self):
        with tempfile.TemporaryDirectory(prefix='olive-m3-other-') as other:
            isolated=PersonalService(Path(other)/'personal.sqlite3')
            contact=isolated.save('contact',{'display_name':'Other isolated fixture'})
            with self.assertRaises(PersonalOperationError):
                await self.host.execute('contacts.get',{'record_id':contact['id']})
            self.assertEqual(self.s.personal.records.search('contact')['items'],[])

    async def test_unsaved_new_event_cannot_link_reminder_to_previous_event(self):
        chat_id=self.s.current_chat_id
        old=self.s.personal.records.save('event',{'title':'Previously selected fixture','calendar_id':self.s.personal.records.profile()['default_calendar'],'timezone':'Africa/Johannesburg','start':'2026-09-14T08:00:00+02:00','end':'2026-09-14T09:00:00+02:00'})
        context=self.s.interaction.context(chat_id)
        context.entities['event_id']=old['id']
        self.s.interaction.interpreter.interpret=AsyncMock(return_value={
            'confidence':1.,'clarification':'','steps':[
                {'intent':'calendar.create','entities':{'title':'New fixture','start':'2026-09-15T09:00:00+02:00','duration_minutes':'60'},'references':{}},
                {'intent':'reminders.create','entities':{'offset_minutes':'30'},'references':{'event_id':'event_id'}}]})
        await self.host.execute('interaction.submit',{'chat_id':chat_id,'text':'Prepare a new appointment and remind me before that appointment.'})
        self.assertEqual(len(context.personal_pending),1)
        self.assertEqual(next(iter(context.personal_pending.values()))['method'],'calendar.create')
        self.assertNotIn('event_id',context.entities)
        self.assertEqual(self.s.personal.records.search('reminder')['items'],[])

    async def test_availability_single_date_does_not_expand_to_a_week(self):
        from olive.personal.language import PersonalLanguage
        context=self.s.interaction.context(self.s.current_chat_id)
        language=PersonalLanguage(self.s)
        one=await language.route({'intent':'calendar.free_busy','entities':{'date':'2026-09-14','duration_minutes':'120'}},context)
        self.assertIn('2026-09-14T09:00:00+02:00 to 2026-09-14T11:00:00+02:00',one)
        self.assertNotIn('2026-09-15',one)
        range_result=await language.route({'intent':'calendar.free_busy','entities':{'date':'2026-09-14','date_until':'2026-09-16','duration_minutes':'120'}},context)
        self.assertIn('2026-09-15T09:00:00+02:00',range_result)
        self.assertNotIn('2026-09-16',range_result)
