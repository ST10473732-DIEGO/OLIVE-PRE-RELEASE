"""Generate desktop packaging icons from the OLIVE brand source (no new artwork).

    python packaging/icons/make_icons.py

Writes assets/branding/olive.icns (macOS app and DMG icon) from
assets/branding/olive-source.png (1024x1024 RGBA). Requires Pillow, which writes
ICNS on every platform. The Windows .ico and the Linux PNG sizes already exist in
assets/branding and are used as they are.
"""
from pathlib import Path

from PIL import Image

REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE = REPOSITORY / 'assets' / 'branding' / 'olive-source.png'
ICNS = REPOSITORY / 'assets' / 'branding' / 'olive.icns'
SIZES = (16, 32, 64, 128, 256, 512, 1024)


def main():
    with Image.open(SOURCE) as source:
        image = source.convert('RGBA')
        if image.size != (1024, 1024):
            raise SystemExit(f'{SOURCE.name} must be 1024x1024, found {image.size}')
        image.save(ICNS, format='ICNS', sizes=[(size, size) for size in SIZES])
    print(f'{ICNS.relative_to(REPOSITORY)}: {ICNS.stat().st_size} bytes')


if __name__ == '__main__':
    main()
