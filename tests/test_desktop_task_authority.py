import json
from pathlib import Path
import tempfile
import threading
import unittest

from olive.desktop.task_authority import TaskAuthority, direct_scope, decode_action, validate_effect
from olive.desktop.effect_ledger import EffectLedger

POLICY = dict(enabled=True, trusted_tasks=True, keyboard_policy='allow', mouse_policy='allow')


class TaskAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.stop = threading.Event()
        self.now = 0
        self.authority = TaskAuthority(self.stop, lambda: self.now)

    def grant(self, request="Send 'I will be there at six.' to Alex in Messenger using account Work"):
        return self.authority.issue(request, 'actual-message-id', POLICY, local_user=True)

    def observation(self, grant):
        return {'revision': 'fresh', 'destination': {'account': 'Work', 'destination': 'Alex', 'server': ''},
                'controls': [{'id': 'send', 'name': 'Send', 'enabled': True},
                             {'id': 'composer', 'name': 'Message', 'enabled': True,
                              'editable': True, 'value': grant.scope.content}]}

    def test_literal_request_and_search(self):
        self.assertEqual(direct_scope('Open Firefox and search for Cape Town weather').content, 'Cape Town weather')
        self.assertEqual(direct_scope("Send 'Don\'t worry.\nSee you!' to Alex in Messenger using account Work").content, "Don't worry.\nSee you!")
        self.assertEqual(direct_scope('Open Kate').effect, 'open')

    def test_page_or_model_cannot_issue(self):
        for policy, local in [(POLICY, False), ({**POLICY, 'trusted_tasks': False}, True)]:
            with self.assertRaises(PermissionError):
                self.authority.issue('Open Firefox', 'fake', policy, local_user=local)
        for text in ['How do I send a message?', "Don't open Firefox", 'Send something nice to Alex']:
            with self.assertRaises(ValueError):
                direct_scope(text)

    def test_explicit_send_needs_no_new_confirmation(self):
        grant = self.grant()
        self.authority.check(grant, POLICY)
        target, submit = validate_effect(grant, dict(action='invoke', target='send', value='click',
            revision='fresh', expected='delivery'), self.observation(grant))
        self.assertTrue(submit)
        self.assertEqual(target['id'], 'send')

    def test_draft_never_submits(self):
        grant = self.grant("Draft 'hello' to Alex in Messenger using account Work")
        with self.assertRaises(PermissionError):
            validate_effect(grant, dict(action='invoke', target='send', value='click', revision='fresh', expected=''), self.observation(grant))

    def test_changed_destination_account_or_content(self):
        grant = self.grant()
        for field in ('account', 'destination', 'server', 'content'):
            observed = self.observation(grant)
            if field == 'content':
                observed['controls'][1]['value'] = 'different'
            else:
                observed['destination'][field] = 'different'
            with self.assertRaises(PermissionError):
                validate_effect(grant, dict(action='invoke', target='send', value='click', revision='fresh', expected=''), observed)

    def test_strict_json_rejects_forgery_and_fragments(self):
        valid = dict(action='click', target='1', value='', revision='fresh', expected='next')
        for raw in ['```json\n'+json.dumps(valid)+'\n```', json.dumps({**valid, 'approved': True}),
                    json.dumps({**valid, 'action': 'shell'}), json.dumps({**valid, 'value': None}),
                    json.dumps(valid)[:-1]+',"action":"click"}', 'NaN']:
            with self.assertRaises((ValueError, TypeError)):
                decode_action(raw)

    def test_cancel_revision_expiry_and_removed_policy(self):
        grant = self.grant()
        self.authority.cancel()
        with self.assertRaises(InterruptedError):
            self.authority.check(grant, POLICY)
        grant = self.grant()
        self.now = 301
        with self.assertRaises(PermissionError):
            self.authority.check(grant, POLICY)
        self.now = 0
        grant = self.grant()
        with self.assertRaises(PermissionError):
            self.authority.check(grant, {**POLICY, 'keyboard_policy': 'deny'})
        self.stop.set()
        with self.assertRaises(InterruptedError):
            self.authority.check(grant, POLICY)

    def test_stale_and_existing_draft_preserved(self):
        grant = self.grant()
        for revision in ('old', 'fresh'):
            with self.assertRaises((PermissionError, ValueError)):
                validate_effect(grant, dict(action='type', target='composer', value=grant.scope.content,
                    revision=revision, expected=''), self.observation(grant))

    def test_uncertain_send_is_not_repeated_after_reopen(self):
        grant = self.grant()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'effects.sqlite'
            EffectLedger(path).reserve(grant)
            with self.assertRaises(PermissionError):
                EffectLedger(path).reserve(grant)
            self.assertNotIn(grant.scope.content.encode(), path.read_bytes())

    def test_corrupt_required_ledger_does_not_admit(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'effects.sqlite'
            path.write_bytes(b'invalid existing state')
            with self.assertRaises(sqlite3.DatabaseError):
                EffectLedger(path)
