"""J.A.R.V.I.S. // WINDOWS STATE ADAPTER

Leitura estruturada e somente-leitura do estado do Windows.
Não executa ações e não altera janelas/processos.

Quando executado fora do Windows, retorna um estado explícito de indisponibilidade
em vez de simular dados.
"""
from __future__ import annotations

import os
import time
import ctypes
from ctypes import wintypes

_USER32 = None
_KERNEL32 = None
if os.name == "nt":
    _USER32 = ctypes.windll.user32
    _KERNEL32 = ctypes.windll.kernel32


def available() -> bool:
    return os.name == "nt" and _USER32 is not None and _KERNEL32 is not None


def _text(hwnd) -> str:
    if not hwnd or not available():
        return ""
    length = _USER32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _USER32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value.strip()


def _pid(hwnd):
    pid = wintypes.DWORD(0)
    _USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _process_name(pid: int) -> str:
    if not pid or not available():
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = _KERNEL32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if _KERNEL32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        _KERNEL32.CloseHandle(handle)


def _rect(hwnd):
    rect = wintypes.RECT()
    if not hwnd or not _USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return {"left": int(rect.left), "top": int(rect.top),
            "right": int(rect.right), "bottom": int(rect.bottom),
            "width": int(rect.right - rect.left),
            "height": int(rect.bottom - rect.top)}


def active_window() -> dict:
    """Retorna a janela em primeiro plano e seu processo."""
    if not available():
        return {"available": False, "reason": "Windows API indisponível neste sistema"}
    hwnd = int(_USER32.GetForegroundWindow() or 0)
    if not hwnd:
        return {"available": True, "hwnd": 0, "title": "", "process": "", "pid": 0}
    pid = _pid(hwnd)
    return {
        "available": True,
        "hwnd": hwnd,
        "title": _text(hwnd),
        "process": _process_name(pid),
        "pid": pid,
        "rect": _rect(hwnd),
        "is_visible": bool(_USER32.IsWindowVisible(hwnd)),
        "is_minimized": bool(_USER32.IsIconic(hwnd)),
    }


def _enumerate_windows():
    if not available():
        return []
    windows = []
    CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not _USER32.IsWindowVisible(hwnd) or _USER32.IsIconic(hwnd):
            return True
        title = _text(hwnd)
        if not title:
            return True
        pid = _pid(hwnd)
        windows.append({
            "hwnd": int(hwnd),
            "title": title[:220],
            "pid": pid,
            "process": _process_name(pid),
            "rect": _rect(hwnd),
        })
        return True

    _USER32.EnumWindows(CALLBACK(callback), 0)
    return windows


def snapshot(*, include_windows: bool = True, max_windows: int = 40) -> dict:
    """Captura um retrato somente-leitura do estado estrutural do Windows."""
    now = time.time()
    if not available():
        return {
            "timestamp": now,
            "platform": os.name,
            "available": False,
            "active_window": active_window(),
            "windows": [],
        }
    windows = _enumerate_windows() if include_windows else []
    return {
        "timestamp": now,
        "platform": "windows",
        "available": True,
        "active_window": active_window(),
        "windows": windows[:max(1, int(max_windows))],
    }


def diff(previous: dict | None, current: dict | None) -> dict:
    """Compara dois snapshots sem inferir intenção."""
    previous = previous or {}
    current = current or {}
    pa = previous.get("active_window") or {}
    ca = current.get("active_window") or {}
    changes = []
    if (pa.get("hwnd"), pa.get("pid"), pa.get("title")) != (ca.get("hwnd"), ca.get("pid"), ca.get("title")):
        changes.append("active_window")
    prev_map = {w.get("hwnd"): w for w in previous.get("windows") or []}
    curr_map = {w.get("hwnd"): w for w in current.get("windows") or []}
    opened = [w for h, w in curr_map.items() if h not in prev_map]
    closed = [w for h, w in prev_map.items() if h not in curr_map]
    if opened: changes.append("windows_opened")
    if closed: changes.append("windows_closed")
    return {
        "changed": bool(changes),
        "changes": changes,
        "opened": opened[:10],
        "closed": closed[:10],
        "timestamp": current.get("timestamp", time.time()),
    }
