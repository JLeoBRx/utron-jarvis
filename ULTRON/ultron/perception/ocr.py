"""Sensor de OCR (texto visível na tela).

Usa ``pytesseract`` + Tesseract OCR quando instalados. Sem eles, o sensor se declara
indisponível. Blocos que parecem segredos são descartados antes de qualquer uso.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable

from ..memory.store import looks_secret
from .base import Percept, Sensor, SensorUnavailable

ERROR_PATTERN = re.compile(
    r"Traceback|Exception|Error\b|Erro\b|ModuleNotFoundError|ImportError|SyntaxError|NameError|TypeError|"
    r"falha|failed|fatal|not found|não encontrado|denied|negado", re.I)


_WINDOWS_TESSERACT = (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                      r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe")


def tesseract_available() -> tuple[bool, str]:
    """Verifica pytesseract e o executável (PATH ou pasta padrão do instalador no Windows)."""
    try:
        import pytesseract
    except ImportError:
        return False, "OCR indisponível: instale pytesseract e o Tesseract OCR"
    configured = pytesseract.pytesseract.tesseract_cmd
    if shutil.which(configured or "tesseract"):
        return True, ""
    for candidate in _WINDOWS_TESSERACT:
        if Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return True, ""
    return False, "OCR indisponível: executável do Tesseract não encontrado"


def read_blocks(image) -> list[dict[str, Any]]:
    import pytesseract
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, lang="por+eng")
    blocks = []
    for i, text in enumerate(data.get("text", [])):
        text = " ".join(str(text).split())
        if not text or looks_secret(text):
            continue
        try:
            conf = float(data.get("conf", [0])[i])
        except (TypeError, ValueError, IndexError):
            conf = 0.0
        blocks.append({"text": text, "confidence": conf, "left": int(data["left"][i]), "top": int(data["top"][i]),
                       "width": int(data["width"][i]), "height": int(data["height"][i])})
    return blocks


def lines_from_blocks(blocks: list[dict[str, Any]], tolerance: int = 8) -> list[str]:
    rows: list[list[dict]] = []
    for block in sorted(blocks, key=lambda b: (b["top"], b["left"])):
        for row in rows:
            if abs(row[0]["top"] - block["top"]) <= tolerance:
                row.append(block)
                break
        else:
            rows.append([block])
    return [" ".join(b["text"] for b in sorted(row, key=lambda b: b["left"])) for row in rows]


class OCRSensor(Sensor):
    name = "ocr"
    kind = "textual"
    worker = "vision"

    def __init__(self, capture: Callable[[], tuple], *, interval: float = 60.0, periodic: bool = False):
        super().__init__(interval)
        self._capture = capture
        self.periodic = periodic

    def available(self) -> tuple[bool, str]:
        return tesseract_available()

    def sense(self) -> Percept | None:
        if not self.periodic:
            return None
        return self.read_screen()

    def read_screen(self) -> Percept:
        ok, reason = self.available()
        if not ok:
            raise SensorUnavailable(reason)
        image, meta = self._capture()
        try:
            blocks = read_blocks(image)
        finally:
            del image
        lines = lines_from_blocks(blocks)
        errors = [line for line in lines if ERROR_PATTERN.search(line)][:10]
        mean_conf = sum(b["confidence"] for b in blocks) / len(blocks) / 100.0 if blocks else 0.0
        percept = Percept("ocr", "textual", {"lines": lines[:120], "blocks": blocks[:300], "errors": errors,
                                             "foreground": meta.get("foreground", {})}, max(0.0, min(1.0, mean_conf)))
        self.last = percept
        return percept
