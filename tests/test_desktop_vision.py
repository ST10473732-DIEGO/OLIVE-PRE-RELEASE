import unittest
from olive.desktop.vision import validate_observation


class DesktopVisionRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_label_verification_does_not_hint_answer_or_authorize_input(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock, AsyncMock
        from olive.desktop.vision import DesktopVision
        ollama, router = Mock(), Mock()
        router.route.return_value = SimpleNamespace(name="vision", supports_vision=True)
        ollama.chat_measured = AsyncMock(return_value={"content": '{"label":"PREVIEW"}'})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "owned.png"
            path.write_bytes(b"fixture")
            result = await DesktopVision(ollama, router).verify_label({"path": str(path), "id": "capture"}, "Preview")
        self.assertTrue(result["verified"])
        self.assertFalse(result["authorizes_action"])
        self.assertNotIn("Preview", ollama.chat_measured.await_args.args[1][0]["content"])
        self.assertNotIn("bounds", result)

    async def test_empty_budget_exhaustion_retries_once_with_bounded_context(self):
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock, AsyncMock
        from olive.desktop.vision import DesktopVision
        ollama, router = Mock(), Mock()
        router.route.return_value = SimpleNamespace(name="vision", supports_vision=True)
        value = {"target_found": False, "target_label": "", "visible_state": "No target", "confidence": 0, "coordinate_space": "capture_pixels",
                 "bounds": {"left": 0, "top": 0, "right": 0, "bottom": 0}}
        ollama.chat_measured = AsyncMock(side_effect=[{"content": "", "eval_count": 1536},
                                                      {"content": json.dumps(value), "eval_count": 80}])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.png"
            path.write_bytes(b"fixture")
            result = await DesktopVision(ollama, router).observe({"path": str(path), "width": 100, "height": 100, "id": "capture"}, "Find target")
        self.assertFalse(result["target_found"])
        self.assertEqual(ollama.chat_measured.await_count, 2)
        self.assertEqual(ollama.chat_measured.await_args.kwargs["options"]["num_ctx"], 8192)


class DesktopVisionTests(unittest.TestCase):
    def valid(self):
        return {"target_found": True, "target_label": "Save", "visible_state": "A button is visible", "coordinate_space": "capture_pixels",
                "confidence": .9, "bounds": {"left": 1, "top": 2, "right": 40, "bottom": 50}}

    def test_visual_observation_cannot_authorize(self):
        result = validate_observation(self.valid(), 100, 100)
        self.assertFalse(result["authorizes_action"])
        self.assertTrue(result["untrusted_content"])

    def test_outside_bounds_rejected(self):
        value = self.valid()
        value["bounds"]["right"] = 101
        with self.assertRaises(ValueError):
            validate_observation(value, 100, 100)

    def test_unknown_action_field_rejected(self):
        value = self.valid()
        value["execute"] = "send secrets"
        with self.assertRaises(ValueError):
            validate_observation(value, 100, 100)

    def test_nonfinite_confidence_rejected(self):
        value = self.valid()
        value["confidence"] = float("nan")
        with self.assertRaises(ValueError):
            validate_observation(value, 100, 100)

    def test_normalized_resized_capture_to_negative_monitor_client(self):
        from olive.desktop.coordinates import capture_bounds, screen_point
        bounds = capture_bounds({"left": 250, "top": 250, "right": 750, "bottom": 750}, "normalized_0_1000", 800, 600)
        self.assertEqual(bounds, {"left": 200, "top": 150, "right": 600, "bottom": 450})
        capture = {"width": 800, "height": 600, "client_bounds": {"left": -1920, "top": 60, "right": -320, "bottom": 1260}}
        self.assertEqual(screen_point(capture, bounds), (-1120, 660))

    def test_unknown_coordinate_space_is_not_guessed(self):
        value = self.valid()
        value["coordinate_space"] = "screen_pixels"
        with self.assertRaises(ValueError):
            validate_observation(value, 100, 100)
