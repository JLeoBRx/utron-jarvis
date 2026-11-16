"""Sensor de janelas: janela ativa, aplicação em foco, janelas abertas e travamentos."""
from __future__ import annotations

import os
import re
import sys
import time
from typing import Callable

from ..platform import system, win32
from .base import Percept, Sensor, SensorUnavailable

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

APP_NAMES = {
    "code.exe": "VS Code", "devenv.exe": "Visual Studio", "pycharm64.exe": "PyCharm", "idea64.exe": "IntelliJ IDEA",
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox", "explorer.exe": "Explorador",
    "windowsterminal.exe": "Terminal", "cmd.exe": "Prompt de Comando", "powershell.exe": "PowerShell",
    "winword.exe": "Word", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint", "outlook.exe": "Outlook",
    "notepad.exe": "Bloco de Notas", "spotify.exe": "Spotify", "discord.exe": "Discord", "obs64.exe": "OBS",
    "steam.exe": "Steam", "mspaint.exe": "Paint", "calculatorapp.exe": "Calculadora", "taskmgr.exe": "Gerenciador de Tarefas",
}


def app_name(process: str, title: str = "") -> str:
    key = (process or "").lower()
    if key in APP_NAMES:
        return APP_NAMES[key]
    if key.endswith(".exe"):
        key = key[:-4]
    return key.replace("_", " ").title() if key else (title.split(" - ")[-1].strip() if title else "")


def _linux_foreground() -> dict:
    if not system.which("xdotool") or not os.environ.get("DISPLAY"):
        raise SensorUnavailable("janela ativa indisponível (Win32 ausente e xdotool/DISPLAY não encontrados)")
    title = system.run(["xdotool", "getactivewindow", "getwindowname"], timeout=2, encoding="utf-8")
    pid = system.run(["xdotool", "getactivewindow", "getwindowpid"], timeout=2, encoding="utf-8")
    if not title.ok:
        raise SensorUnavailable("xdotool não conseguiu ler a janela ativa")
    proc_name = ""
    if pid.ok and pid.stdout.strip().isdigit() and psutil is not None:
        try:
            proc_name = psutil.Process(int(pid.stdout.strip())).name()
        except Exception:
            proc_name = ""
    return {"available": True, "hwnd": 0, "title": title.stdout.strip(),
            "pid": int(pid.stdout.strip()) if pid.stdout.strip().isdigit() else 0,
            "process": proc_name, "hung": False, "minimized": False}


class WindowSensor(Sensor):
    name = "windows"
    kind = "structural"

    def __init__(self, interval: float = 1.0, *, on_change: Callable[[dict, dict], None] | None = None,
                 on_hung: Callable[[dict], None] | None = None, list_every: float = 5.0):
        super().__init__(interval)
        self._on_change = on_change
        self._on_hung = on_hung
        self._previous: dict = {}
        self._hung_count: dict[int, int] = {}
        self._reported_hung: set[int] = set()
        self._list_every = list_every
        self._last_list = 0.0
        self._windows: list[dict] = []
        self.focus_started = time.time()

    def available(self) -> tuple[bool, str]:
        if win32.AVAILABLE:
            return True, ""
        if sys.platform.startswith("linux") and system.which("xdotool") and os.environ.get("DISPLAY"):
            return True, ""
        return False, "leitura de janelas requer Windows (ou xdotool com servidor gráfico)"

    def sense(self) -> Percept:
        fg = win32.foreground_window() if win32.AVAILABLE else _linux_foreground()
        now = time.time()
        if win32.AVAILABLE and now - self._last_list >= self._list_every:
            self._windows = win32.enumerate_windows()
            self._last_list = now
            self._check_hung(self._windows)
        fg["application"] = app_name(fg.get("process", ""), fg.get("title", ""))
        previous = self._previous
        changed_window = (fg.get("hwnd"), fg.get("title")) != (previous.get("hwnd"), previous.get("title"))
        changed_app = fg.get("process") != previous.get("process")
        if changed_app:
            self.focus_started = now
        if (changed_window or changed_app) and self._on_change and previous:
            self._on_change(previous, fg)
        self._previous = fg
        data = {"foreground": fg, "windows": self._windows, "changed_window": changed_window,
                "changed_app": changed_app, "focus_seconds": round(now - self.focus_started, 1),
                "idle_seconds": win32.idle_seconds()}
        return Percept("window", "structural", data, 0.98 if win32.AVAILABLE else 0.8)

    def _check_hung(self, windows: list[dict]) -> None:
        hung_now = {w["hwnd"]: w for w in windows if w.get("hung")}
        for hwnd in list(self._hung_count):
            if hwnd not in hung_now:
                self._hung_count.pop(hwnd, None)
                self._reported_hung.discard(hwnd)
        for hwnd, window in hung_now.items():
            self._hung_count[hwnd] = self._hung_count.get(hwnd, 0) + 1
            if self._hung_count[hwnd] >= 2 and hwnd not in self._reported_hung and self._on_hung:
                self._reported_hung.add(hwnd)        # dois ciclos seguidos: travamento confirmado
                self._on_hung({**window, "application": app_name(window.get("process", ""), window.get("title", ""))})

    @property
    def windows(self) -> list[dict]:
        return list(self._windows)

    @staticmethod
    def title_matches(title: str, pattern: re.Pattern) -> bool:
        return bool(pattern.search(title or ""))
