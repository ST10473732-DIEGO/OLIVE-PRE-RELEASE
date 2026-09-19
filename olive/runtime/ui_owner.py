"""Trusted supervisor identity for returning focus from Electron approvals.

This is process-lifecycle binding, not a defence against every same-user process.
The renderer cannot select this identity through the local protocol.
"""
import os


def supervisor_owner(pid, process_factory=None):
    import psutil
    process_factory = process_factory or psutil.Process
    if type(pid) is not int or pid <= 0:
        raise ValueError('Invalid presentation supervisor')
    # Windows venv launchers may introduce an intermediate Python process.
    ancestors = process_factory(os.getpid()).parents()[:8]
    process = next((parent for parent in ancestors if parent.pid == pid), None)
    if process is None:
        raise ValueError('Presentation supervisor is not a runtime ancestor')
    created = process.create_time()

    def matches(owner):
        if owner != pid:
            return False
        try:
            return process.is_running() and process.create_time() == created
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    return matches
