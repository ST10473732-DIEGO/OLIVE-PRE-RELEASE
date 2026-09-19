"""Opt-in normal-launch acceptance using only a new synthetic profile and owned windows."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import psutil
import win32con
import win32gui
import win32process


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='olive-launcher-', ignore_cleanup_errors=True) as profile:
        records = []
        for iteration in range(2):
            process = subprocess.Popen(['cmd.exe', '/d', '/c', str(root / 'run_olive.bat')], cwd=root,
                env={**os.environ, 'OLIVE_DATA_DIR': profile, 'OLIVE_OLLAMA_HOST': 'http://127.0.0.1:1'},
                creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            owner = psutil.Process(process.pid)
            owned = []
            try:
                deadline = time.monotonic() + 30
                windows = []
                while time.monotonic() < deadline:
                    owned = owner.children(recursive=True)
                    electron_ids = {p.pid for p in owned if p.name().lower() == 'electron.exe'}
                    windows = []
                    win32gui.EnumWindows(lambda hwnd, _: windows.append(hwnd)
                        if win32gui.IsWindowVisible(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] in electron_ids else None, None)
                    if windows and any(p.name().lower() == 'python.exe' for p in owned) and (Path(profile) / 'personal.sqlite3').exists():
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Normal launcher did not create its owned window and backend')
                time.sleep(1)
                # Sample only this launch, excluding model servers and unrelated
                # applications. 100% here means one fully occupied logical core.
                baseline = {child.pid: sum(child.cpu_times()[:2]) for child in owned}
                sampled = time.monotonic()
                time.sleep(5)
                cpu_seconds = sum(max(0, sum(child.cpu_times()[:2]) - baseline[child.pid]) for child in owned)
                cpu_percent = round(100 * cpu_seconds / (time.monotonic() - sampled), 2)
                rss_mb = round(sum(child.memory_info().rss for child in owned) / (1024 * 1024), 1)
                for hwnd in windows:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                process.wait(timeout=20)
                _, alive = psutil.wait_procs(owned, timeout=10)
                if alive:
                    raise RuntimeError('Owned launcher processes survived normal shutdown: ' + str([p.pid for p in alive]))
                records.append({'iteration': iteration + 1, 'normal_launcher': True,
                                'owned_processes_reaped': len(owned), 'idle_cpu_one_core_percent': cpu_percent,
                                'idle_working_set_mb': rss_mb, 'sample_seconds': 5})
            finally:
                # Cleanup is restricted to the retained identities of this launch.
                for child in reversed(owned):
                    try:
                        if child.is_running(): child.kill()
                    except psutil.Error:
                        pass
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                psutil.wait_procs(owned, timeout=10)
        print(json.dumps(records))


if __name__ == '__main__':
    main()
