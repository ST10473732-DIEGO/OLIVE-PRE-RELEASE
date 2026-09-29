"""Read-only GPU memory evidence for a local engine process.

Used when an engine's own allocator statistics cannot prove release (for
example cudaMallocAsync). This only observes; it never signals a process.
"""
import asyncio
import shutil
import socket

RELEASED_MIB = 1024  # CUDA context + library workspaces of an idle process.


def port_bound(port, host='127.0.0.1'):
    """True when something accepts TCP connections on the loopback port."""
    try:
        with socket.create_connection((host, port), timeout=.5):
            return True
    except OSError:
        return False


def listening_pid(port):
    import psutil
    try:
        connections = psutil.net_connections(kind='tcp')
    except (psutil.AccessDenied, OSError):
        return None
    for connection in connections:
        if (connection.status == psutil.CONN_LISTEN and connection.laddr and connection.laddr.port == port
                and connection.laddr.ip in {'127.0.0.1', '::1'}):
            return connection.pid
    return None


def process_tree(pid):
    import psutil
    try:
        return {pid, *(child.pid for child in psutil.Process(pid).children(recursive=True))}
    except psutil.Error:
        return {pid}


async def process_gpu_mib(pid):
    """GPU MiB used by pid and its descendants (0 when absent), or None when unobservable."""
    executable = shutil.which('nvidia-smi')
    if not executable or not pid:
        return None
    pids = process_tree(pid)
    try:
        process = await asyncio.create_subprocess_exec(
            executable, '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        output, _ = await asyncio.wait_for(process.communicate(), 5)
    except (OSError, TimeoutError):
        return None
    if process.returncode != 0:
        return None
    total = 0
    for line in output.decode(errors='replace').splitlines():
        fields = [value.strip() for value in line.split(',')]
        if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit() and int(fields[0]) in pids:
            total += int(fields[1])
    return total
