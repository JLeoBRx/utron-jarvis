"""Controle do processo do JARVIS pela linha de comando: ``--status`` e ``--stop``.

* ao iniciar, a instância registra o PID em ``<dados>/jarvis.pid`` (e o apaga ao sair);
* ``--stop`` não mata nada à força: cria ``<dados>/parar.solicitado``; a instância em execução
  verifica esse pedido a cada ~1,5 s e encerra do jeito normal (lembretes, banco e microfone
  fechados em ordem). Se ela não sair no prazo, o comando diz isso e sugere bandeja > Sair;
* só um processo cujo comando é o do JARVIS (``main.py`` ou ``-m ultron``) é considerado.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from ..config import paths

PID_FILE = "jarvis.pid"
STOP_FILE = "parar.solicitado"


def pid_path() -> Path:
    return paths.data_file(PID_FILE)


def stop_path() -> Path:
    return paths.data_file(STOP_FILE)


def register(pid: int | None = None) -> None:
    pid_path().write_text(str(pid or os.getpid()), encoding="ascii")
    clear_stop_request()


def unregister() -> None:
    try:
        path = pid_path()
        if path.is_file() and path.read_text(encoding="ascii").strip() == str(os.getpid()):
            path.unlink()
    except OSError:
        pass


def _is_jarvis(pid: int) -> bool:
    try:
        import psutil
        process = psutil.Process(pid)
        command = " ".join(process.cmdline()).casefold()
    except Exception:
        return False
    return "main.py" in command or "-m ultron" in command or "ultron" in command.split()


def running_pid() -> int | None:
    """PID da instância em execução, se houver (arquivo de PID + processo do JARVIS vivo)."""
    try:
        pid = int(pid_path().read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None
    return pid if pid != os.getpid() and _is_jarvis(pid) else None


def request_stop() -> None:
    stop_path().write_text(str(time.time()), encoding="ascii")


def clear_stop_request() -> None:
    try:
        stop_path().unlink()
    except OSError:
        pass


def stop_requested() -> bool:
    return stop_path().is_file()


def stop(timeout: float = 15.0, *, sleep=time.sleep) -> tuple[bool, str]:
    """Pede o encerramento limpo da instância em execução e espera até ``timeout`` segundos."""
    pid = running_pid()
    if pid is None:
        clear_stop_request()
        return True, "O JARVIS não está em execução."
    request_stop()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if running_pid() is None:
            clear_stop_request()
            return True, f"JARVIS encerrado (processo {pid})."
        sleep(0.3)
    return False, (f"O JARVIS (processo {pid}) não encerrou em {timeout:.0f} s. Use o ícone da bandeja > Sair; "
                   "se a janela não responder, finalize o processo pelo Gerenciador de Tarefas.")
