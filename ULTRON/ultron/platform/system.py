"""Execução segura de programas do sistema.

Regras herdadas do JARVIS e mantidas:

* nunca ``shell=True`` e nunca texto livre vindo do usuário ou do modelo como comando;
* scripts PowerShell são FIXOS; valores de listas fechadas entram por variável de
  ambiente, nunca por concatenação;
* sempre com *timeout* e sem janela de console no Windows.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def which(name: str) -> str | None:
    return shutil.which(name)


def run(args: list[str], *, timeout: float = 10.0, env: dict | None = None,
        encoding: str | None = None) -> CommandResult:
    """Executa um vetor de argumentos fixo. Nunca levanta por executável ausente."""
    if not args or not isinstance(args, (list, tuple)):
        raise ValueError("argumentos devem ser uma lista")
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update({k: str(v) for k, v in env.items()})
    try:
        proc = subprocess.run(list(args), capture_output=True, timeout=timeout, env=full_env,
                              creationflags=NO_WINDOW, shell=False)
    except FileNotFoundError:
        return CommandResult(127, "", f"{args[0]} não encontrado")
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", f"{args[0]} excedeu {timeout:.0f}s")
    except OSError as exc:
        return CommandResult(126, "", str(exc))
    enc = encoding or ("cp850" if IS_WINDOWS else "utf-8")
    return CommandResult(proc.returncode, proc.stdout.decode(enc, "replace"), proc.stderr.decode(enc, "replace"))


def powershell(script: str, *, timeout: float = 25.0, **env: str) -> CommandResult:
    """Executa um script PowerShell FIXO (codificado em UTF-16LE). Somente Windows."""
    if not IS_WINDOWS:
        return CommandResult(127, "", "PowerShell disponível apenas no Windows")
    prefix = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    encoded = base64.b64encode((prefix + script).encode("utf-16-le")).decode("ascii")
    return run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-EncodedCommand", encoded], timeout=timeout, env=env, encoding="utf-8")


def spawn_detached(args: list[str]) -> int:
    """Inicia um programa sem esperar (ex.: abrir aplicativo). Devolve o PID."""
    flags = 0
    kwargs: dict = {}
    if IS_WINDOWS:
        flags = NO_WINDOW | 0x00000008     # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(list(args), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, creationflags=flags, shell=False, **kwargs)
    return proc.pid


def open_with_default(path_or_uri: str) -> None:
    """Abre arquivo/pasta/URI com o programa padrão do sistema."""
    if IS_WINDOWS:
        os.startfile(path_or_uri)  # type: ignore[attr-defined]
        return
    opener = which("xdg-open") or which("open")
    if not opener:
        raise RuntimeError("nenhum abridor padrão disponível neste sistema")
    spawn_detached([opener, path_or_uri])
