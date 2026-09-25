"""Damage-driven capture: evidence postdates the last input; an unchanged screen is current (no live session)."""
import importlib.util
from pathlib import Path
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

NONE = -1


class Sample:
    def __init__(self, pts):
        self.pts = pts

    def get_buffer(self):
        return self


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
                          MessageType=SimpleNamespace(ERROR=1, EOS=2), FlowReturn=SimpleNamespace(OK=0),
                          init=lambda args: None)
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
        self.capture.pipeline = Pipeline()
        self.capture.last_pts, self.capture.held, self.capture.failed = None, None, False
        self.capture.latest, self.capture.latest_at = None, 0.0
        self.capture.arrived = threading.Condition()

    def arrive(self, pts):
        sink = SimpleNamespace(emit=lambda name: Sample(pts))
        self.capture._arrive(sink)
        return time.monotonic()

    def test_a_frame_newer_than_the_input_is_returned_without_waiting(self):
        self.arrive(10)
        started = time.monotonic()
        frame = self.capture.frame(since=started - 1, wait=1)
        self.assertEqual((frame['pts'], frame['static']), (10, False))
        self.assertLess(time.monotonic() - started, .2)

    def test_after_input_only_a_later_frame_counts_and_arrives_mid_wait(self):
        self.arrive(10)
        input_at = time.monotonic()
        threading.Timer(.05, lambda: self.arrive(11)).start()
        frame = self.capture.frame(since=input_at, wait=1)
        self.assertEqual((frame['pts'], frame['static']), (11, False))

    def test_unchanged_screen_is_current_but_a_failed_stream_is_not(self):
        self.arrive(10)
        input_at = time.monotonic()
        frame = self.capture.frame(since=input_at, wait=.05)
        self.assertEqual((frame['pts'], frame['static']), (10, True))
        self.capture.pipeline.messages = ['error']
        with self.assertRaisesRegex(TimeoutError, 'paused or unavailable'):
            self.capture.frame(since=time.monotonic(), wait=.05)

    def test_nothing_captured_yet_is_unavailable(self):
        with self.assertRaisesRegex(TimeoutError, 'paused or unavailable'):
            self.capture.frame(wait=.05)

    def test_missing_timestamps_fail(self):
        self.arrive(NONE)
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.capture.frame(wait=.05)


if __name__ == '__main__':
    unittest.main()
