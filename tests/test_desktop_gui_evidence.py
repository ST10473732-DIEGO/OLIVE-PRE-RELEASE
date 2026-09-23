import unittest
from olive.desktop.task_authority import TaskScope
from olive.desktop.gui_evidence import messaging_destination, delivery, search_result


class GuiEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.scope = TaskScope('Owned messenger', 'send', 'Exact synthetic text.', 'A new person', 'Test account')
        self.controls = [dict(id='account', name='Account: Test account', role='label'),
                         dict(id='header', name='A new person', role='heading')]

    def test_ambiguous_and_missing_recipient_never_resolve(self):
        self.assertIsNotNone(messaging_destination(self.scope, {'controls': self.controls}))
        self.assertIsNone(messaging_destination(self.scope, {'controls': self.controls * 2}))
        self.assertIsNone(messaging_destination(self.scope, {'controls': self.controls[:1]}))
        self.controls[1]['role'] = 'text'  # A message claiming a name is not a header.
        self.assertIsNone(messaging_destination(self.scope, {'controls': self.controls}))

    def test_server_must_be_selected_and_unique(self):
        scope = TaskScope('Owned messenger', 'send', 'x', 'A new person', 'Test account', 'New server')
        controls = self.controls + [dict(id='server', name='New server', role='list item', selected=False)]
        self.assertIsNone(messaging_destination(scope, {'controls': controls}))
        controls[-1]['selected'] = True
        self.assertEqual(messaging_destination(scope, {'controls': controls})['server'], 'New server')

    def test_composer_and_pending_echo_are_not_delivery(self):
        controls = self.controls + [dict(id='row', name='Outgoing message', role='list item'),
            dict(id='body', parent='row', name=self.scope.content, role='text'),
            dict(id='receipt', parent='row', name='Pending', role='label')]
        self.assertFalse(delivery(self.scope, {'controls': controls}))
        controls[-1]['name'] = 'Delivered'
        self.assertTrue(delivery(self.scope, {'controls': controls}))
        self.assertFalse(delivery(self.scope, {'controls': controls}, previous_count=1))
        controls[-1]['parent'] = 'other-row'
        self.assertFalse(delivery(self.scope, {'controls': controls}))

    def test_wrong_account_or_changed_content_invalidates_receipt(self):
        controls = self.controls + [dict(id='row', name='Outgoing message', role='list item'),
            dict(id='body', parent='row', name='different text', role='text'),
            dict(id='receipt', parent='row', name='Sent', role='label')]
        self.assertFalse(delivery(self.scope, {'controls': controls}))
        controls[3]['name'] = self.scope.content
        controls[0]['name'] = 'Account: Different account'
        self.assertFalse(delivery(self.scope, {'controls': controls}))

    def test_search_needs_native_url_and_visible_results(self):
        scope = TaskScope('Firefox', 'search', 'Cape Town')
        observation = {'documents': [{'uri': 'https://example.test/search?q=Cape+Town', 'name': 'Search results'}],
                       'controls': [{'name': 'Results for Cape Town', 'role': 'heading'}]}
        self.assertTrue(search_result(scope, observation))
        observation['documents'][0]['uri'] = 'https://example.test/search?q=Other'
        self.assertFalse(search_result(scope, observation))
        observation['documents'] = []
        self.assertFalse(search_result(scope, observation))
