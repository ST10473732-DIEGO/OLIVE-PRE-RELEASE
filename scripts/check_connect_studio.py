"""Opt-in full-container C8 acceptance using installed local Python/.NET only."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_connect_studio_process import StudioProcessTests

if __name__ == '__main__':
    os.environ.setdefault('OLIVE_OLLAMA_HOST', 'http://127.0.0.1:1')
    StudioProcessTests.live = True
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StudioProcessTests))
    raise SystemExit(not result.wasSuccessful())
