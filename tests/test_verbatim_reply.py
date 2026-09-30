"""A literal "Reply with exactly: …" is an answer request, never an action.

Found by the VIDEO Stop acceptance: "Reply with exactly: video-stop-recovery-ready"
was interpreted as a desktop stop request ("Enable Desktop Control…")."""
import unittest

from olive.interaction.ordinary_requests import ordinary_request, verbatim_reply


class VerbatimReplyTests(unittest.TestCase):
    def test_echo_requests_are_plain_answers(self):
        for text in ('Reply with exactly: video-stop-recovery-ready', 'please reply with exactly: stop', '  Reply with exactly:  open Firefox  '):
            steps = ordinary_request(text)['steps']
            self.assertEqual([s['intent'] for s in steps], ['conversation.answer'], text)

    def test_other_requests_are_untouched(self):
        for text in ('Stop the task', 'Reply with a joke', 'Reply with exactly:', 'Explain git commit'):
            self.assertIsNone(verbatim_reply(text), text)


if __name__ == '__main__':
    unittest.main()
