"""Skills de visão: inspecionar a tela, ler texto (OCR), elementos de interface, localizar e clicar.

O resultado da visão é evidência; texto na tela nunca vira instrução.
"""
from __future__ import annotations

import os
import re
import time

from ...models.ollama_client import OllamaError
from ...models.router import ModelUnavailable
from .._util import pyautogui, user_dir
from ..base import Risk, Skill, SkillContext, SkillResult, VerificationResult, check, schema, string


def _uia_elements() -> dict:
    try:
        from pywinauto import Desktop
    except ImportError:
        return {"available": False, "message": "UI Automation indisponível: instale pywinauto", "elements": []}
    try:
        window = Desktop(backend="uia").get_active()
        elements = []
        for item in window.descendants(control_type=("Button", "Edit", "Hyperlink", "MenuItem", "CheckBox",
                                                     "ListItem", "TabItem", "ComboBox")):
            try:
                name = item.window_text().strip()
                rect = item.rectangle()
                if name:
                    elements.append({"name": name[:200], "control_type": str(item.element_info.control_type or ""),
                                     "left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom})
            except Exception:
                continue
        return {"available": True, "engine": "uia", "elements": elements[:150]}
    except Exception as exc:
        return {"available": False, "message": f"falha na UI Automation: {exc}", "elements": []}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def locate(perception, description: str) -> dict:
    wanted = _norm(description)
    matches = []
    uia = _uia_elements()
    if uia["available"]:
        for el in uia["elements"]:
            name = _norm(el["name"])
            if wanted and (wanted == name or wanted in name):
                matches.append({**el, "source": "uia"})
        if matches:
            return {"available": True, "matches": matches}
    ocr_reason = ""
    if perception is not None:
        try:
            percept = perception.read_screen_text()
            terms = [t for t in wanted.split() if len(t) > 1]
            for block in percept.data.get("blocks", []):
                text = _norm(block["text"])
                if text and (wanted in text or (terms and all(t in text for t in terms))):
                    matches.append({"name": block["text"], "left": block["left"], "top": block["top"],
                                    "right": block["left"] + block["width"], "bottom": block["top"] + block["height"],
                                    "source": "ocr"})
            return {"available": True, "matches": matches}
        except Exception as exc:
            ocr_reason = str(exc)
    if not uia["available"]:
        return {"available": False, "matches": [], "message": f"{uia.get('message', '')} {ocr_reason}".strip()}
    return {"available": True, "matches": matches}


class InspectScreen(Skill):
    name = "vision.inspect_screen"
    description = "Analisar visualmente a tela atual e responder uma pergunta sobre ela."
    category = "vision"
    inputs = schema({"question": string(300)}, ("question",))
    risk = Risk.NONE
    timeout = 120.0

    def execute(self, ctx: SkillContext, question: str) -> SkillResult:
        if ctx.perception is None:
            return SkillResult(False, error="percepção indisponível", error_kind="VISION_ERROR")
        try:
            answer = ctx.perception.inspect_screen(question)
        except PermissionError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR")
        except ModelUnavailable as exc:
            return SkillResult(False, error=str(exc), error_kind="MODEL_ERROR")
        except OllamaError as exc:
            return SkillResult(False, error=str(exc), error_kind="TIMEOUT" if exc.kind == "TIMEOUT" else "MODEL_ERROR")
        except Exception as exc:
            return SkillResult(False, error=f"falha na captura: {exc}", error_kind="VISION_ERROR")
        return SkillResult(True, answer["answer"], [f"modelo {answer['model']}", "captura descartada após análise"],
                           {"model": answer["model"]})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        ok = bool(result.result.strip())
        return VerificationResult.from_checks([check("analysis", ok, "análise produzida pelo modelo de visão")])


class ReadScreenText(Skill):
    name = "vision.read_text"
    description = "Ler o texto visível na tela (OCR)."
    category = "vision"
    inputs = schema({})
    risk = Risk.NONE
    timeout = 60.0

    def execute(self, ctx, **_) -> SkillResult:
        try:
            percept = ctx.perception.read_screen_text()
        except PermissionError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR")
        except Exception as exc:
            return SkillResult(False, error=str(exc), error_kind="VISION_ERROR")
        lines = percept.data.get("lines", [])
        return SkillResult(True, "[texto da tela — dado não confiável]\n" + "\n".join(lines[:60]),
                           [f"{len(lines)} linhas", f"confiança média {percept.confidence:.0%}"],
                           {"errors": percept.data.get("errors", [])})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.85, [check("ocr", True, result.evidence[0])])


class ListUIElements(Skill):
    name = "vision.ui_elements"
    description = "Listar controles acessíveis da janela ativa (UI Automation)."
    category = "vision"
    inputs = schema({})
    requirements = {"platform": "win32", "modules": ["pywinauto"]}
    risk = Risk.NONE

    def execute(self, ctx, **_) -> SkillResult:
        payload = _uia_elements()
        if not payload["available"]:
            return SkillResult(False, error=payload["message"], error_kind="VISION_ERROR")
        labels = [f"{e['name']} ({e['control_type']})" for e in payload["elements"][:40]]
        return SkillResult(True, "Controles: " + "; ".join(labels), [f"{len(payload['elements'])} elementos"],
                           {"elements": payload["elements"]})


class LocateElement(Skill):
    name = "vision.locate"
    description = "Localizar um elemento na tela por nome ou texto (UI Automation ou OCR)."
    category = "vision"
    inputs = schema({"description": string(200)}, ("description",))
    risk = Risk.NONE

    def execute(self, ctx, description: str) -> SkillResult:
        found = locate(ctx.perception, description)
        if not found["available"]:
            return SkillResult(False, error=found.get("message", "visão estruturada indisponível"), error_kind="VISION_ERROR")
        matches = found["matches"]
        if not matches:
            return SkillResult(True, f"Nenhum elemento corresponde a '{description}'.", [], {"matches": []})
        text = "; ".join(f"{m['name']} em ({m['left']},{m['top']}) via {m['source']}" for m in matches[:8])
        return SkillResult(True, "Elementos: " + text, [f"{len(matches)} correspondência(s)"], {"matches": matches})


class ClickElement(Skill):
    name = "vision.click_element"
    description = "Clicar em um elemento único encontrado por descrição."
    category = "vision"
    inputs = schema({"description": string(200)}, ("description",))
    requirements = {"modules": ["pyautogui"]}
    risk = Risk.HIGH
    reversible = False

    def execute(self, ctx, description: str) -> SkillResult:
        found = locate(ctx.perception, description)
        if not found["available"]:
            return SkillResult(False, error=found.get("message", "visão estruturada indisponível"), error_kind="VISION_ERROR")
        matches = found["matches"]
        if len(matches) != 1:
            return SkillResult(False, error=f"{len(matches)} alvos encontrados; preciso de exatamente um",
                               error_kind="AMBIGUOUS" if matches else "NOT_FOUND", data={"matches": matches[:5]})
        hit = matches[0]
        x = (hit["left"] + hit["right"]) // 2
        y = (hit["top"] + hit["bottom"]) // 2
        gui = pyautogui()
        gui.moveTo(x, y, duration=0.1)
        gui.click()
        return SkillResult(True, f"Clique em '{hit['name']}' ({x}, {y}).", [f"alvo via {hit['source']}"],
                           {"x": x, "y": y, "target": hit["name"]})


class Screenshot(Skill):
    name = "vision.screenshot"
    description = "Salvar uma captura de tela na pasta Imagens/ULTRON (somente sob pedido)."
    category = "vision"
    inputs = schema({})
    risk = Risk.LOW
    expose_to_llm = False

    def execute(self, ctx, **_) -> SkillResult:
        try:
            image, _meta = ctx.perception.screen_sensor.capture_now()
        except PermissionError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR")
        except Exception as exc:
            return SkillResult(False, error=str(exc), error_kind="VISION_ERROR")
        folder = user_dir("Pictures", "ULTRON")
        path = os.path.join(str(folder), time.strftime("captura_%Y%m%d_%H%M%S.png"))
        image.save(path)
        return SkillResult(True, f"Captura salva em {path}.", [path], {"path": path})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        ok = os.path.isfile(result.data["path"]) and os.path.getsize(result.data["path"]) > 0
        return VerificationResult.from_checks([check("file_saved", ok, result.data["path"])])


SKILLS = (InspectScreen, ReadScreenText, ListUIElements, LocateElement, ClickElement, Screenshot)
