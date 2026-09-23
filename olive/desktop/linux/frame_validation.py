"""Validate consented transient capture without storing or forwarding pixels."""
import base64
import io
from PIL import Image


def validate_frame(frame):
    if not isinstance(frame, dict) or any(type(frame.get(key)) is not int for key in ('width', 'height', 'pts')):
        raise ValueError('Capture metadata is invalid')
    width, height = frame['width'], frame['height']
    if not (1 <= width <= 1280 and 1 <= height <= 4096):
        raise ValueError('Capture dimensions exceed the observation budget')
    encoded = frame.get('png')
    if not isinstance(encoded, str) or len(encoded) > 6 * 1024 * 1024:
        raise ValueError('Capture payload exceeds the observation budget')
    data = base64.b64decode(encoded, validate=True)
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG' or image.size != (width, height):
            raise ValueError('Capture format or geometry changed')
        image.load()
        with image.convert('RGB') as rgb:
            if max(high for low, high in rgb.getextrema()) < 4:
                raise PermissionError('Capture is black; no input is permitted')
