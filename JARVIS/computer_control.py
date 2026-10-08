"""J.A.R.V.I.S. // COMPUTER CONTROL LAYER

Camada unificada para ações de computador. Ela não cria permissões novas:
usa somente primitivas já expostas pelo registro allowlisted e mantém um
modo de pré-visualização (dry-run) para planejamento/testes.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import platform
import time

import commands


@dataclass
class ControlResult:
    ok: bool
    action: str
    message: str
    verified: bool = False
    evidence: str = ""
    requires_confirmation: bool = False

    def to_dict(self):
        return asdict(self)


def capabilities() -> dict:
    """Descreve capacidades físicas disponíveis sem executar nada."""
    return {
        "platform": platform.system(),
        "mouse": True,
        "keyboard": True,
        "windows": platform.system() == "Windows",
        "screen": True,
        "allowlist_authority": "commands.py",
    }


def _execute(name: str, args: dict, *, dry_run=False) -> ControlResult:
    if dry_run:
        return ControlResult(True, name, f"Pré-visualização: {name}({args!r})", False,
                             "dry_run", False)

    handled, result = commands.execute_tool(name, args)
    if not handled:
        return ControlResult(False, name, "Ferramenta não disponível na allowlist.", False,
                             "allowlist", False)
    pending = commands.is_confirmation_pending()
    verification = commands.verify_tool(name, args, result) if not pending else {
        "verified": False, "evidence": result or "Aguardando confirmação."
    }
    return ControlResult(
        ok=bool(result is not None), action=name, message=str(result or ""),
        verified=bool(verification.get("verified")),
        evidence=str(verification.get("evidence", "")),
        requires_confirmation=pending,
    )


def move_mouse(x: int, y: int, *, dry_run=False):
    return _execute("move_mouse", {"x": int(x), "y": int(y)}, dry_run=dry_run)


def click(button="left", *, dry_run=False):
    return _execute("mouse_click", {"button": str(button)}, dry_run=dry_run)


def type_text(text: str, *, dry_run=False):
    return _execute("type_text", {"text": str(text)[:500]}, dry_run=dry_run)


def press_key(key: str, *, dry_run=False):
    return _execute("press_key", {"key": str(key)}, dry_run=dry_run)


def scroll(direction="down", amount=1, *, dry_run=False):
    return _execute("scroll", {"direction": str(direction), "amount": int(amount)}, dry_run=dry_run)


def window(action: str, *, dry_run=False):
    return _execute("control_window", {"action": str(action)}, dry_run=dry_run)


def open_app(name: str, *, dry_run=False):
    return _execute("open_app", {"name": str(name)}, dry_run=dry_run)


def wait(seconds: int, *, dry_run=False):
    seconds = max(1, min(10, int(seconds)))
    if dry_run:
        return ControlResult(True, "wait_seconds", f"Pré-visualização: aguardaria {seconds}s.", False, "dry_run")
    result = _execute("wait_seconds", {"seconds": seconds})
    return result


def execute(action: dict, *, dry_run=False) -> ControlResult:
    """Executa uma ação estruturada usando somente primitivas conhecidas."""
    if not isinstance(action, dict):
        return ControlResult(False, "unknown", "Ação inválida.")
    name = str(action.get("tool", "")).strip()
    args = action.get("arguments", {})
    if name not in {
        "move_mouse", "mouse_click", "type_text", "press_key", "scroll",
        "control_window", "open_app", "wait_seconds",
    }:
        return ControlResult(False, name or "unknown", "Ação fora da camada de controle permitida.")
    if not isinstance(args, dict):
        return ControlResult(False, name, "Argumentos inválidos.")
    return _execute(name, args, dry_run=dry_run)
