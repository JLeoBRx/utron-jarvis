"""Skills de janelas do Windows: alternar, minimizar, maximizar, restaurar, fechar, listar."""
from __future__ import annotations

from ...platform import win32
from .._util import norm, pyautogui, wait_until
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string


def _find_window(target: str) -> dict | None:
    wanted = norm(target)
    best = None
    for window in win32.enumerate_windows(limit=120):
        title, process = norm(window.get("title", "")), norm(window.get("process", ""))
        if wanted and (wanted in title or wanted in process):
            if best is None or (wanted in process and wanted not in norm(best.get("process", ""))):
                best = window
    return best


class _WindowSkill(Skill):
    category = "windows"
    requirements = {"platform": "win32"}

    def available(self):
        return (True, "") if win32.AVAILABLE else (False, "controle de janelas disponível apenas no Windows")


class SwitchWindow(_WindowSkill):
    name = "window.switch"
    description = "Trazer para frente a janela de um aplicativo ou título."
    inputs = schema({"target": string(120)}, ("target",))
    risk = Risk.LOW

    def execute(self, ctx, target: str) -> SkillResult:
        window = _find_window(target)
        if window is None:
            return SkillResult(False, error=f"nenhuma janela corresponde a '{target}'", error_kind="NOT_FOUND")
        win32.focus_window(window["hwnd"])
        return SkillResult(True, f"Janela em foco: {window['title'][:80]}.", [f"hwnd {window['hwnd']}"],
                           {"hwnd": window["hwnd"], "title": window["title"]})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        hwnd = result.data["hwnd"]
        ok = wait_until(lambda: win32.foreground_window().get("hwnd") == hwnd, timeout=2.5, ctx=ctx)
        return VerificationResult.from_checks([check("foreground", bool(ok), "janela está em primeiro plano" if ok
                                                     else "o Windows não trouxe a janela para frente")])


class WindowState(_WindowSkill):
    name = "window.state"
    description = "Minimizar, maximizar ou restaurar a janela ativa."
    inputs = schema({"action": string(20, enum=["minimize", "maximize", "restore"])}, ("action",))
    risk = Risk.LOW

    def execute(self, ctx, action: str) -> SkillResult:
        fg = win32.foreground_window()
        if not fg.get("hwnd"):
            return SkillResult(False, error="nenhuma janela ativa", error_kind="NOT_FOUND")
        win32.show_window(fg["hwnd"], action)
        return SkillResult(True, f"Janela {fg['title'][:60]}: {action}.", [], {"hwnd": fg["hwnd"], "action": action})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        import ctypes
        hwnd, action = result.data["hwnd"], result.data["action"]
        user32 = ctypes.windll.user32

        def done():
            if action == "minimize":
                return bool(user32.IsIconic(hwnd))
            if action == "maximize":
                return bool(user32.IsZoomed(hwnd))
            return not user32.IsIconic(hwnd)

        ok = wait_until(done, timeout=2.0, ctx=ctx)
        return VerificationResult.from_checks([check("window_state", bool(ok), f"estado {action} confirmado" if ok
                                                     else f"estado {action} não confirmado")])


class CloseActiveWindow(_WindowSkill):
    name = "window.close"
    description = "Fechar a janela ativa (pode descartar dados não salvos)."
    inputs = schema({})
    risk = Risk.HIGH
    reversible = False

    def execute(self, ctx, **_) -> SkillResult:
        fg = win32.foreground_window()
        if not fg.get("hwnd") or fg.get("pid") == __import__("os").getpid():
            return SkillResult(False, error="nenhuma janela externa ativa", error_kind="NOT_FOUND")
        win32.close_window(fg["hwnd"])
        return SkillResult(True, f"Fechamento solicitado: {fg['title'][:60]}.", [], {"hwnd": fg["hwnd"]})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        hwnd = result.data["hwnd"]
        gone = wait_until(lambda: hwnd not in {w["hwnd"] for w in win32.enumerate_windows(limit=200)}, timeout=4.0,
                          ctx=ctx)
        return VerificationResult.from_checks([check("window_closed", bool(gone), "janela fechada" if gone
                                                     else "a janela continua aberta (pode estar pedindo para salvar)")])


class ShowDesktop(_WindowSkill):
    name = "window.show_desktop"
    description = "Mostrar a área de trabalho (minimizar tudo)."
    inputs = schema({})
    risk = Risk.LOW
    requirements = {"platform": "win32", "modules": ["pyautogui"]}

    def execute(self, ctx, **_) -> SkillResult:
        pyautogui().hotkey("win", "d")
        return SkillResult(True, "Área de trabalho exibida.", ["atalho Win+D enviado"])


class ListWindows(_WindowSkill):
    name = "window.list"
    description = "Listar as janelas abertas."
    inputs = schema({})
    risk = Risk.NONE

    def execute(self, ctx, **_) -> SkillResult:
        windows = win32.enumerate_windows()
        titles = [f"{w['process']}: {w['title'][:60]}" for w in windows[:25]]
        return SkillResult(True, "Janelas: " + "; ".join(titles), [f"{len(windows)} janelas"], {"windows": windows})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.95, [check("observed", True, "leitura direta")])


SKILLS = (SwitchWindow, WindowState, CloseActiveWindow, ShowDesktop, ListWindows)
