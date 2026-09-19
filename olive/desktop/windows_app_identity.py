"""Read the Windows-assigned packaged application identity for a process."""

def process_application_id(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetApplicationUserModelId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    kernel.GetApplicationUserModelId.restype = wintypes.LONG
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ""  # Processes outside the user's inspection rights have no usable identity.
    try:
        length = wintypes.UINT(0)
        if kernel.GetApplicationUserModelId(handle, ctypes.byref(length), None) != 122 or not 1 <= length.value <= 512:
            return ""
        buffer = ctypes.create_unicode_buffer(length.value)
        return buffer.value if kernel.GetApplicationUserModelId(handle, ctypes.byref(length), buffer) == 0 else ""
    finally:
        kernel.CloseHandle(handle)
