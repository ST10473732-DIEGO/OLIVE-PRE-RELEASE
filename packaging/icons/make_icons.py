"""Install the OLIVE 2 application icons from the supplied artwork (no new artwork).

    python packaging/icons/make_icons.py          # write the canonical icons
    python packaging/icons/make_icons.py --check  # verify them, write nothing

Source: assets/branding/olive2/app-icons/ (source/ is the untouched master set).

- Windows: windows/olive.ico      -> assets/branding/olive.ico   (byte copy)
- macOS:   macos/olive.icns       -> assets/branding/olive.icns  (byte copy)
- Linux:   linux/olive-1024.png   -> assets/branding/olive-<N>.png, every size resampled
           directly from that master (Lanczos on premultiplied alpha), never upscaled
           and never chained through a smaller PNG
- iOS:     ios/AppIcon-{Light,Dark}-1024.png -> AppIcon.appiconset/AppIcon-{Light,Dark}.png
           (byte copy after checking they are opaque 1024x1024; iOS applies its own mask)

The desktop app icon is the dark design. Requires Pillow.
"""
import argparse
from pathlib import Path
import sys

from PIL import Image

REPOSITORY = Path(__file__).resolve().parents[2]
BRANDING = REPOSITORY / 'assets' / 'branding'
ARTWORK = BRANDING / 'olive2' / 'app-icons'
APPICONSET = REPOSITORY / 'mobile' / 'ios' / 'OLIVEMobile' / 'Assets.xcassets' / 'AppIcon.appiconset'
LINUX_MASTER = ARTWORK / 'linux' / 'olive-1024.png'
LINUX_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
COPIES = (
    (ARTWORK / 'windows' / 'olive.ico', BRANDING / 'olive.ico'),
    (ARTWORK / 'macos' / 'olive.icns', BRANDING / 'olive.icns'),
    (ARTWORK / 'ios' / 'AppIcon-Light-1024.png', APPICONSET / 'AppIcon-Light.png'),
    (ARTWORK / 'ios' / 'AppIcon-Dark-1024.png', APPICONSET / 'AppIcon-Dark.png'),
)


def linux_icon(master, size):
    if size == master.width:
        return master.copy()
    # Resampling premultiplied alpha keeps transparent edge pixels from bleeding dark fringes.
    return master.convert('RGBa').resize((size, size), Image.Resampling.LANCZOS).convert('RGBA')


def require_opaque_ios_icon(path):
    with Image.open(path) as image:
        if image.size != (1024, 1024):
            raise SystemExit(f'{path.name} must be 1024x1024, found {image.size}')
        if image.mode != 'RGB':
            raise SystemExit(f'{path.name} must be opaque RGB without an alpha channel, found {image.mode}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='verify the installed icons; write nothing')
    check = parser.parse_args().check
    stale = []
    for source, target in COPIES:
        if target.parent == APPICONSET:
            require_opaque_ios_icon(source)
        data = source.read_bytes()
        if check:
            if not target.is_file() or target.read_bytes() != data:
                stale.append(target)
        else:
            target.write_bytes(data)
    with Image.open(LINUX_MASTER) as opened:
        master = opened.convert('RGBA')
    if master.width != master.height or master.width < max(LINUX_SIZES):
        raise SystemExit(f'{LINUX_MASTER.name} must be square and at least {max(LINUX_SIZES)}px, found {master.size}')
    for size in LINUX_SIZES:
        target = BRANDING / f'olive-{size}.png'
        icon = linux_icon(master, size)
        if check and not target.is_file():
            stale.append(target)
        elif check:
            # Pixels, not bytes: PNG compression differs between zlib builds.
            with Image.open(target) as installed:
                if installed.size != icon.size or installed.convert('RGBA').tobytes() != icon.tobytes():
                    stale.append(target)
        else:
            icon.save(target, format='PNG')
    for target in stale:
        print(f'stale: {target.relative_to(REPOSITORY)}')
    if stale:
        sys.exit(1)
    print('OLIVE 2 application icons are ' + ('current' if check else 'installed'))


if __name__ == '__main__':
    main()
