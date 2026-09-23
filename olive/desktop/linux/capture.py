"""One bounded PipeWire frame in memory, from the portal-provided connection."""
import base64
import os
import time

import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst


class Capture:
    def __init__(self, fd, node):
        Gst.init(None)
        self.fd = fd
        self.pipeline = Gst.parse_launch(
            f'pipewiresrc fd={fd} path={int(node)} do-timestamp=true ! '
            'videorate drop-only=true ! video/x-raw,framerate=2/1 ! videoconvert ! videoscale ! video/x-raw,width=1280,pixel-aspect-ratio=1/1 ! '
            'pngenc snapshot=false ! appsink name=frame max-buffers=1 drop=true sync=false')
        self.sink = self.pipeline.get_by_name('frame')
        self.last_pts = None
        self.pipeline.set_state(Gst.State.PLAYING)

    def frame(self):
        # Drain old retained frame, then require a new producer timestamp.
        for _ in range(4):
            if self.sink.try_pull_sample(0) is None:
                break
        sample = self.sink.try_pull_sample(2 * Gst.SECOND)
        if sample is None:
            raise TimeoutError('Approved capture is paused or unavailable')
        buffer = sample.get_buffer()
        if buffer.pts == self.last_pts or buffer.pts == Gst.CLOCK_TIME_NONE:
            raise ValueError('Capture timestamp is stale or missing')
        self.last_pts = buffer.pts
        data = buffer.extract_dup(0, buffer.get_size())
        if len(data) > 4 * 1024 * 1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Capture format or size is invalid')
        # PNG IHDR dimensions, no filesystem retention.
        width, height = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
        return {'png': base64.b64encode(data).decode('ascii'), 'width': width,
                'height': height, 'pts': buffer.pts, 'captured_at': time.monotonic()}

    def close(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
