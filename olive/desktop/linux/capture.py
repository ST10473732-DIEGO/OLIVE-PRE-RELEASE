"""One bounded PipeWire frame in memory, from the portal-provided connection."""
import base64
import io
import os
import time

import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstApp, GstVideo
from PIL import Image


def encode_sample(sample):
    """Bound dimensions/stride before copying a native RGBA buffer; no PNG plugin."""
    info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
    if not info or info.finfo.name != 'RGBA' or not 1 <= info.width <= 1280 or not 1 <= info.height <= 4096:
        raise ValueError('Capture dimensions or pixel format are invalid')
    stride, offset = info.stride[0], info.offset[0]
    buffer = sample.get_buffer()
    metadata = GstVideo.buffer_get_video_meta(buffer)
    if metadata:
        if metadata.format != info.finfo.format or metadata.width != info.width or metadata.height != info.height:
            raise ValueError('Capture metadata disagrees with negotiated dimensions')
        stride, offset = metadata.stride[0], metadata.offset[0]
    required = stride * (info.height - 1) + info.width * 4
    if stride < info.width * 4 or stride > 8192 or offset < 0 or buffer.get_size() > 32 * 1024 * 1024 or offset + required > buffer.get_size():
        raise ValueError('Capture stride or buffer size is invalid')
    raw = buffer.extract_dup(offset, required)
    with Image.frombytes('RGBA', (info.width, info.height), raw, 'raw', 'RGBA', stride, 1) as pixels:
        output = io.BytesIO()
        pixels.save(output, format='PNG')
    data = output.getvalue()
    if len(data) > 4 * 1024 * 1024:
        raise ValueError('Encoded capture exceeds the frame budget')
    return data, info.width, info.height


class Capture:
    def __init__(self, fd, node, size=(1920, 1080)):
        Gst.init(None)
        self.fd = fd
        self.pipeline = None
        try:
            width, height = size
            if not 1 <= width <= 16384 or not 1 <= height <= 16384:
                raise ValueError('Invalid source dimensions')
            scaled_height = round(1280 * height / width)
            if not 1 <= scaled_height <= 4096:
                raise ValueError('Capture aspect ratio exceeds the frame budget')
            self.pipeline = Gst.parse_launch(
                f'pipewiresrc name=source fd={fd} path={int(node)} do-timestamp=true ! '
                'videorate drop-only=true ! video/x-raw,framerate=2/1 ! videoconvert ! videoscale ! '
                f'video/x-raw,format=RGBA,width=1280,height={scaled_height},pixel-aspect-ratio=1/1 ! '
                'appsink name=frame max-buffers=1 drop=true sync=false')
            self.sink = self.pipeline.get_by_name('frame')
            if not isinstance(self.sink, GstApp.AppSink):
                raise RuntimeError('Capture sink has no typed sample interface')
            self.last_pts = None
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError('Capture pipeline could not start')
        except BaseException:
            self.close()
            raise

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
        data, width, height = encode_sample(sample)
        source = self.pipeline.get_by_name('source').get_static_pad('src').get_current_caps().get_structure(0)
        return {'png': base64.b64encode(data).decode('ascii'), 'width': width,
                'height': height, 'original_width': source.get_value('width'),
                'original_height': source.get_value('height'), 'crop_origin': [0, 0],
                'pts': buffer.pts, 'captured_at': time.monotonic()}

    def close(self):
        try:
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None
        finally:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
