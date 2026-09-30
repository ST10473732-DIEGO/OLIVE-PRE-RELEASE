"""OLIVE Draw / DrawNote from Chat: literal navigation only, Notes routing unchanged."""
import tempfile
import unittest

from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host
from olive.draw.chat import parse
from olive.notes.chat import parse as parse_notes
from olive.services.model_registry import ModelCapability


class DrawGrammarTests(unittest.TestCase):
    def test_literal_requests_only(self):
        for text in ('Open OLIVE Draw', 'Open Draw', 'open draw.', 'Please open the Draw app', 'Go to Draw',
                     'Switch to OLIVE Draw', 'Open DrawNote and go to Draw', 'open olive drawnote, then show the draw tab',
                     'Open my drawings'):
            self.assertEqual(parse(text)['action'], 'open_draw', text)
        for text in ('Open OLIVE DrawNote', 'open drawnote', 'Show DrawNote', 'Open Draw Note'):
            self.assertEqual(parse(text)['action'], 'open_drawnote', text)
        self.assertEqual(parse('Open DrawNote and go to Notes')['action'], 'open_notes')
        self.assertEqual(parse('New drawing')['action'], 'create')
        self.assertEqual(parse('Create a new drawing called "Site plan"')['title'], 'Site plan')
        self.assertEqual(parse('Open my "Site plan" drawing')['title'], 'Site plan')
        self.assertEqual(parse('open drawing called Sketch')['title'], 'Sketch')
        self.assertEqual(parse('List my drawings')['action'], 'list')
        for other in ('draw a conclusion', 'Draw a cat', 'Draw me a map of Lisbon', 'Can you draw a conclusion from this?',
                      'Open the drawer', 'What does draw mean?', 'Make a drawing of a sunset', 'Open Notes',
                      'Open my Shopping note', 'Open LibreOffice Draw', 'open drawings from the 1900s',
                      'Draw', 'Open'):
            self.assertIsNone(parse(other), other)

    def test_notes_requests_still_parse_as_notes(self):
        self.assertEqual(parse_notes('Open OLIVE Notes')['action'], 'open_all')
        self.assertEqual(parse_notes('Open my Shopping note')['title'], 'Shopping')
        self.assertIsNone(parse('Open OLIVE Notes'))
        self.assertIsNone(parse('Open my Shopping note'))


class DrawChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-draw-chat-')
        self.events = []
        self.host = Host(self.events.append)
        self.s = ServiceContainer(self.host.publish, self.host.confirm, data_dir=self.temp.name, migrate=False)
        self.host.services = self.s
        self.chat = self.s.chats[self.s.current_chat_id]
        self.s.model_registry.models['gpt-oss:20b'] = ModelCapability('gpt-oss:20b', True, ('completion',), 32768, 'general')
        self.s.ollama._context_length_cache['gpt-oss:20b'] = 32768
        self.s.presets.apply(self.chat, 'normal')
        self.calls = []
        self.s.ollama.client.chat = self.infer

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.temp.cleanup()

    async def infer(self, **kwargs):
        self.calls.append(kwargs)
        async def chunks():
            yield {'message': {'content': 'A model answer.'}, 'done': True, 'done_reason': 'stop'}
        return chunks()

    async def say(self, text):
        await self.host.execute('interaction.submit', {'chat_id': self.chat.id, 'text': text})
        return self.chat.messages[-1]

    def navigations(self, topic):
        return [e['data'] for e in self.events if e['topic'] == topic]

    async def test_open_draw_drawnote_and_notes(self):
        self.assertEqual((await self.say('Open OLIVE Draw')).content, 'Opened OLIVE Draw.')
        self.assertEqual(self.navigations('drawnote.navigate')[-1], {'section': 'draw'})
        await self.say('Open DrawNote and go to Draw')
        self.assertEqual(self.navigations('drawnote.navigate')[-1], {'section': 'draw'})
        await self.say('Open OLIVE DrawNote')
        self.assertEqual(self.navigations('drawnote.navigate')[-1], {'section': ''})
        await self.say('Open DrawNote and go to Notes')
        self.assertEqual(self.navigations('notes.navigate')[-1], {})
        # The existing Notes command is untouched and still lands in Notes.
        self.assertEqual((await self.say('Open OLIVE Notes')).content, 'Opened OLIVE Notes.')
        self.assertEqual(len(self.navigations('notes.navigate')), 2)
        self.assertEqual(self.calls, [])   # No model was involved.

    async def test_open_note_by_title_still_routes_to_notes(self):
        await self.say('Create a note called Shopping')
        before = len(self.navigations('drawnote.navigate'))
        answer = await self.say('Open my Shopping note')
        self.assertIn('Opened “Shopping” in OLIVE Notes', answer.content)
        self.assertTrue(self.navigations('notes.navigate')[-1]['note_id'])
        self.assertEqual(len(self.navigations('drawnote.navigate')), before)

    async def test_new_open_list_drawings(self):
        answer = await self.say('New drawing called Garden')
        self.assertIn('Created “Garden” (1920 × 1080) in OLIVE Draw', answer.content)
        garden = self.s.draw.list_drawings()['drawings'][0]
        self.assertEqual(self.navigations('drawnote.navigate')[-1], {'section': 'draw', 'drawing_id': garden['drawing_id']})
        self.s.draw.create('Garden')
        answer = await self.say('Open my "Garden" drawing')
        self.assertIn('You have 2 drawings called “Garden”', answer.content)
        answer = await self.say('2')
        self.assertIn('Opened “Garden” in OLIVE Draw', answer.content)
        self.assertEqual(self.navigations('drawnote.navigate')[-1]['section'], 'draw')
        # The number choice was single-use.
        await self.say('2')
        self.assertEqual(len(self.calls), 1)
        answer = await self.say('Open drawing called Nowhere')
        self.assertIn('couldn’t find a drawing called “Nowhere”', answer.content)
        answer = await self.say('List my drawings')
        self.assertIn('You have 2 drawing(s)', answer.content)

    async def test_ordinary_sentences_reach_the_model_not_draw(self):
        before = len(self.events)
        await self.say('Can you draw a conclusion from these results?')
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(any(e['topic'] == 'drawnote.navigate' for e in self.events[before:]))

    async def test_navigation_works_even_when_storage_is_unavailable(self):
        self.s.draw.store = None
        self.s.draw.unavailable = 'draw_storage_newer'
        self.assertEqual((await self.say('Open Draw')).content, 'Opened OLIVE Draw.')
        answer = await self.say('New drawing')
        self.assertIn('Drawing storage unavailable', answer.content)


if __name__ == '__main__':
    unittest.main()
