"""Garante uma única instância do ULTRON (duas instâncias disputariam o microfone)."""
from __future__ import annotations

import ctypes
import os
import sys

from ..config import paths

_handle = None
_lock_file = None


def acquire(name: str = "ULTRON.NeuralCore") -> bool:
    global _handle, _lock_file
    if _handle is not None or _lock_file is not None:
        return True
    if sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateMutexW
        create.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        create.restype = ctypes.c_void_p
        handle = create(None, False, "Local\\" + name)
        if not handle:
            return True                      # sem mutex: não impede a execução
        if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
            kernel.CloseHandle(handle)
            return False
        _handle = handle
        return True
    import fcntl

    path = paths.data_file("ultron.lock")
    handle = open(path, "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _lock_file = handle
    return True


def release() -> None:
    global _handle, _lock_file
    if _lock_file is not None:
        try:
            import fcntl
            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
            _lock_file.close()
        except OSError:
            pass
        _lock_file = None
    if _handle is not None and sys.platform == "win32":
        ctypes.windll.kernel32.CloseHandle(_handle)
        _handle = None
