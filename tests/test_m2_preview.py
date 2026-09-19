"""Preview authorization is tied to a live owned process, not a printed URL."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from olive.bridge.preview import authorize
class PreviewAuthorizationTests(unittest.TestCase):
 def setUp(self):
  self.run=NS(id='run',workspace_id='workspace',state='running',process_id=41,local_url='http://127.0.0.1:8912/index.html')
  self.services=NS(workspace_repo=Mock(),run_service=NS(sessions={'run':self.run},_processes={'run':NS(pid=41,returncode=None)}))
 def test_rejects_unowned_inactive_or_non_loopback_run(self):
  with patch('olive.services.local_preview.require_approved_workspace'):
   for url in ['https://example.invalid:8912','file:///fixture','http://user:password@127.0.0.1:8912','http://127.0.0.1']:
    self.run.local_url=url
    with self.assertRaises(ValueError):authorize(self.services,'run')
   self.run.local_url='http://127.0.0.1:8912';self.services.run_service._processes.clear()
   with self.assertRaises(ValueError):authorize(self.services,'run')
   self.run.state='completed'
   with self.assertRaises(ValueError):authorize(self.services,'run')
 def test_listener_must_belong_to_owned_run_or_its_descendant(self):
  parent=Mock();parent.children.return_value=[];parent.net_connections.return_value=[]
  with patch('olive.services.local_preview.require_approved_workspace'),patch('olive.services.local_preview.psutil.Process',return_value=parent):
   with self.assertRaisesRegex(ValueError,'not owned'):authorize(self.services,'run')
   child=Mock();parent.children.return_value=[child];child.net_connections.return_value=[NS(status='LISTEN',laddr=NS(ip='127.0.0.1',port=8912))]
   self.assertEqual(authorize(self.services,'run')['url'],self.run.local_url)
