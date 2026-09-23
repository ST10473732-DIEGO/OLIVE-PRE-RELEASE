"""Native synthetic pipeline checks; no compositor session, screen or input."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(sys.platform == 'linux', 'Linux GStreamer/GObject pipeline')
class NativeCaptureTests(unittest.TestCase):
    def test_installed_pipeline_encodes_exact_pixels_and_dimensions(self):
        root = Path(__file__).resolve().parents[1]
        python = Path('/usr/bin/python3')
        if not python.is_file():
            self.skipTest('Distribution Python unavailable')
        probe = subprocess.run([str(python), '-I', str(root / 'olive/desktop/linux/native_probe.py')],
                               capture_output=True, timeout=12, check=True)
        dependencies = json.loads(probe.stdout)
        required = ('Gst', 'GstApp', 'GstVideo', 'pillow_png', 'appsink')
        if any(not dependencies.get(key, {}).get('available') for key in required):
            self.skipTest('Native GStreamer/Pillow dependencies unavailable; portable broker tests remain active')
        result = subprocess.run([str(python), '-I', str(root / 'scripts/check_linux_capture_pipeline.py')],
                                capture_output=True, timeout=15, check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report['passed'], 4)
        self.assertFalse(report['capture_or_input_attempted'])
        self.assertTrue(report['failed_constructor_descriptor_closed'])
        self.assertTrue(all(case['exact_center_rgba'] for case in report['cases']))
