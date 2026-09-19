"""Atomic local export to a destination selected by the native file dialog."""
import os
from pathlib import Path
import tempfile
from .store import WRITE_GUARD


def save_export(destination, content):
    destination=Path(destination)
    guard=WRITE_GUARD.get()
    if guard:guard()
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',
                                        dir=destination.parent,prefix='.olive-export-',delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        if guard:guard()
        os.replace(temporary,destination)
    finally:
        if temporary and temporary.exists():temporary.unlink()
