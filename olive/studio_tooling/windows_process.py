"""Windows pipe jobs with kernel-owned descendant lifetime (no console or PTY).

The child starts suspended, joins a kill-on-close Job Object, then resumes.
Only explicitly owned runs use this adapter. API failures fail closed.
"""
import asyncio
import ctypes
from ctypes import wintypes
import psutil


class JobObject:
    def __init__(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel = kernel
        for name, restype, argtypes in (
            ('CreateJobObjectW', wintypes.HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR]),
            ('SetInformationJobObject', wintypes.BOOL, [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]),
            ('OpenProcess', wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            ('AssignProcessToJobObject', wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE]),
            ('OpenThread', wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            ('ResumeThread', wintypes.DWORD, [wintypes.HANDLE]),
            ('CloseHandle', wintypes.BOOL, [wintypes.HANDLE]),
        ):
            function = getattr(kernel, name); function.restype = restype; function.argtypes = argtypes
        class Basic(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount',
                'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', Counters), ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended(); limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error()); self.close(); raise error

    def attach_and_resume(self, pid):
        process = self.kernel.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
            # CREATE_SUSPENDED has not run user code; only the initial thread exists.
            threads = psutil.Process(pid).threads()
            if len(threads) != 1:
                raise RuntimeError('Unexpected suspended process state')
            thread = self.kernel.OpenThread(0x0002, False, threads[0].id)  # SUSPEND_RESUME
            if not thread:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if self.kernel.ResumeThread(thread) == 0xFFFFFFFF:
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                self.kernel.CloseHandle(thread)
        finally:
            self.kernel.CloseHandle(process)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class OwnedProcess:
    def __init__(self, process, job):
        self.process, self.job = process, job

    def __getattr__(self, name):
        return getattr(self.process, name)

    def kill(self):
        self.job.close()

    terminate = kill

    async def wait(self):
        try:
            return await self.process.wait()
        finally:
            # Also reap descendants when the root exits normally.
            self.job.close()


async def start_owned_process(command, **options):
    job = JobObject()
    process = None
    try:
        options['creationflags'] = options.get('creationflags', 0) | 0x00000004  # CREATE_SUSPENDED
        process = await asyncio.create_subprocess_exec(*command, **options)
        job.attach_and_resume(process.pid)
        return OwnedProcess(process, job)
    except BaseException:
        job.close()
        if process:
            if process.returncode is None:
                process.kill()
            await process.wait()
        raise
