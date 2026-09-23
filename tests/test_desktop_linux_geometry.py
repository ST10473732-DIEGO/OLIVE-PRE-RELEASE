import unittest
from olive.desktop.linux.geometry import approved_region, contains, pixel_point


class GeometryTests(unittest.TestCase):
    def test_fractional_display_and_negative_origin(self):
        region = approved_region({'position': (-2048, -100), 'size': (2048, 1280)})
        self.assertEqual(pixel_point(region, (1280, 800), (640, 400)), (-1024, 540))
        self.assertTrue(contains(region, [-2000, 0, 300, 100]))
        self.assertFalse(contains(region, [-20, 0, 300, 100]))

    def test_rotated_frame_uses_each_axis_independently(self):
        self.assertEqual(pixel_point((0, 0, 1080, 1920), (720, 1280), (360, 640)), (540, 960))

    def test_unknown_display_and_nonfinite_coordinates_fail_closed(self):
        with self.assertRaises(PermissionError):
            approved_region({})
        for bounds in (None, [0, 0, 0, 1], [0, 0, float('nan'), 1]):
            self.assertFalse(contains((0, 0, 1920, 1080), bounds))
        for point in ((-1, 0), (1280, 0), (float('inf'), 0)):
            with self.assertRaises(ValueError):
                pixel_point((0, 0, 1920, 1080), (1280, 720), point)
