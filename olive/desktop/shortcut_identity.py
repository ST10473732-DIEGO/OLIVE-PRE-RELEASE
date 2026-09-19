"""Corroborate a running executable using an installed Start Menu shortcut.

Names alone never merge identities. Supports direct executable shortcuts and the
existing Squirrel updater layout, without running or modifying the shortcut.
"""

import os
from pathlib import Path
import shlex


def matches_executable(target, arguments, executable):
    target, executable = Path(target), Path(executable)
    if not arguments.strip():
        return os.path.normcase(str(target)) == os.path.normcase(str(executable))
    try:
        parts = [part.strip('"') for part in shlex.split(arguments, posix=False)]
    except ValueError:
        return False
    return (target.name.casefold() == "update.exe" and len(parts) == 2
            and parts[0] == "--processStart" and parts[1].casefold() == executable.name.casefold()
            and executable.parent.name.casefold().startswith("app-")
            and os.path.normcase(str(executable.parent.parent)) == os.path.normcase(str(target.parent)))


def shortcut_matches(shortcut, executable):
    import pythoncom
    from win32com.shell import shell
    pythoncom.CoInitialize()
    try:
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(shortcut))
        target, _ = link.GetPath(shell.SLGP_RAWPATH)
        return matches_executable(os.path.expandvars(target), link.GetArguments(), executable)
    except pythoncom.com_error:
        # An unreadable/removed link provides no identity evidence. Keep candidates
        # separate so the caller requests clarification instead of guessing.
        return False
    finally:
        pythoncom.CoUninitialize()
