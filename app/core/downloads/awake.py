"""Keep the computer from going to sleep while a long download runs. Windows only; elsewhere it does nothing.

SetThreadExecutionState applies to the calling thread, so call keep_awake(True) and keep_awake(False) from the same
thread (the download's worker thread).
"""
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def keep_awake(on: bool) -> None:
    if sys.platform != 'win32':
        return
    import ctypes
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if on else ES_CONTINUOUS
    ctypes.windll.kernel32.SetThreadExecutionState(flags)
