import base64
import io
import unittest
from PIL import Image
from olive.desktop.linux.frame_validation import validate_frame


class CaptureValidationTests(unittest.TestCase):
    def frame(self, color):
        output = io.BytesIO()
        Image.new('RGB', (16, 16), color).save(output, format='PNG')
        return dict(width=16, height=16, pts=100, png=base64.b64encode(output.getvalue()).decode())

    def test_readable_frame_without_persistence(self):
        validate_frame(self.frame('white'))

    def test_black_or_changed_capture_blocks_input(self):
        with self.assertRaises(PermissionError):
            validate_frame(self.frame('black'))
        value = self.frame('white')
        value['width'] = 1281
        with self.assertRaises(ValueError):
            validate_frame(value)
        value['width'] = 17
        with self.assertRaises(ValueError):
            validate_frame(value)
