"""Integração somente-leitura e de controle mínimo com a API Win32 (ctypes).

Fora do Windows todas as funções devolvem estados explícitos de indisponibilidade em vez
de inventar dados.
"""
from __future__ import annotations

import ctypes
import os
import sys
from typing import Any

AVAILABLE = sys.platform == "win32"

if AVAILABLE:
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
else:  # pragma: no cover - plataforma sem Win32
    wintypes = None
    _user32 = _kernel32 = None


def _text(hwnd: int) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value.strip()


def _pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def process_image(pid: int) -> str:
    if not AVAILABLE or not pid:
        return ""
    handle = _kernel32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        _kernel32.CloseHandle(handle)


def _rect(hwnd: int) -> dict[str, int] | None:
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom,
            "width": rect.right - rect.left, "height": rect.bottom - rect.top}


def is_hung(hwnd: int) -> bool:
    """Janela que não processa mensagens há ~5 s ("Não está respondendo")."""
    if not AVAILABLE or not hwnd:
        return False
    try:
        return bool(_user32.IsHungAppWindow(hwnd))
    except Exception:
        return False


def foreground_window() -> dict[str, Any]:
    if not AVAILABLE:
        return {"available": False, "reason": "API Win32 indisponível neste sistema"}
    hwnd = int(_user32.GetForegroundWindow() or 0)
    if not hwnd:
        return {"available": True, "hwnd": 0, "title": "", "process": "", "pid": 0}
    pid = _pid(hwnd)
    return {"available": True, "hwnd": hwnd, "title": _text(hwnd), "pid": pid, "process": process_image(pid),
            "rect": _rect(hwnd), "minimized": bool(_user32.IsIconic(hwnd)), "hung": is_hung(hwnd)}


def enumerate_windows(limit: int = 60) -> list[dict[str, Any]]:
    if not AVAILABLE:
        return []
    windows: list[dict[str, Any]] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if len(windows) >= limit:
            return False
        if not _user32.IsWindowVisible(hwnd):
            return True
        title = _text(hwnd)
        if not title:
            return True
        pid = _pid(hwnd)
        windows.append({"hwnd": int(hwnd), "title": title[:220], "pid": pid, "process": process_image(pid),
                        "minimized": bool(_user32.IsIconic(hwnd)), "hung": is_hung(hwnd)})
        return True

    _user32.EnumWindows(callback_type(callback), 0)
    return windows


def focus_window(hwnd: int) -> bool:
    if not AVAILABLE or not hwnd:
        return False
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)                               # SW_RESTORE
    return bool(_user32.SetForegroundWindow(hwnd))


def show_window(hwnd: int, command: str) -> bool:
    codes = {"minimize": 6, "maximize": 3, "restore": 9}
    if not AVAILABLE or not hwnd or command not in codes:
        return False
    return bool(_user32.ShowWindow(hwnd, codes[command]) or True)


def close_window(hwnd: int) -> bool:
    """Pede o fechamento gracioso (WM_CLOSE). Nunca mata o processo."""
    if not AVAILABLE or not hwnd:
        return False
    return bool(_user32.PostMessageW(hwnd, 0x0010, 0, 0))


def lock_workstation() -> bool:
    return bool(AVAILABLE and _user32.LockWorkStation())


def idle_seconds() -> float | None:
    """Segundos desde a última entrada do usuário (teclado/mouse)."""
    if not AVAILABLE:
        return None

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return max(0.0, (_kernel32.GetTickCount() - info.dwTime) / 1000.0)


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def power_status() -> dict[str, Any] | None:
    if not AVAILABLE:
        return None
    status = _PowerStatus()
    if not _kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return None
    has_battery = not (status.BatteryFlag == 128 or status.BatteryLifePercent == 255)
    return {"has_battery": has_battery,
            "percent": int(status.BatteryLifePercent) if has_battery else None,
            "plugged": status.ACLineStatus == 1}
