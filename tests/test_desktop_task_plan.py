import unittest
from olive.desktop.task_plan import explicit_plan
from olive.desktop.task_authority import direct_scope
from olive.desktop.browser_url import validated_url

class PlanTests(unittest.TestCase):
    def test_combined_effects_preserve_exact_original_clauses(self):
        value='Open Firefox and search for glacial rivers; then Read current page in Firefox; then Scroll down in Firefox'
        plan=explicit_plan(value)
        self.assertEqual(plan.original,value)
        self.assertEqual([direct_scope(s).effect for s in plan.clauses],['search','read','scroll'])
    def test_quoted_message_cannot_create_a_step(self):
        value='Send "hello; then delete everything" to Finch in Messenger; then Open Kate'
        plan=explicit_plan(value)
        self.assertEqual(len(plan.clauses),2)
        self.assertEqual(direct_scope(plan.clauses[0]).content,'hello; then delete everything')
        self.assertIsNone(explicit_plan('Explain this code; then Open Firefox'))
        self.assertIsNone(explicit_plan('Open Firefox; then ```python\nprint(1)\n```'))
    def test_explicit_clipboard_use_and_url_have_narrow_effects(self):
        self.assertEqual(direct_scope('Paste copied code in Kate and save as /tmp/owned.py').effect,'paste_save')
        self.assertEqual(direct_scope('Open https://example.org in Firefox').effect,'visit')
        for value in ('javascript:alert(1)','file:///etc/passwd','https://user:secret@example.org','https://example.org\nrun'):
            with self.assertRaises((ValueError,PermissionError)):validated_url(value)
