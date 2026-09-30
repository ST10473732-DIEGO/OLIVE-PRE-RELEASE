"""Synthetic image fixtures for OLIVE Draw e2e runs (no personal photos)."""
import io
import struct
import sys
from pathlib import Path

from PIL import Image

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
# 400x300 PNG: left half opaque red, right half transparent, a green square on the right.
image = Image.new('RGBA', (400, 300), (0, 0, 0, 0))
for x in range(200):
    for y in range(300):
        image.putpixel((x, y), (229, 57, 53, 255))
for x in range(250, 350):
    for y in range(100, 200):
        image.putpixel((x, y), (67, 160, 71, 255))
image.save(out / 'transparent.png')
# The same PNG bytes under a .jpg name: the content decides, not the extension.
(out / 'really-a-png.jpg').write_bytes((out / 'transparent.png').read_bytes())
# 300x200 JPEG with a blue band on its left edge, EXIF orientation 6 (rotate 90 CW)
# and a GPS block that must not survive import.
photo = Image.new('RGB', (300, 200), (220, 40, 40))
for x in range(60):
    for y in range(200):
        photo.putpixel((x, y), (20, 20, 220))
exif = Image.Exif()
exif[0x0112] = 6
exif[0x8825] = {1: 'N', 2: (51.0, 30.0, 0.0), 3: 'W', 4: (0.0, 7.0, 0.0)}
photo.save(out / 'rotated.jpg', quality=95, exif=exif.tobytes())
# A large JPEG (scaled down to fit on import, never upscaled).
Image.new('RGB', (3000, 2000), (30, 99, 233)).save(out / 'large.jpg', quality=90)
# A PNG header that claims 100000 x 100000 pixels (refused before any decoder runs).
header = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>IIBBBBB', 100000, 100000, 8, 6, 0, 0, 0)
(out / 'absurd.png').write_bytes(header + b'\x00' * 64)
# Not an image at all.
(out / 'not-an-image.png').write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>')
print('ok')
