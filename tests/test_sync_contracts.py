import unittest
from dataclasses import replace
from olive.sync.contracts import RecordEnvelope,DeviceGrant,stable_id,reconcile

class SyncContractTests(unittest.TestCase):
    def setUp(self):
        self.device='550e8400-e29b-41d4-a716-446655440000'
        self.record=RecordEnvelope('notes',stable_id(self.device,'notes','legacy-note-1'),1,0,self.device,False,{'text':'offline draft'})
    def test_stable_mapping_and_offline_conflicts_never_silently_overwrite(self):
        self.assertEqual(self.record.record_id,stable_id(self.device,'notes','legacy-note-1'))
        self.assertEqual(reconcile(None,self.record),'apply');self.assertEqual(reconcile(self.record,self.record),'duplicate')
        self.assertEqual(reconcile(self.record,replace(self.record,revision=2,base_revision=1,data={'text':'next'})),'apply')
        self.assertEqual(reconcile(self.record,replace(self.record,data={'text':'competing offline edit'})),'conflict')
        self.assertEqual(reconcile(self.record,replace(self.record,deleted=True,data={})),'conflict')
    def test_revoked_or_unselected_devices_have_no_authority(self):
        grant=DeviceGrant(self.device,'a'*64,frozenset({'notes'}),frozenset({'chat.remote_inference'}))
        self.assertTrue(grant.allows('notes'));self.assertFalse(grant.allows('tasks'));self.assertFalse(replace(grant,revoked=True).allows('notes'))
        self.assertFalse(grant.allows('notes','desktop.control_local'))
    def test_credentials_actions_and_oversize_payloads_are_rejected(self):
        for payload in [{'vault':{}},{'nested':{'refresh_token':'secret'}},{'execution_queue':[]},{'text':'x'*256001}]:
            with self.assertRaises(ValueError):replace(self.record,data=payload).validate()
        with self.assertRaises(ValueError):replace(self.record,collection='outbox').validate()
