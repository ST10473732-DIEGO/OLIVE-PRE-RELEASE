import unittest
from olive.desktop.window_identity import foreground_matches, merge_hosted_window


class WindowIdentityTests(unittest.TestCase):
    def test_hosted_window_retains_application_identity_and_frame_geometry(self):
        frame = {"hwnd": 1, "pid": 10, "window_class": "ApplicationFrameWindow", "bounds": {"left": 5}, "foreground": True}
        content = {"hwnd": 2, "pid": 20, "package_identity": "Fixture!App", "application": "fixture", "executable": "fixture.exe"}
        window = merge_hosted_window(frame, content)
        self.assertEqual(window["pid"], 20)
        self.assertEqual(window["hwnd"], 1)
        self.assertEqual(window["content_hwnd"], 2)
        self.assertEqual(window["bounds"], frame["bounds"])
        self.assertTrue(foreground_matches(window, 1, 10))
        self.assertFalse(foreground_matches(window, 2, 20))
        self.assertFalse(foreground_matches(window, 3, 10))

    def test_unrelated_frame_cannot_supply_packaged_app_identity(self):
        with self.assertRaises(ValueError):
            merge_hosted_window({"window_class": "OtherWindow"}, {"package_identity": "App"})

    def test_native_window_checks_both_handle_and_process(self):
        window = {"hwnd": 1, "pid": 2}
        self.assertTrue(foreground_matches(window, 1, 2))
        self.assertFalse(foreground_matches(window, 1, 3))
        self.assertFalse(foreground_matches(window, 4, 2))
