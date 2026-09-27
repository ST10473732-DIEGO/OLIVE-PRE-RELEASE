"""Exclusive selected-address listeners with safe same-port restart semantics."""
import socket
import sys


def listener_socket(address):
    sock = socket.socket(socket.AF_INET6 if ':' in address else socket.AF_INET,
                         socket.SOCK_STREAM)
    try:
        # Windows REUSEADDR allows listener hijacking. Never use it there.
        # POSIX REUSEADDR permits TIME_WAIT reuse, not a second active listener.
        option = socket.SO_EXCLUSIVEADDRUSE if sys.platform == 'win32' else socket.SO_REUSEADDR
        sock.setsockopt(socket.SOL_SOCKET, option, 1)
        return sock
    except BaseException:
        sock.close()
        raise
