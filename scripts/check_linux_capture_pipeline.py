"""Synthetic native frame acceptance; no portal, desktop capture, input or files.

Run with distribution Python (GObject/Pillow). These generated test sources do
not establish PipeWire portal/display acceptance.
"""
import io
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.desktop.linux.capture import Capture, Gst, GstVideo, Image, encode_sample


def check():
    Gst.init(None)
    results = []
    for width, height, color, pixel in ((640, 360, 'red', (255, 0, 0, 255)),
                                      (641, 359, 'green', (0, 255, 0, 255)),
                                      (1280, 720, 'blue', (0, 0, 255, 255))):
        pipeline = Gst.parse_launch(f'videotestsrc num-buffers=1 pattern={color} ! '
            f'video/x-raw,format=RGBA,width={width},height={height} ! appsink name=frame sync=false')
        started = time.monotonic()
        try:
            pipeline.set_state(Gst.State.PLAYING)
            sample = pipeline.get_by_name('frame').try_pull_sample(3 * Gst.SECOND)
            if sample is None:
                raise RuntimeError('Synthetic source did not deliver')
            data, actual_width, actual_height = encode_sample(sample)
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                assert image.size == (width, height) == (actual_width, actual_height)
                assert image.getpixel((width // 2, height // 2)) == pixel
            results.append({'size': [width, height], 'exact_center_rgba': True,
                            'seconds': round(time.monotonic() - started, 4)})
        finally:
            pipeline.set_state(Gst.State.NULL)
    # PipeWire may supply row padding via VideoMeta rather than negotiated caps.
    width, height, stride, offset = 7, 3, 40, 8
    pixels = b'\xff\x00\x00\xff' * width
    raw = b'\x00' * offset + (pixels + b'\x00' * (stride - len(pixels))) * height
    buffer = Gst.Buffer.new_allocate(None, len(raw), None)
    buffer.fill(0, raw)
    GstVideo.buffer_add_video_meta_full(buffer, GstVideo.VideoFrameFlags.NONE, GstVideo.VideoFormat.RGBA,
        width, height, 1, [offset, 0, 0, 0], [stride, 0, 0, 0])
    caps = Gst.Caps.from_string(f'video/x-raw,format=RGBA,width={width},height={height},framerate=1/1')
    sample = Gst.Sample.new(buffer, caps, None, None)
    data, _, _ = encode_sample(sample)
    with Image.open(io.BytesIO(data)) as image:
        assert all(pixel == (255, 0, 0, 255) for pixel in image.get_flattened_data())
    results.append({'size': [width, height], 'exact_center_rgba': True, 'padded_stride_and_offset': True})
    # A pipeline-construction failure must close the descriptor transferred to it.
    fd = os.open(os.devnull, os.O_RDONLY)
    with patch('olive.desktop.linux.capture.Gst.parse_launch', side_effect=RuntimeError('synthetic constructor failure')):
        try:
            Capture(fd, 1)
        except RuntimeError:
            pass
    try:
        os.fstat(fd)
    except OSError:
        descriptor_closed = True
    else:
        os.close(fd)
        raise AssertionError('Capture construction leaked its owned descriptor')
    return {'schema_version': 1, 'synthetic_only': True, 'capture_or_input_attempted': False,
            'failed_constructor_descriptor_closed': descriptor_closed,
            'passed': len(results), 'cases': results}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
