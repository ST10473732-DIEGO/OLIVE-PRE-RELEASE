"""Provision the pinned Studio developer tooling into the ignored .toolchains/studio directory.

Downloads are verified against recorded SHA-256 digests before extraction; a
mismatch aborts. Python packages come from requirements-studio.txt into the
repository virtual environment. Nothing is installed system-wide.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile
import tarfile
import platform

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".toolchains" / "studio"
ARCHIVES = {
    "omnisharp": {
        "url": "https://github.com/OmniSharp/omnisharp-roslyn/releases/download/v1.39.15/omnisharp-win-x64-net6.0.zip",
        "sha256": "b03eb6b9ac6446fce803b87c0965e94cef5570cc86f47bfefe2f60933d8658e8",
        "target": "omnisharp", "licence": "MIT (OmniSharp/omnisharp-roslyn, .NET Foundation and Contributors)",
    },
    "netcoredbg": {
        "url": "https://github.com/Samsung/netcoredbg/releases/download/3.2.0-1092/netcoredbg-win64.zip",
        "sha256": "3c410a45fa502415203a94fcb88654af65bf8e3dac158a5527a722e7a6b9274a",
        "target": "netcoredbg", "licence": "MIT (Samsung/netcoredbg)",
    },
}


if sys.platform == "linux":
    if platform.machine() not in {"x86_64", "AMD64"}:
        raise SystemExit("Pinned Linux tooling currently targets x86-64")
    ARCHIVES["omnisharp"].update(
        url="https://github.com/OmniSharp/omnisharp-roslyn/releases/download/v1.39.15/omnisharp-linux-x64-net6.0.tar.gz",
        sha256="e34b2ad29c31202b05dbdc1439600f98ea38acf656f84817c52e3dda81879f6c")
    ARCHIVES["netcoredbg"].update(
        url="https://github.com/Samsung/netcoredbg/releases/download/3.2.0-1092/netcoredbg-linux-amd64.tar.gz",
        sha256="080eb3b2d2152465f599d3b33d1ee6e747794e11cc0a3773ec689f5e5f2c5afa")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def fetch(name: str, item: dict, force: bool) -> None:
    TOOLS.mkdir(parents=True, exist_ok=True)
    archive = TOOLS / Path(item["url"]).name
    target = TOOLS / item["target"]
    if target.exists() and not force:
        print(f"{name}: present at {target}")
        return
    if not archive.exists() or force:
        print(f"{name}: downloading {item['url']}")
        with urllib.request.urlopen(item["url"], timeout=600) as response, archive.open("wb") as handle:
            while block := response.read(1 << 20):
                handle.write(block)
    actual = digest(archive)
    if actual != item["sha256"]:
        archive.unlink(missing_ok=True)
        raise SystemExit(f"{name}: SHA-256 mismatch ({actual}); the archive was discarded")
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive) as bundle:
            bundle.extractall(target, filter="data")
        print(f"{name}: verified and extracted to {target} ({item['licence']})")
        return
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.namelist():
            if member.startswith("/") or ".." in Path(member).parts:
                raise SystemExit(f"{name}: unsafe archive member {member}")
        bundle.extractall(target)
    print(f"{name}: verified and extracted to {target} ({item['licence']})")


def install_python_packages() -> None:
    requirements = ROOT / "requirements-studio.txt"
    python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        python = Path(sys.executable)
    print(f"python packages: pip install -r {requirements.name} into {python}")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "-r", str(requirements)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-download and re-extract archives")
    parser.add_argument("--skip-python", action="store_true")
    args = parser.parse_args()
    for name, item in ARCHIVES.items():
        fetch(name, item, args.force)
    if not args.skip_python:
        install_python_packages()
    print("Studio tooling is provisioned. Inventory: python -c \"from olive.studio_tooling.toolchain import inventory; print(inventory())\"")


if __name__ == "__main__":
    main()
