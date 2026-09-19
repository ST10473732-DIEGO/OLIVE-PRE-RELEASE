import unittest
from unittest.mock import Mock
from olive.runtime.ui_owner import supervisor_owner


class PresentationOwnerTests(unittest.TestCase):
    def test_only_living_original_ancestor_can_receive_approval_handoff(self):
        parent = Mock(pid=4321)
        parent.create_time.return_value = 100.0
        parent.is_running.return_value = True
        factory = Mock(return_value=Mock(parents=Mock(return_value=[Mock(pid=999), parent])))
        owner = supervisor_owner(4321, factory)
        self.assertTrue(owner(4321))
        self.assertFalse(owner(1234))
        parent.is_running.return_value = False
        self.assertFalse(owner(4321))
        parent.is_running.return_value = True
        parent.create_time.return_value = 101.0
        self.assertFalse(owner(4321))

    def test_unrelated_or_invalid_supervisor_rejected(self):
        factory = Mock(return_value=Mock(parents=Mock(return_value=[Mock(pid=4321)])))
        for pid in (1234, 0, -1, True, '4321'):
            with self.assertRaises(ValueError):
                supervisor_owner(pid, factory)
