"""Garante uma única instância do JARVIS (duas instâncias disputariam o microfone)."""
from __future__ import annotations

import ctypes
import os
import sys

from ..config import paths

_handle = None
_legacy_handle = None
_lock_file = None
# Mutex do JARVIS original (backend.py): segurá-lo impede que a versão antiga e esta rodem juntas
# disputando o microfone (o original encerra quando encontra o mutex já criado).
LEGACY_NAME = "JARVIS.PersonalAssistant"
blocked_by_legacy = False


def _create(kernel, name: str):
    create = kernel.CreateMutexW
    create.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    create.restype = ctypes.c_void_p
    handle = create(None, False, "Local\\" + name)
    exists = ctypes.get_last_error() == 183           # ERROR_ALREADY_EXISTS
    return handle, exists


def acquire(name: str = "ULTRON.NeuralCore") -> bool:
    global _handle, _legacy_handle, _lock_file, blocked_by_legacy
    if _handle is not None or _lock_file is not None:
        return True
    blocked_by_legacy = False
    if sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        handle, exists = _create(kernel, name)
        if not handle:
            return True                      # sem mutex: não impede a execução
        if exists:
            kernel.CloseHandle(handle)
            return False
        legacy, legacy_exists = _create(kernel, LEGACY_NAME)
        if legacy and legacy_exists:         # o JARVIS original está aberto
            kernel.CloseHandle(legacy)
            kernel.CloseHandle(handle)
            blocked_by_legacy = True
            return False
        _handle, _legacy_handle = handle, legacy
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
    global _handle, _legacy_handle, _lock_file
    if _lock_file is not None:
        try:
            import fcntl
            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
            _lock_file.close()
        except OSError:
            pass
        _lock_file = None
    if sys.platform == "win32":
        for handle in (_handle, _legacy_handle):
            if handle is not None:
                ctypes.windll.kernel32.CloseHandle(handle)
        _handle = _legacy_handle = None
