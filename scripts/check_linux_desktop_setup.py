"""Safe unattended preflight. Exit 0 means inspected, never live-control acceptance."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from olive.desktop.linux.preflight import inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Create a new content-free JSON report; never overwrite')
    args = parser.parse_args()
    report = asyncio.run(inspect())
    value = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(value)
    print(value, end='')
    return 2 if report['status'] in {'BLOCKED_SETUP', 'UNSUPPORTED_PLATFORM'} else 0


if __name__ == '__main__':
    raise SystemExit(main())
