"""Smoke-test a built OLIVE backend artefact from outside the repository.

Run with the artefact's own interpreter:  <artefact>/bin/python3 -s -P smoke_backend.py <artefact>

Checks, in a throwaway HOME/profile and an unrelated working directory:
  * the interpreter, olive and every dependency resolve inside the artefact;
  * excluded components (Qt, Playwright, dmdo, pip) are not importable;
  * `python -m olive.bridge` starts, announces runtime.ready, reports runtimes as
    Needs setup (none are installed in the throwaway profile) and exits on EOF;
  * nothing is written inside the artefact while it runs.
No model, runtime or network service is contacted: the Ollama host points at a
closed loopback port and app-owned starts are disabled.
"""
import json
import os
import queue
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

IMPORTS = ('ssl', 'sqlite3', 'ctypes', 'zoneinfo', 'cryptography.hazmat.primitives.ciphers.aead', 'OpenSSL',
           'httpx', 'ollama', 'zeroconf', 'psutil', 'pycrdt', 'PIL.Image', 'send2trash', 'bs4', 'ddgs',
           'pdfplumber', 'pypdf', 'docx', 'icalendar', 'dateutil', 'vobject', 'tzdata',
           'olive.bridge.host', 'olive.bridge.__main__', 'olive.application.service_container')
ABSENT = ('PySide6', 'shiboken6', 'playwright', 'dmdo', 'pip', 'olive.ui_qt')


def snapshot(root):
    return {str(p.relative_to(root)) for p in root.rglob('*')}


def environment(base):
    env = {k: v for k, v in os.environ.items() if k in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'COMSPEC'}}
    home = base / 'home'
    for name in ('home', 'data', 'config', 'cache', 'local', 'roaming', 'profile'):
        (base / name).mkdir()
    env.update(HOME=str(home), USERPROFILE=str(home), XDG_DATA_HOME=str(base / 'data'),
               XDG_CONFIG_HOME=str(base / 'config'), XDG_CACHE_HOME=str(base / 'cache'),
               LOCALAPPDATA=str(base / 'local'), APPDATA=str(base / 'roaming'),
               OLIVE_DATA_DIR=str(base / 'profile'), OLIVE_OLLAMA_HOST='http://127.0.0.1:9',
               OLIVE_START_OLLAMA='0', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONIOENCODING='utf-8')
    return env


def check_imports(python, root, env, cwd):
    script = (
        'import importlib,importlib.util,json,sys,os;'
        f'mods={IMPORTS!r};absent={ABSENT!r};'
        'files={m:getattr(importlib.import_module(m),"__file__",None) for m in mods};'
        'missing=[m for m in absent if (importlib.util.find_spec(m.split(".")[0]) is not None and '
        '(m.count(".")==0 or importlib.util.find_spec(m) is not None))];'
        'print(json.dumps({"prefix":sys.prefix,"files":files,"present":missing,"version":sys.version}))')
    result = json.loads(subprocess.run([python, '-s', '-P', '-c', script], cwd=cwd, env=env, check=True,
                                       capture_output=True, text=True).stdout)
    root_text = str(root.resolve())
    outside = {m: f for m, f in result['files'].items() if f and not str(Path(f).resolve()).startswith(root_text)}
    if not str(Path(result['prefix']).resolve()).startswith(root_text):
        raise SystemExit(f'Interpreter prefix escapes the artefact: {result["prefix"]}')
    if outside:
        raise SystemExit(f'Modules resolved outside the artefact: {outside}')
    if result['present']:
        raise SystemExit(f'Excluded components are importable: {result["present"]}')
    return result


def read_frame(lines, deadline):
    try:
        line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
    except queue.Empty:
        raise SystemExit('The backend did not answer in time') from None
    if not line:
        raise SystemExit('The backend exited before answering')
    return json.loads(line)


def check_bridge(python, env, cwd):
    process = subprocess.Popen([python, '-s', '-P', '-u', '-m', 'olive.bridge'], cwd=cwd, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in iter(process.stdout.readline, b'')] + [lines.put(b'')],
                     daemon=True).start()
    try:
        deadline = time.monotonic() + 90
        ready = False
        while not ready:
            frame = read_frame(lines, deadline)
            ready = frame.get('kind') == 'event' and frame.get('topic') == 'runtime.ready'
        request = {'v': 1, 'id': 'smoke-runtimes', 'method': 'runtime.runtimes', 'args': {}}
        process.stdin.write((json.dumps(request) + '\n').encode())
        process.stdin.flush()
        while True:
            frame = read_frame(lines, deadline)
            if frame.get('kind') == 'response' and frame.get('id') == 'smoke-runtimes':
                break
        if not frame.get('ok'):
            raise SystemExit(f'runtime.runtimes failed: {frame.get("error")}')
        states = {name: entry['state'] for name, entry in frame['result']['runtimes'].items()}
        if any(state != 'needs_setup' for state in states.values()):
            raise SystemExit(f'A throwaway profile unexpectedly found runtimes: {states}')
        process.stdin.close()
        code = process.wait(timeout=60)
        if code != 0:
            raise SystemExit(f'The backend exited with {code}: {process.stderr.read()[-2000:]!r}')
        return {'states': states, 'packaged': frame['result']['packaged']}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def main():
    root = Path(sys.argv[1]).resolve()
    python = sys.executable
    before = snapshot(root)
    with tempfile.TemporaryDirectory(prefix='olive-backend-smoke-') as directory:
        base = Path(directory)
        env = environment(base)
        work = base / 'elsewhere'
        work.mkdir()
        imports = check_imports(python, root, env, work)
        bridge = check_bridge(python, env, work)
        written = [p for p in (base / 'profile').rglob('*')]
    after = snapshot(root)
    if after != before:
        raise SystemExit(f'The backend wrote inside the artefact: {sorted(after - before)[:20]}')
    if not bridge['packaged']:
        raise SystemExit('The backend did not recognise its packaged layout')
    print(json.dumps({'python': imports['version'].split()[0], 'runtimes': bridge['states'],
                      'profile_entries': len(written), 'artefact_unchanged': True}))


if __name__ == '__main__':
    main()
