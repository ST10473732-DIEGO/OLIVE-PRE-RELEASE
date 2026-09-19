import unittest
from tests.connect_process_fixture import acceptance


class ProcessTests(unittest.TestCase):
    def test_real_process_transport_without_multicast_requirement(self):
        acceptance(discovery=False)
