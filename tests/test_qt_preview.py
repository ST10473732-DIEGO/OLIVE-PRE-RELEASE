import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from PySide6.QtCore import QUrl
from olive.ui_qt.studio.preview import local_origin, OriginInterceptor


class PreviewPolicyTests(unittest.TestCase):
    def test_only_explicit_loopback_http_origins_are_allowed(self):
        self.assertEqual(local_origin("http://127.0.0.1:8123/path"), ("http", "127.0.0.1", 8123))
        for url in (
            "https://example.com",
            "file:///tmp/private",
            "http://localhost.example.com",
            "http://user:secret@localhost:8123",
            "javascript:alert(1)",
        ):
            with self.assertRaises(PermissionError):
                local_origin(url)

    def test_subresources_cannot_escape_the_development_origin(self):
        interceptor = OriginInterceptor(local_origin("http://localhost:8123"))

        class Request:
            def __init__(self, url):
                self.url = QUrl(url)
                self.blocked = False

            def requestUrl(self):
                return self.url

            def block(self, value):
                self.blocked = value

        for url, blocked in [
            ("http://localhost:8123/app.js", False),
            ("http://localhost:8124/private", True),
            ("https://example.com/tracker", True),
            ("file:///private", True),
        ]:
            request = Request(url)
            interceptor.interceptRequest(request)
            self.assertEqual(request.blocked, blocked)

    def test_editor_has_no_webchannel_or_evaluation_bridge(self):
        from pathlib import Path

        source = (Path(__file__).parents[1] / "olive/ui_qt/studio/preview.py").read_text(encoding="utf-8-sig")
        self.assertNotIn("setWebChannel(", source)
        self.assertNotIn("runJavaScript(", source)


if __name__ == "__main__":
    unittest.main()
