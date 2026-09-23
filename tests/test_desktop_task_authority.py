import json
from pathlib import Path
import tempfile
import threading
import unittest

from olive.desktop.task_authority import TaskAuthority, direct_scope, decode_action, validate_effect, scroll_amount
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
        self.assertEqual(direct_scope('Please search for Cape Town weather in Firefox').content, 'Cape Town weather')
        self.assertEqual(direct_scope("Open Discord, go to OLIVE Community, open development, send 'The new build is ready.'").account, '')

    def test_omitted_account_is_narrowed_once_and_old_grant_is_invalid(self):
        grant = self.grant("Send 'Exact text' to Alex in Messenger")
        narrowed = self.authority.bind_account(grant, {'controls': [dict(name='Account: Work', role='label')]}, POLICY)
        self.assertEqual(narrowed.scope.account, 'Work')
        self.assertEqual(narrowed.request_digest, grant.request_digest)
        self.assertEqual(narrowed.expires, grant.expires)
        with self.assertRaises(InterruptedError):
            self.authority.check(grant, POLICY)
        self.assertIs(self.authority.bind_account(narrowed, {'controls': [dict(name='Account: Other', role='label')]}, POLICY), narrowed)

    def test_missing_duplicate_or_message_claimed_account_cannot_bind(self):
        for controls in ([], [dict(name='Account: Work', role='text')],
                         [dict(name='Account: Work', role='label')] * 2):
            grant = self.grant("Send 'Exact text' to Alex in Messenger")
            with self.assertRaisesRegex(ValueError, 'NEEDS_USER_CLARIFICATION'):
                self.authority.bind_account(grant, {'controls': controls}, POLICY)

    def test_content_cannot_be_typed_into_wrong_destination_or_unrelated_field(self):
        grant = self.grant()
        for field in ('destination', 'target'):
            observed = self.observation(grant)
            observed['controls'][1]['value'] = ''
            if field == 'destination':
                observed['destination']['destination'] = 'Other recipient'
            else:
                observed['controls'][1]['name'] = 'Profile biography'
            with self.assertRaises(PermissionError):
                validate_effect(grant, dict(action='type', target='composer', value=grant.scope.content,
                    revision='fresh', expected=''), observed)

    def test_enter_on_unrelated_control_cannot_submit_a_valid_draft(self):
        grant = self.grant()
        observed = self.observation(grant)
        observed['controls'].append(dict(id='other', name='OK', enabled=True))
        with self.assertRaises(PermissionError):
            validate_effect(grant, dict(action='key', target='other', value='Enter', revision='fresh', expected=''), observed)

    def test_scroll_is_strict_and_bounded(self):
        self.assertEqual(scroll_amount('-300'), -300)
        for value in ('NaN', '601', '-601', '1.5', '300; send', '0', 300):
            with self.assertRaises(ValueError):
                scroll_amount(value)

    def test_page_or_model_cannot_issue(self):
        for policy, local in [(POLICY, False), ({**POLICY, 'trusted_tasks': False}, True)]:
            with self.assertRaises(PermissionError):
                self.authority.issue('Open Firefox', 'fake', policy, local_user=local)
        for text in ['How do I send a message?', "Don't open Firefox", 'Send something nice to Alex']:
            with self.assertRaises(ValueError):
                direct_scope(text)

    def test_trailing_constraints_are_not_silently_absorbed_into_fields(self):
        for text in ["Open Firefox and search for cats but don't download anything",
                     "Send 'hello' to Alex in Messenger using account Work, but do not send yet"]:
            with self.assertRaises(ValueError):
                direct_scope(text)

    def test_explicit_send_needs_no_new_confirmation(self):
        grant = self.grant()
        self.authority.check(grant, POLICY)
        target, submit = validate_effect(grant, dict(action='invoke', target='send', value='click',
            revision='fresh', expected='delivery'), self.observation(grant))
        self.assertTrue(submit)
        self.assertEqual(target['id'], 'send')

    def test_focus_is_not_submission_and_advertised_destructive_action_is_rejected(self):
        grant = self.grant()
        _, submit = validate_effect(grant, dict(action='focus', target='send', value='',
            revision='fresh', expected=''), self.observation(grant))
        self.assertFalse(submit)
        with self.assertRaises(PermissionError):
            validate_effect(grant, dict(action='invoke', target='send', value='delete',
                revision='fresh', expected=''), self.observation(grant))

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
