"""Tie the backend and its planning workers to one Windows lifetime."""
import ctypes as C
from ctypes import wintypes as W

def create_job():
    class Basic(C.Structure):
        _fields_ = [('process_time', C.c_int64), ('job_time', C.c_int64),
                    ('flags', W.DWORD), ('min_working', C.c_size_t), ('max_working', C.c_size_t),
                    ('active_limit', W.DWORD), ('affinity', C.c_size_t),
                    ('priority', W.DWORD), ('scheduling', W.DWORD)]
    class IO(C.Structure):
        _fields_ = [(name,C.c_uint64) for name in ('reads','writes','other','read_bytes','write_bytes','other_bytes')]
    class Extended(C.Structure):
        _fields_ = [('basic',Basic),('io',IO),('process_memory',C.c_size_t),
                    ('job_memory',C.c_size_t),('peak_process',C.c_size_t),('peak_job',C.c_size_t)]
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [C.c_void_p, W.LPCWSTR]
    kernel.CreateJobObjectW.restype = W.HANDLE
    kernel.SetInformationJobObject.argtypes = [W.HANDLE,C.c_int,C.c_void_p,W.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [W.HANDLE,W.HANDLE]
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    job=kernel.CreateJobObjectW(None,None)
    if not job: raise C.WinError(C.get_last_error())
    limits=Extended();limits.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job,9,C.byref(limits),C.sizeof(limits)):
        error=C.get_last_error();kernel.CloseHandle(job);raise C.WinError(error)
    if not kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()):
        error=C.get_last_error();kernel.CloseHandle(job);raise C.WinError(error)
    return job  # Keep this non-inheritable handle open until process exit.
