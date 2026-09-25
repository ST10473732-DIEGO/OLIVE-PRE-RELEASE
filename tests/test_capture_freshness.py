"""Damage-driven capture: an unchanged screen is current, a failed stream is not (no live session)."""
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

NONE = -1


class Sample:
    def __init__(self, pts):
        self.pts = pts

    def get_buffer(self):
        return self


class Sink:
    def __init__(self):
        self.retained, self.arriving = [], []

    def try_pull_sample(self, timeout):
        if timeout == 0:
            return self.retained.pop(0) if self.retained else None
        return self.arriving.pop(0) if self.arriving else None


class Pipeline:
    def __init__(self):
        self.messages, self.state = [], 'PLAYING'

    def get_bus(self):
        return SimpleNamespace(pop_filtered=lambda kinds: self.messages.pop(0) if self.messages else None)

    def get_state(self, timeout):
        return None, self.state, None

    def get_by_name(self, name):
        caps = SimpleNamespace(get_structure=lambda i: SimpleNamespace(get_value=lambda key: 1920 if key == 'width' else 1080))
        return SimpleNamespace(get_static_pad=lambda pad: SimpleNamespace(get_current_caps=lambda: caps))


def load():
    gi, repository = ModuleType('gi'), ModuleType('gi.repository')
    gi.require_version = lambda *args: None
    gst = SimpleNamespace(CLOCK_TIME_NONE=NONE, SECOND=10 ** 9, State=SimpleNamespace(PLAYING='PLAYING', NULL='NULL'),
                          MessageType=SimpleNamespace(ERROR=1, EOS=2), init=lambda args: None)
    repository.Gst, repository.GstApp, repository.GstVideo = gst, SimpleNamespace(AppSink=object), SimpleNamespace()
    gi.repository = repository
    path = Path(__file__).resolve().parents[1] / 'olive/desktop/linux/capture.py'
    spec = importlib.util.spec_from_file_location('olive.desktop.linux._capture_under_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict('sys.modules', {'gi': gi, 'gi.repository': repository}):
        spec.loader.exec_module(module)
    module.encode_sample = lambda sample: (b'png', 1280, 720)
    return module


class CaptureFreshnessTests(unittest.TestCase):
    def setUp(self):
        module = load()
        self.capture = module.Capture.__new__(module.Capture)
        self.capture.sink, self.capture.pipeline = Sink(), Pipeline()
        self.capture.last_pts, self.capture.held, self.capture.failed = None, None, False

    def test_new_frame_is_preferred_and_marked_changing(self):
        self.capture.sink.arriving = [Sample(10)]
        frame = self.capture.frame()
        self.assertEqual((frame['pts'], frame['static']), (10, False))

    def test_unchanged_screen_returns_the_newest_frame_as_static(self):
        self.capture.sink.arriving = [Sample(10)]
        self.capture.frame()
        self.capture.sink.retained = [Sample(11)]   # Rendered after the last read, then the screen settled.
        frame = self.capture.frame()
        self.assertEqual((frame['pts'], frame['static']), (11, True))
        self.assertTrue(self.capture.frame()['static'])  # Still unchanged: still current.

    def test_no_frame_or_failed_stream_is_never_treated_as_current(self):
        with self.assertRaisesRegex(TimeoutError, 'paused or unavailable'):
            self.capture.frame()
        self.capture.sink.arriving = [Sample(10)]
        self.capture.frame()
        self.capture.pipeline.messages = ['error']
        with self.assertRaisesRegex(TimeoutError, 'paused or unavailable'):
            self.capture.frame()
        self.capture.pipeline.messages = []
        with self.assertRaises(TimeoutError):
            self.capture.frame()  # A stream that failed once stays failed.
        self.capture.failed = False
        self.capture.pipeline.state = 'PAUSED'
        with self.assertRaises(TimeoutError):
            self.capture.frame()

    def test_a_repeated_producer_timestamp_is_still_rejected_when_new(self):
        self.capture.sink.arriving = [Sample(10)]
        self.capture.frame()
        self.capture.sink.arriving = [Sample(10)]
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.capture.frame()
        self.capture.sink.arriving = [Sample(NONE)]
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.capture.frame()


if __name__ == '__main__':
    unittest.main()
