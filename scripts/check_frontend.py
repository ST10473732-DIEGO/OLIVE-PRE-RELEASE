"""Run pinned frontend checks without relying on ignored recovery helpers."""
import argparse
import json
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
output = Path(parser.parse_args().output).resolve()
output.mkdir(parents=True, exist_ok=True)
node_dir = root / '.toolchains/node-v24.21.0-win-x64'
env = dict(os.environ, PATH=str(node_dir) + os.pathsep + os.environ['PATH'])
results = {}
for command in ('typecheck', 'lint', 'test', 'build'):
    with (output / f'frontend-{command}.log').open('wb') as log:
        result = subprocess.run([str(node_dir / 'node.exe'), str(node_dir / 'node_modules/npm/bin/npm-cli.js'), 'run', command], cwd=root / 'desktop', env=env, stdout=log, stderr=subprocess.STDOUT)
    results[command] = result.returncode
    print(command, result.returncode, flush=True)
(output / 'frontend-checks.json').write_text(json.dumps(results, indent=2))
raise SystemExit(any(results.values()))
