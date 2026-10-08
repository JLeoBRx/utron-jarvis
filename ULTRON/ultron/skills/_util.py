"""Utilitários compartilhados pelas skills."""
from __future__ import annotations

import os
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

_pyautogui = None


def norm(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").lower())
    return " ".join("".join(c for c in value if unicodedata.category(c) != "Mn").split())


def absolute_path(value: str) -> str:
    value = str(value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    value = os.path.expandvars(os.path.expanduser(value))
    if not value or "\0" in value:
        raise ValueError("caminho inválido")
    return os.path.abspath(value)


def pyautogui():
    """Importa o pyautogui sob demanda com FAILSAFE ligado (canto superior esquerdo aborta)."""
    global _pyautogui
    if _pyautogui is None:
        import pyautogui as module
        module.FAILSAFE = True
        module.PAUSE = 0.08
        _pyautogui = module
    return _pyautogui


def wait_until(predicate: Callable[[], Any], *, timeout: float, interval: float = 0.4, ctx=None) -> Any:
    """Observa até ``predicate`` ser verdadeiro (verificação por observação, não por suposição)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            value = predicate()
        except Exception:
            value = None
        if value:
            return value
        if time.monotonic() >= deadline:
            return value
        if ctx is not None and ctx.wait(interval):
            return value
        if ctx is None:
            time.sleep(interval)


def processes_named(names: set[str]) -> list[dict]:
    try:
        import psutil
    except ImportError:
        return []
    wanted = {n.lower() for n in names}
    found = []
    for proc in psutil.process_iter(["pid", "name", "status", "create_time"]):
        name = (proc.info.get("name") or "").lower()
        if name in wanted:
            found.append({"pid": proc.info["pid"], "name": proc.info["name"], "status": proc.info.get("status"),
                          "started": proc.info.get("create_time")})
    return found


def user_dir(*parts: str) -> Path:
    path = Path.home().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path
