"""Unattended inspection. Never binds a shortcut, opens a source or enables policy."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from .applications import Applications
from .client import NativeClient


def dependencies(python='/usr/bin/python3'):
    try:
        completed = subprocess.run([python, '-I', str(Path(__file__).with_name('native_probe.py'))],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=True)
        if len(completed.stdout) > 16000:
            raise ValueError('Excessive dependency response')
        value = json.loads(completed.stdout)
        if not isinstance(value, dict) or not all(isinstance(v, dict) and type(v.get('available')) is bool for v in value.values()):
            raise ValueError('Invalid dependency response')
        return value
    except (OSError, subprocess.SubprocessError, ValueError):
        return {'native_python': {'available': False}}


def classify(deps, interfaces):
    missing = [name for name, value in deps.items() if not value['available']]
    required = {'RemoteDesktop': 2, 'ScreenCast': 4}
    missing += [name for name, minimum in required.items() if interfaces.get(name, {}).get('version', 0) < minimum]
    return {'status': 'BLOCKED_SETUP' if missing else 'DEPENDENCIES_READY',
            'missing': sorted(missing),
            'reason': 'Required native dependency/interface is unavailable' if missing else
                'Dependencies are available; the named KDE grant and actual task session are checked separately',
            'resume': './run_olive.sh → Chat',
            'whole_milestone_rerun_required': False}


async def inspect(client=None, apps=None):
    if sys.platform != 'linux':
        return {'schema_version': 1, 'status': 'UNSUPPORTED_PLATFORM', 'live_input_attempted': False}
    client = client or NativeClient(threading.Event())
    apps = apps or Applications()
    deps = await asyncio.to_thread(dependencies)
    interfaces, probe_error = {}, ''
    try:
        # GetAll only. In particular: no CreateSession, BindShortcuts or Start.
        values = await client.call('probe', timeout=12)
        interfaces = {name: {'version': value.get('version', 0)} for name, value in values.items()}
    except Exception as error:
        probe_error = type(error).__name__  # No session-bus addresses/private details.
    finally:
        await client.close()
    await asyncio.to_thread(apps.discover)
    applications = {}
    for name in ('Firefox', 'Kate', 'Dolphin', 'Discord'):
        try:
            apps.resolve(name)
            applications[name] = 'installed_reviewed_entry'
        except (LookupError, ValueError):
            applications[name] = 'unavailable_or_ambiguous'
    gate = classify(deps, interfaces)
    return {'schema_version': 1, **gate, 'session_type': os.environ.get('XDG_SESSION_TYPE', 'unknown'),
            'dependencies': deps, 'portal_interfaces': interfaces, 'probe_error': probe_error,
            'applications': applications, 'policy_changed': False, 'consent_requested': False,
            'capture_attempted': False, 'live_input_attempted': False, 'owned_helper_closed': client.process is None,
            'global_stop_verified_by_this_check': False}
