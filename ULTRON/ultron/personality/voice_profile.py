"""Perfil de voz do ULTRON.

Masculina, grave, rouca, fria, autoritária, baixa, controlada e lenta. Os parâmetros são
aplicados pelo processamento de sinal em ``ultron/voice/tts.py``:

* ``pitch``: fator de altura (< 1 = mais grave). Também desloca formantes, o que dá
  "corpo" e frieza sintética à voz;
* ``speed``: fator de velocidade final (< 1 = mais lenta);
* ``rasp``: rouquidão (saturação suave + ruído modulado pela envolvente);
* ``depth_db``: reforço de graves (shelf ~160 Hz);
* ``air_cut_hz``: corte de agudos (voz mais escura e controlada);
* ``doubling``: camada sintética levemente desafinada (timbre artificial);
* ``room``: reflexões curtas e escuras.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class VoiceProfile:
    pitch: float = 0.86
    speed: float = 0.9
    rasp: float = 0.22
    depth_db: float = 4.0
    air_cut_hz: float = 6500.0
    doubling: float = 0.16
    room: float = 0.12
    volume: float = 0.9
    sapi_rate: int = 150               # fallback pyttsx3 (palavras/min)
    prefer_male_sapi: bool = True

    def with_user(self, *, volume: float | None = None, speed: float | None = None) -> "VoiceProfile":
        values = asdict(self)
        if volume is not None:
            values["volume"] = max(0.0, min(1.0, float(volume)))
        if speed is not None:
            values["speed"] = max(0.6, min(1.4, float(speed)))
        return VoiceProfile(**values)

    def to_dict(self) -> dict:
        return asdict(self)


ULTRON = VoiceProfile()
NEUTRAL = VoiceProfile(pitch=1.0, speed=1.0, rasp=0.0, depth_db=0.0, air_cut_hz=11000.0,
                       doubling=0.0, room=0.0)
