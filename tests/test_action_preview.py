import unittest

from olive.desktop.action_preview import ActionPreview, resolve_recipient


class ActionPreviewTests(unittest.TestCase):
    def test_preview_is_independent_of_mutable_input(self):
        details = {"destination": "alex@example.test", "body": "Meeting moved to 3 PM."}
        preview = ActionPreview.create("browser", "communication.send", details)
        original = preview.fingerprint
        details["body"] = "Changed"
        self.assertEqual(preview.fingerprint, original)
        self.assertEqual(preview.details["body"], "Meeting moved to 3 PM.")

    def test_changed_destination_changes_approval_identity(self):
        first = ActionPreview.create("browser", "communication.send", {"destination": "a", "body": "hello"})
        second = ActionPreview.create("browser", "communication.send", {"destination": "b", "body": "hello"})
        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_paid_installation_cannot_use_free_install_preview(self):
        for cost in ("unknown", "$5", "trial"):
            with self.assertRaises(ValueError):
                ActionPreview.create("store", "software.install", {
                    "application": "Example", "source": "Store", "publisher": "Example", "cost": cost})

    def test_incomplete_upload_rejected(self):
        with self.assertRaises(ValueError):
            ActionPreview.create("browser", "application.upload", {"destination": "example.test"})

    def test_ambiguous_recipient_requires_review(self):
        with self.assertRaises(ValueError):
            resolve_recipient([{"address": "one@example.test"}, {"address": "two@example.test"}])
