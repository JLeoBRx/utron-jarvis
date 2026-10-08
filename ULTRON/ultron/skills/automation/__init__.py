"""Skills de automação: mouse, teclado, rolagem e automações salvas pelo usuário.

Proteções herdadas do JARVIS:

* ``pyautogui.FAILSAFE``: jogar o mouse no canto superior esquerdo interrompe qualquer automação;
* digitar ou pressionar Enter em um terminal eleva o risco (exige autorização);
* Delete exige autorização; somente teclas e atalhos de uma lista fechada.
"""
from __future__ import annotations

import time

from ...platform import win32
from .._util import norm, pyautogui
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string

KEYS = {"enter": "enter", "escape": "esc", "esc": "esc", "tab": "tab", "espaco": "space", "space": "space",
        "backspace": "backspace", "retrocesso": "backspace", "cima": "up", "baixo": "down", "esquerda": "left",
        "direita": "right", "up": "up", "down": "down", "left": "left", "right": "right", "home": "home",
        "end": "end", "pageup": "pageup", "pagedown": "pagedown", "delete": "delete", "f5": "f5",
        "windows": "win", "win": "win"}
HOTKEYS = {"ctrl+c": ("ctrl", "c"), "ctrl+v": ("ctrl", "v"), "ctrl+a": ("ctrl", "a"), "ctrl+z": ("ctrl", "z"),
           "ctrl+s": ("ctrl", "s"), "ctrl+f": ("ctrl", "f"), "ctrl+t": ("ctrl", "t"), "ctrl+w": ("ctrl", "w"),
           "ctrl+shift+t": ("ctrl", "shift", "t"), "alt+tab": ("alt", "tab"), "win+d": ("win", "d"),
           "win+e": ("win", "e"), "ctrl+l": ("ctrl", "l")}
TERMINAL_HINTS = ("powershell", "prompt de comando", "command prompt", "cmd.exe", "windows terminal", "terminal",
                  "git bash", "bash", "wsl", "windowsterminal")


def terminal_active() -> bool:
    fg = win32.foreground_window() if win32.AVAILABLE else {}
    haystack = norm(f"{fg.get('title', '')} {fg.get('process', '')}")
    return any(hint in haystack for hint in TERMINAL_HINTS)


class _InputSkill(Skill):
    category = "automation"
    requirements = {"modules": ["pyautogui"]}


class TypeText(_InputSkill):
    name = "input.type_text"
    description = "Digitar texto na janela ativa (até 1000 caracteres)."
    inputs = schema({"text": string(1000)}, ("text",))
    risk = Risk.MEDIUM

    def risk_for(self, args):
        return Risk.HIGH if terminal_active() else Risk.MEDIUM

    def execute(self, ctx, text: str) -> SkillResult:
        import pyperclip
        fg = win32.foreground_window() if win32.AVAILABLE else {}
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
        pyperclip.copy(text)
        pyautogui().hotkey("ctrl", "v")
        time.sleep(0.15)
        if previous is not None:
            try:
                pyperclip.copy(previous)          # restaura a área de transferência do usuário
            except Exception:
                pass
        return SkillResult(True, f"Texto digitado ({len(text)} caracteres).", [f"janela: {fg.get('title', '?')[:60]}"],
                           {"window": fg.get("title", ""), "length": len(text)})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        fg = win32.foreground_window() if win32.AVAILABLE else {}
        same = fg.get("title", "") == result.data.get("window") if win32.AVAILABLE else None
        return VerificationResult.from_checks(
            [check("same_window", same, "o texto foi enviado à janela esperada" if same else
                   "a janela ativa mudou durante a digitação" if same is False else "janela não verificável")],
            unconfirmed_reason="o conteúdo digitado não pode ser lido de volta")


class PressKey(_InputSkill):
    name = "input.press_key"
    description = "Pressionar uma tecla ou atalho permitido (enter, esc, tab, setas, ctrl+c, ctrl+v, alt+tab...)."
    inputs = schema({"key": string(30)}, ("key",))
    risk = Risk.LOW

    def risk_for(self, args):
        key = norm(args.get("key", ""))
        if key == "delete" or key in ("ctrl+w",):
            return Risk.HIGH
        if key == "enter" and terminal_active():
            return Risk.HIGH
        return Risk.LOW

    def validate(self, args):
        args = super().validate(args)
        key = norm(args["key"]).replace(" ", "")
        if key not in KEYS and key not in HOTKEYS:
            raise ValueError(f"tecla fora da lista permitida: {args['key']}")
        return {"key": key}

    def execute(self, ctx, key: str) -> SkillResult:
        if key in HOTKEYS:
            pyautogui().hotkey(*HOTKEYS[key])
        else:
            pyautogui().press(KEYS[key])
        return SkillResult(True, f"Tecla {key} pressionada.", [])


class MoveMouse(_InputSkill):
    name = "input.move_mouse"
    description = "Mover o mouse para coordenadas da tela."
    inputs = schema({"x": {"type": "integer", "minimum": 0, "maximum": 20000},
                     "y": {"type": "integer", "minimum": 0, "maximum": 20000}}, ("x", "y"))
    risk = Risk.LOW

    def execute(self, ctx, x: int, y: int) -> SkillResult:
        width, height = pyautogui().size()
        if not (0 <= x < width and 0 <= y < height):
            return SkillResult(False, error="coordenadas fora da tela", error_kind="INVALID_ARGUMENT")
        pyautogui().moveTo(x, y, duration=0.12)
        return SkillResult(True, f"Mouse em {x}, {y}.", [], {"x": x, "y": y})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        pos = pyautogui().position()
        ok = abs(pos[0] - result.data["x"]) <= 2 and abs(pos[1] - result.data["y"]) <= 2
        return VerificationResult.from_checks([check("cursor_position", ok, f"cursor em {pos[0]}, {pos[1]}")])


class Click(_InputSkill):
    name = "input.click"
    description = "Clicar na posição atual do mouse (esquerdo, direito ou duplo)."
    inputs = schema({"button": string(10, enum=["left", "right", "double"])}, ("button",))
    risk = Risk.MEDIUM
    reversible = False

    def execute(self, ctx, button: str) -> SkillResult:
        gui = pyautogui()
        if button == "double":
            gui.doubleClick()
        else:
            gui.click(button=button)
        return SkillResult(True, f"Clique {button} executado.", [f"posição {tuple(gui.position())}"])


class Scroll(_InputSkill):
    name = "input.scroll"
    description = "Rolar a janela ativa."
    inputs = schema({"direction": string(4, enum=["up", "down"]),
                     "amount": {"type": "integer", "minimum": 1, "maximum": 15}}, ("direction",))
    risk = Risk.LOW

    def execute(self, ctx, direction: str, amount: int = 3) -> SkillResult:
        pyautogui().scroll(amount * 120 if direction == "up" else -amount * 120)
        return SkillResult(True, f"Rolagem para {'cima' if direction == 'up' else 'baixo'}.", [])


# ---------------------------------------------------------------- automações do usuário
SAFE_AUTOMATION_SKILLS = {"app.open", "web.search", "web.open_url", "audio.volume", "audio.media",
                          "fs.search", "network.status", "diagnostics.system_report"}


class CreateAutomation(Skill):
    name = "automation.create"
    description = "Criar uma automação disparada por uma frase exata (apenas ações não destrutivas)."
    category = "automation"
    inputs = schema({"name": string(60), "trigger": string(100),
                     "skill": string(40, enum=sorted(SAFE_AUTOMATION_SKILLS)),
                     "arguments": {"type": "object"}}, ("name", "trigger", "skill", "arguments"))
    risk = Risk.LOW

    def execute(self, ctx, name: str, trigger: str, skill: str, arguments: dict) -> SkillResult:
        registry = ctx.extras.get("registry")
        target = registry.get(skill) if registry else None
        if target is None:
            return SkillResult(False, error=f"skill {skill} indisponível", error_kind="NOT_FOUND")
        clean = target.validate(dict(arguments))
        normalized = ctx.memory.procedural.save_automation(name, trigger, skill, clean)
        return SkillResult(True, f"Automação {name} criada para a frase: {trigger}.", [f"gatilho '{normalized}'"],
                           {"trigger": normalized, "name": name})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        found = ctx.memory.procedural.automation_for(result.data["trigger"])
        return VerificationResult.from_checks([check("persisted", bool(found), "automação gravada na memória"
                                                     if found else "a automação não foi encontrada após gravar")])


class ListAutomations(Skill):
    name = "automation.list"
    description = "Listar automações do usuário."
    category = "automation"
    inputs = schema({})
    risk = Risk.NONE

    def execute(self, ctx, **_) -> SkillResult:
        items = ctx.memory.procedural.automations()
        if not items:
            return SkillResult(True, "Nenhuma automação configurada.", [], {"automations": []})
        text = "; ".join(f"{a['name']} ('{a['trigger']}' → {a['skill']}){'' if a['enabled'] else ' [pausada]'}"
                         for a in items)
        return SkillResult(True, "Automações: " + text, [], {"automations": items})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.95, [check("read", True, "lido da memória procedural")])


class DeleteAutomation(Skill):
    name = "automation.delete"
    description = "Remover uma automação do usuário."
    category = "automation"
    inputs = schema({"name": string(60)}, ("name",))
    risk = Risk.HIGH
    reversible = False

    def execute(self, ctx, name: str) -> SkillResult:
        if not ctx.memory.procedural.delete_automation(name):
            return SkillResult(False, error=f"automação {name} não encontrada", error_kind="NOT_FOUND")
        return SkillResult(True, f"Automação {name} removida.", [], {"name": name})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        names = {a["name"].lower() for a in ctx.memory.procedural.automations()}
        gone = result.data["name"].lower() not in names
        return VerificationResult.from_checks([check("removed", gone, "removida" if gone else "ainda presente")])


SKILLS = (TypeText, PressKey, MoveMouse, Click, Scroll, CreateAutomation, ListAutomations, DeleteAutomation)
