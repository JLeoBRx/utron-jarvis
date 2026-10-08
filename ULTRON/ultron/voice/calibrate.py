"""Calibração da palavra de ativação.

O reconhecedor pode transcrever "Ultron" de formas diferentes conforme o sotaque e o
microfone ("ultrom", "ul tron"...). A calibração grava algumas repetições, transcreve com
o mesmo modelo usado no dia a dia e acrescenta as formas ouvidas às variantes aceitas.

Uso: ``python -m ultron.voice.calibrate`` (pede para dizer "Ultron" três vezes).
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Callable

from .stt import VoskSTT, choose_model
from .wake_word import _norm, learn_variants

RATE = 16000
CHUNK = 4000


@dataclass
class CalibrationResult:
    transcripts: list[str] = field(default_factory=list)
    variants: tuple = ()
    added: tuple = ()


def transcribe(stt, pcm: bytes) -> str:
    stt.reset()
    pieces = []
    for start in range(0, len(pcm), CHUNK * 2):
        final, _partial = stt.accept(pcm[start:start + CHUNK * 2])
        if final:
            pieces.append(final)
    tail = stt.finish()
    if tail:
        pieces.append(tail)
    stt.reset()
    return " ".join(pieces).strip()


def calibrate(stt, recordings: list[bytes], known: tuple) -> CalibrationResult:
    transcripts = [t for t in (transcribe(stt, pcm) for pcm in recordings) if t]
    variants = learn_variants(transcripts, tuple(known))
    added = tuple(v for v in variants if v not in {_norm(k) for k in known} and v not in known)
    return CalibrationResult(transcripts, variants, added)


def record_microphone(seconds: float, *, name_hint: str = "", index: int = -1) -> bytes:
    from .audio import open_microphone
    audio, stream, _name = open_microphone(rate=RATE, chunk=CHUNK, name_hint=name_hint, index=index)
    try:
        frames = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            frames.append(stream.read(CHUNK, exception_on_overflow=False))
        return b"".join(frames)
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()


def main(argv: list[str] | None = None, *, recorder: Callable[[float], bytes] | None = None) -> int:
    from ..config import settings as settings_module

    argv = list(sys.argv[1:] if argv is None else argv)
    repetitions = int(argv[0]) if argv and argv[0].isdigit() else 3
    manager = settings_module.manager()
    s = manager.settings
    path, reason = choose_model(s.stt_engine)
    if path is None:
        print(f"Calibração indisponível: {reason}.")
        return 1
    stt = VoskSTT(path, RATE)
    record = recorder or (lambda secs: record_microphone(secs, name_hint=s.mic_name, index=s.mic_index))
    recordings = []
    for number in range(1, repetitions + 1):
        input(f"[{number}/{repetitions}] Pressione Enter e diga apenas \"Ultron\".")
        recordings.append(record(2.5))
    result = calibrate(stt, recordings, tuple(s.wake_variants))
    print("Ouvido:", "; ".join(result.transcripts) or "(nada reconhecido)")
    if result.added:
        manager.update(wake_variants=list(result.variants))
        print("Variantes adicionadas:", ", ".join(result.added))
    else:
        print("Nenhuma variante nova. As formas atuais já cobrem a sua pronúncia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
