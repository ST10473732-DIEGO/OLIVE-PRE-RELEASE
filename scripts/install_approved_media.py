"""Download only the approved pinned media artifacts; verify bytes before use."""
import argparse
import hashlib
from pathlib import Path
import time
import urllib.request

ARTIFACTS = {
    'runtime': ('ComfyUI_windows_portable_nvidia.7z', 1910039517,
                '6fb005a8269c6f5972a8fb76d7a4fc251578ccc7906671a801b382591c791dd2',
                'https://github.com/Comfy-Org/ComfyUI/releases/download/v0.35.0/ComfyUI_windows_portable_nvidia.7z'),
    'model': ('sd_xl_base_1.0.safetensors', 6938078334,
              '31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b',
              'https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors'),
}

def download(kind):
    name, size, expected, url = ARTIFACTS[kind]
    root = Path(__file__).resolve().parents[1] / '.media-runtime' / 'downloads'
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    installed = root.parent / 'ComfyUI_windows_portable/ComfyUI/models/checkpoints' / name
    if kind == 'model' and installed.exists():
        if installed.is_symlink() or installed.stat().st_size != size:
            raise ValueError('Installed checkpoint does not match the approved file')
        with installed.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Installed checkpoint hash differs; it was not overwritten')
        print('model: approved checkpoint already installed and verified; no duplicate download', flush=True)
        return
    if target.is_symlink(): raise ValueError('Download target cannot be a link')
    offset = target.stat().st_size if target.exists() else 0
    if offset > size: raise ValueError('Existing artifact exceeds approved size')
    started = last = time.monotonic()
    while offset < size:
        # Bounded ranges also prevent intermediaries from truncating a huge body.
        end = min(offset + 16 * 1024 * 1024, size) - 1
        request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-{end}'})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    if response.status != 206 or response.headers.get('Content-Range') != f'bytes {offset}-{end}/{size}':
                        raise ValueError('Server did not honor the verified download range')
                    data = response.read(end - offset + 2)
                    if len(data) != end - offset + 1: raise ValueError('Incomplete download range')
                break
            except OSError:
                if attempt == 3: raise
                time.sleep(1 + attempt)
        with target.open('ab') as stream: stream.write(data)
        offset += len(data)
        if time.monotonic() - last > 20:
            print(f'{kind}: {offset}/{size} bytes ({100*offset/size:.1f}%)', flush=True)
            last = time.monotonic()
    with target.open('rb') as stream: actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected: raise ValueError('SHA-256 mismatch; artifact must not be used')
    print(f'{kind}: verified {size} bytes SHA-256 {actual}, {time.monotonic()-started:.1f}s', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', choices=ARTIFACTS)
    parser.add_argument('--approved', action='store_true', help='Explicit user approval for these exact large downloads is required')
    args = parser.parse_args()
    if not args.approved: parser.error('Obtain explicit approval for the pinned download manifest first')
    download(args.artifact)
