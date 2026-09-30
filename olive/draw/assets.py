"""OLIVE Draw image assets: validation of PNG/JPEG bytes before storage.

An asset is identified by the SHA-256 of its bytes. Assets reach the store from
the renderer (a user-chosen file, already decoded, EXIF-oriented and re-encoded
by Chromium in the sandboxed renderer, so no metadata survives) or from a
paired peer. Either way the bytes are untrusted here: the type comes from the
content (never a file name), dimensions come from the header and are bounded
before any decoder runs, and Pillow then checks the structure with its
decompression-bomb guard on.
"""
import hashlib
import io
import struct
import warnings

from .document import LIMITS

PNG = b'\x89PNG\r\n\x1a\n'
# Every JPEG start-of-frame marker (baseline, extended, progressive, lossless,
# arithmetic); C4/C8/CC are other segment types.
SOF = frozenset({0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})


class AssetError(ValueError):
    """Fixed, content-free asset failure categories."""


def image_info(data):
    """(mime, width, height) from a PNG or JPEG header, or None. Headers only."""
    if type(data) is not bytes:
        return None
    if data[:8] == PNG and len(data) >= 24 and data[12:16] == b'IHDR':
        width, height = struct.unpack('>II', data[16:24])
        return 'image/png', width, height
    if data[:3] == b'\xff\xd8\xff':
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                return None
            marker = data[index + 1]
            if marker == 0xFF:
                index += 1           # Fill byte.
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            length = struct.unpack('>H', data[index + 2:index + 4])[0]
            if marker in SOF:
                height, width = struct.unpack('>HH', data[index + 5:index + 9])
                return 'image/jpeg', width, height
            if length < 2:
                return None
            index += 2 + length
    return None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def validate(data, *, expected_id=None):
    """Return (asset_id, mime, width, height) for acceptable asset bytes."""
    if type(data) is not bytes or not data:
        raise AssetError('invalid_image')
    if len(data) > LIMITS['max_asset_bytes']:
        raise AssetError('image_too_large')
    info = image_info(data)
    if info is None:
        raise AssetError('unsupported_image')
    mime, width, height = info
    side, pixels = LIMITS['max_asset_side'], LIMITS['max_asset_pixels']
    if not (1 <= width <= side and 1 <= height <= side) or width * height > pixels:
        raise AssetError('image_too_large')
    asset_id = sha256(data)
    if expected_id is not None and asset_id != expected_id:
        raise AssetError('checksum_mismatch')
    _check_structure(data, mime, width, height)
    return asset_id, mime, width, height


def _check_structure(data, mime, width, height):
    from PIL import Image
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != ('PNG' if mime == 'image/png' else 'JPEG') or image.size != (width, height):
                    raise AssetError('invalid_image')
                image.verify()
    except AssetError:
        raise
    except Exception:
        raise AssetError('invalid_image') from None
