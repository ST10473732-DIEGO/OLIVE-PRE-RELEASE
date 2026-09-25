"""Observation-only accessibility inspector: no portal, EIS, clipboard or input.

Runs in its own distribution-Python process under a hard wall-clock limit so a
hung or crashing accessibility peer cannot stall OLIVE or the input helper. It
prints bounded structural counts and categories, never control names or text.
"""
import json
import sys
import time


def summarize(pid, item=''):
    from olive.desktop.linux.accessibility import Accessibility, ObservationAborted
    access = Accessibility()
    started = time.monotonic()
    try:
        result = access.observe(pid, [-100000, -100000, 200000, 200000], item=item)
    except ObservationAborted as error:
        return {'pid': pid, 'status': error.category, 'seconds': round(time.monotonic() - started, 3)}
    except LookupError:
        return {'pid': pid, 'status': 'NOT_ACCESSIBLE', 'seconds': round(time.monotonic() - started, 3)}
    roles = {}
    for control in result['controls']:
        roles[control['role']] = roles.get(control['role'], 0) + 1
    return {'pid': pid, 'status': 'OBSERVED', 'profile': result['profile'], 'windows': len(result['windows']),
            'controls': len(result['controls']), 'roles': roles, 'pruned_item_views': result['pruned_item_views'],
            'incomplete': result['incomplete'], 'item_matches': sum(c['name'] == item for c in result['controls'])
            if item else 0, 'seconds': round(time.monotonic() - started, 3)}


def inspect(pid, item='', timeout=8, python='/usr/bin/python3'):
    """Run `summarize` in a separate process; the caller never shares its state."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    try:
        completed = subprocess.run([python, '-I', '-c',
            'import sys,json;sys.path.insert(0,sys.argv[1]);'
            'from olive.desktop.linux.inspect_helper import summarize;'
            'print(json.dumps(summarize(int(sys.argv[2]),sys.argv[3])))', str(root), str(int(pid)), item],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'pid': pid, 'status': 'INSPECTION_TIMEOUT'}
    if completed.returncode != 0:
        return {'pid': pid, 'status': 'INSPECTOR_FAILED', 'returncode': completed.returncode}
    return json.loads(completed.stdout.strip().splitlines()[-1])


if __name__ == '__main__':
    print(json.dumps(inspect(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else '')))
