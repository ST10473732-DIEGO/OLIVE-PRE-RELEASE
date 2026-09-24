import unittest
from olive.desktop.linux.editor_ownership import EditorOwnership


class EditorOwnershipTests(unittest.TestCase):
    controls = [{'name': 'Save', 'enabled': True}, {'name': 'Cancel', 'enabled': True},
                {'name': 'File name', 'value': '', 'editable': True}]

    def history(self, isolated=False):
        history = EditorOwnership(42, 100., 'document', isolated)
        history.expect_save([{'id': 'document', 'active': True}, {'id': 'unrelated', 'active': False}])
        return history

    def test_empty_task_owned_dialog_with_parent_is_admitted(self):
        h = self.history()
        h.admit({'id': 'new', 'pid': 42, 'transient_for': 'document', 'dialog': False}, 100., self.controls)
        self.assertEqual(h.dialog_id, 'new')

    def test_preexisting_dialog_same_pid_and_title_is_preserved(self):
        for isolated in (False, True):
            with self.assertRaises(PermissionError):
                self.history(isolated).admit({'id': 'unrelated', 'pid': 42, 'title': 'Save As',
                                             'transient_for': 'document'}, 100., self.controls)

    def test_missing_parent_requires_independently_isolated_session(self):
        window = {'id': 'new', 'pid': 42}
        with self.assertRaises(PermissionError):
            self.history().admit(window, 100., self.controls)
        self.history(True).admit(window, 100., self.controls)

    def test_process_reuse_and_changed_dialog_are_rejected(self):
        h = self.history(True)
        with self.assertRaises(PermissionError):
            h.admit({'id': 'new', 'pid': 42}, 101., self.controls)
        h.admit({'id': 'new', 'pid': 42}, 100., self.controls)
        with self.assertRaises(PermissionError):
            h.admit({'id': 'other', 'pid': 42}, 100., self.controls)
