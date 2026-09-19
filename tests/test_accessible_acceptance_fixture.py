"""Offscreen widget contract only; not live Electron/UIA acceptance evidence."""
from pathlib import Path
import subprocess
import sys
import unittest


class AccessibleFixtureTests(unittest.TestCase):
    def test_initial_names_and_verification_requires_button(self):
        root = Path(__file__).resolve().parents[1]
        code = '''
from PySide6.QtWidgets import QApplication
from scripts.m2_accessible_acceptance_window import AcceptanceWindow
app = QApplication(['fixture-unit', '-platform', 'offscreen'])
w = AcceptanceWindow()
assert w.editor.text() == ''
assert w.editor.accessibleName() == 'Acceptance text'
assert w.button.accessibleName() == 'Check text'
assert w.result.text() == w.result.accessibleName() == 'Not checked'
w.editor.setText('OLIVE local acceptance')
app.processEvents()
assert w.result.text() == 'Not checked', 'Editing must not verify automatically'
w.button.click()
assert w.result.text() == w.result.accessibleName() == 'Verified: OLIVE local acceptance'
w.editor.setText('different text')
assert w.result.text() == 'Verified: OLIVE local acceptance'
w.button.click()
assert w.result.text() == w.result.accessibleName() == 'Text does not match the acceptance phrase'
w.close()
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=root,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
