"""Sensor de tela: captura em memória, privacidade e detecção de mudança.

* A captura nunca é gravada em disco nem enviada à rede.
* Não captura quando a HUD cobre a tela, quando o próprio JARVIS está em foco, em apps
  excluídos (gerenciadores de senha etc.) ou em janelas com título sensível.
* Mudança: miniatura 48×27 em tons de cinza comparada com a anterior (método do Observador
  do JARVIS, preservado).
"""
from __future__ import annotations

import base64
import io
import os
import re
import threading
import time
import unicodedata
from typing import Any, Callable

from .base import Percept, Sensor, SensorUnavailable

THUMB_W, THUMB_H = 48, 27
CHANGE_THRESHOLD = 0.03
SETTLED_THRESHOLD = 0.012

DEFAULT_EXCLUDED = (
    "keepass", "bitwarden", "1password", "lastpass", "dashlane", "nordpass", "enpass",
    "credential", "windows security", "seguranca do windows", "lockapp",
)
SENSITIVE_TITLE_RE = re.compile(
    r"senha|password|passwd|palavra-passe|credencia|\blogin\b|entrar|sign[ -]?in|log[ -]?in|"
    r"banco|bank|cart[aã]o|card number|cvv|\bpix\b|token|2fa|autentica|verifica[cç][aã]o em duas|"
    r"api[ _-]?key|secret|private key|chave privada|carteira|wallet|seed phrase",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    return "".join(c for c in value if unicodedata.category(c) != "Mn")


def capture_image():
    """Captura a tela principal como imagem PIL (somente em memória)."""
    errors = []
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.rgb)
    except Exception as exc:
        errors.append(f"mss: {exc}")
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception as exc:
        errors.append(f"ImageGrab: {exc}")
    raise SensorUnavailable("captura de tela indisponível (" + "; ".join(errors) + ")")


def encode(image, max_side: int = 1280) -> str:
    copy = image.copy()
    copy.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    copy.convert("RGB").save(buffer, format="JPEG", quality=82)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def thumb(image) -> bytes:
    return image.convert("L").resize((THUMB_W, THUMB_H)).tobytes()


def diff(a: bytes | None, b: bytes | None) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    return sum(abs(x - y) for x, y in zip(a, b)) / (255.0 * len(a))


class ScreenSensor(Sensor):
    name = "screen"
    kind = "visual"

    def __init__(self, interval: float = 3.0, *, foreground: Callable[[], dict] | None = None,
                 hud_covering: Callable[[], bool] | None = None, excluded: Callable[[], tuple] | None = None,
                 enabled: Callable[[], bool] | None = None, capture: Callable[[], Any] | None = None):
        super().__init__(interval)
        self._foreground = foreground or (lambda: {})
        self._hud_covering = hud_covering or (lambda: False)
        self._excluded = excluded or (lambda: ())
        self._enabled = enabled or (lambda: True)
        self._capture = capture or capture_image
        self._lock = threading.Lock()
        self._image = None
        self._image_meta: dict = {}
        self._prev_thumb: bytes | None = None
        self.analyzed_thumb: bytes | None = None
        self.skip_reason = ""
        self.sensitive_until: dict[str, float] = {}

    def available(self) -> tuple[bool, str]:
        if not self._enabled():
            return False, "observação de tela desativada nas configurações"
        return True, ""

    @staticmethod
    def context_key(fg: dict) -> str:
        title = re.sub(r"\d+", "#", _norm(fg.get("title") or ""))[:60]
        return f"{(fg.get('process') or '?').lower()}|{title}"

    def privacy_block(self, fg: dict) -> str:
        if self._hud_covering():
            return "HUD cobrindo a tela"
        if fg.get("pid") == os.getpid():
            return "JARVIS em foco"
        haystack = _norm(f"{fg.get('process', '')} {fg.get('title', '')}")
        for item in tuple(DEFAULT_EXCLUDED) + tuple(self._excluded() or ()):
            key = _norm(item)
            if key and key in haystack:
                return f"aplicativo excluído: {item}"
        if SENSITIVE_TITLE_RE.search(fg.get("title") or ""):
            return "janela sensível"
        if self.sensitive_until.get(self.context_key(fg), 0) > time.time():
            return "conteúdo sensível visto recentemente"
        return ""

    def sense(self) -> Percept | None:
        fg = self._foreground() or {}
        blocked = self.privacy_block(fg)
        if blocked:
            self.skip_reason = blocked
            with self._lock:
                self._image = None
            self._prev_thumb = None
            return Percept("screen", "visual", {"captured": False, "skipped": blocked,
                                                "context": self.context_key(fg)}, 1.0)
        self.skip_reason = ""
        image = self._capture()
        small = thumb(image)
        changed_vs_analysis = self.analyzed_thumb is None or diff(self.analyzed_thumb, small) > CHANGE_THRESHOLD
        delta = diff(self._prev_thumb, small)
        settled = self._prev_thumb is not None and delta < SETTLED_THRESHOLD
        changed = self._prev_thumb is None or delta > CHANGE_THRESHOLD
        self._prev_thumb = small
        with self._lock:
            self._image = image
            self._image_meta = {"foreground": dict(fg), "thumb": small, "timestamp": time.time(),
                                "context": self.context_key(fg)}
        return Percept("screen", "visual", {
            "captured": True, "changed": changed, "settled": settled, "delta": round(delta, 4),
            "needs_analysis": changed_vs_analysis and settled, "size": list(image.size),
            "context": self.context_key(fg), "application": fg.get("application") or fg.get("process", ""),
        }, 1.0)

    def take_frame(self) -> tuple[Any, dict] | tuple[None, dict]:
        """Entrega a última captura (para a visão) e a descarta da memória."""
        with self._lock:
            image, meta = self._image, dict(self._image_meta)
            self._image = None
        return image, meta

    def mark_sensitive(self, context: str, seconds: float = 600.0) -> None:
        self.sensitive_until[context] = time.time() + seconds

    def capture_now(self) -> tuple[Any, dict]:
        """Captura imediata sob pedido explícito (respeita as mesmas regras de privacidade)."""
        fg = self._foreground() or {}
        blocked = self.privacy_block(fg)
        if blocked:
            raise PermissionError(f"captura recusada: {blocked}")
        return self._capture(), {"foreground": fg, "context": self.context_key(fg), "timestamp": time.time()}
