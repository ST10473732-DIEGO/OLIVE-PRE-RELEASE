import unittest
from olive.desktop.grounded_steps import next_step
from olive.desktop.task_authority import TaskScope


class GroundedStepTests(unittest.TestCase):
    def test_enter_submission_needs_composer_semantics_and_exact_destination(self):
        from types import SimpleNamespace
        from olive.desktop.task_authority import validate_effect
        scope = TaskScope('Owned', 'send', 'hello', 'garden', 'Owner')
        composer = dict(id='c', name='Message', role='entry', enabled=True, editable=True,
                        focused=True, value='hello', bounds=[0,0,100,30], labels=['Enter to send'])
        observation = dict(revision='r', controls=[composer], destination={'account':'Owner','destination':'garden','server':''})
        step = next_step(scope, observation, False)
        self.assertEqual(step['value'], 'Enter')
        validate_effect(SimpleNamespace(scope=scope), step, observation)
        composer['labels'] = []
        self.assertIsNone(next_step(scope, observation, False))
        with self.assertRaisesRegex(PermissionError,'COMPOSER_SEMANTICS_UNVERIFIED'):
            validate_effect(SimpleNamespace(scope=scope), step, observation)
        composer['labels'] = ['Enter to send', 'Enter inserts a newline']
        self.assertIsNone(next_step(scope, observation, False))
    def setUp(self):
        self.scope = TaskScope('Firefox', 'search', 'A changing query')
        self.control = dict(id='new-id', name='Search or address', enabled=True, editable=True,
                            value='', focused=False, bounds=[321, 25, 700, 44])
        self.observation = dict(revision='new-revision', controls=[self.control])

    def test_semantic_focus_type_submit_use_fresh_ids(self):
        for expected, focus, value in (('focus', False, ''), ('type', True, ''), ('key', True, self.scope.content)):
            self.control.update(focused=focus, value=value)
            step = next_step(self.scope, self.observation, False)
            self.assertEqual(step['action'], expected)
            self.assertEqual(step['target'], 'new-id')
            self.assertEqual(step['revision'], 'new-revision')

    def test_unrelated_draft_ambiguous_control_and_uncertain_submission_are_preserved(self):
        self.control['value'] = 'Unrelated existing text'
        self.assertIsNone(next_step(self.scope, self.observation, False))
        self.control['value'] = ''
        self.observation['controls'] *= 2
        self.assertIsNone(next_step(self.scope, self.observation, False))
        self.observation['controls'] = [self.control]
        self.assertIsNone(next_step(self.scope, self.observation, True))

    def test_message_enter_is_not_guessed_when_send_button_semantics_are_absent(self):
        scope = TaskScope('Messenger', 'send', 'x', 'Alex', 'Work')
        self.control.update(name='Message', value='x', focused=True)
        self.observation['destination'] = dict(account='Work', destination='Alex', server='')
        self.assertIsNone(next_step(scope, self.observation, False))
