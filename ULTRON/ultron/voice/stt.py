"""STT — reconhecimento de fala offline (Vosk).

Seleção do modelo (``stt_engine``):

* ``auto``: modelo grande ``vosk-model-pt-fb`` (verificado: funciona sem HCLG/G.carpa, em modo
  lookahead; muito mais preciso e o único com "ultron" no vocabulário) se houver RAM
  suficiente; senão o pequeno;
* ``vosk-large`` / ``vosk-small``: força um deles.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import paths

log = logging.getLogger("ultron.stt")

LARGE = "vosk-model-pt-fb-v0.1.1-20220516_2113"
SMALL = "vosk-model-small-pt-0.3"


def _ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / 1024 ** 3
    except Exception:
        return 0.0


def choose_model(engine: str = "auto") -> tuple[Path | None, str]:
    base = paths.stt_models_dir()
    large, small = base / LARGE, base / SMALL
    large_ok = (large / "am" / "final.mdl").is_file() and (large / "graph" / "HCLr.fst").is_file()
    small_ok = (small / "final.mdl").is_file()
    if engine == "vosk-large":
        return (large, "") if large_ok else (None, f"modelo {LARGE} ausente")
    if engine == "vosk-small":
        return (small, "") if small_ok else (None, f"modelo {SMALL} ausente")
    if large_ok and (_ram_gb() == 0.0 or _ram_gb() >= 6.0):
        return large, ""
    if small_ok:
        return small, ""
    return None, "nenhum modelo Vosk encontrado em assets/stt"


class VoskSTT:
    name = "vosk"

    def __init__(self, model_path: Path, rate: int = 16000):
        import vosk
        vosk.SetLogLevel(-1)
        self.model_path = model_path
        self.rate = rate
        self._model = vosk.Model(str(model_path))
        self._vosk = vosk
        self.recognizer = self._new()
        self.last_confidence = 0.0
        self.last_words: list[dict] = []

    def _new(self):
        recognizer = self._vosk.KaldiRecognizer(self._model, self.rate)
        try:
            recognizer.SetWords(True)
        except Exception:
            pass
        return recognizer

    @property
    def label(self) -> str:
        return "vosk-large" if LARGE in str(self.model_path) else "vosk-small"

    def _final(self, raw: str) -> str:
        result = json.loads(raw or "{}")
        self.last_words = [w for w in result.get("result", []) if isinstance(w, dict)]
        confs = [float(w.get("conf", 0.0)) for w in self.last_words]
        self.last_confidence = round(sum(confs) / len(confs), 3) if confs else 0.0
        return (result.get("text") or "").strip()

    def accept(self, chunk: bytes) -> tuple[str | None, str | None]:
        """Devolve (texto final, texto parcial). A confiança média do texto final fica em
        ``last_confidence`` (0..1, por palavra, do próprio reconhecedor)."""
        if self.recognizer.AcceptWaveform(chunk):
            return self._final(self.recognizer.Result()) or None, None
        partial = json.loads(self.recognizer.PartialResult() or "{}").get("partial", "").strip()
        return None, partial or None

    def finish(self) -> str:
        return self._final(self.recognizer.FinalResult())

    def reset(self) -> None:
        self.recognizer.Reset()
