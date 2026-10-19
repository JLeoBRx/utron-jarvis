"""Calibração da palavra de ativação "Jarvis".

O reconhecedor transcreve "Jarvis" de formas diferentes conforme o sotaque e o microfone
("jarvis", "jarbas", "aviso", "já vi"…). A calibração ouve algumas repetições com o MESMO
modelo usado no dia a dia e acrescenta as formas ouvidas: próximas de "jarvis" e que não são
palavras comuns viram formas fortes; confusões repetidas com palavras comuns viram formas
fracas (só ativam seguidas de um comando reconhecido).

Uso: ``python -m ultron.voice.calibrate`` (pede para dizer "Jarvis" três vezes) ou, com o
JARVIS aberto, HUB > Voz > Calibrar (usa a captura já aberta, sem um segundo microfone).
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Callable

from .stt import VoskSTT, choose_model
from .wake_word import _norm, learn_variants, learn_weak_variants

RATE = 16000
CHUNK = 4000


@dataclass
class CalibrationResult:
    transcripts: list[str] = field(default_factory=list)
    variants: tuple = ()
    added: tuple = ()
    weak: tuple = ()
    weak_added: tuple = ()


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


def learn(transcripts: list[str], known: tuple, known_weak: tuple = ()) -> CalibrationResult:
    variants = learn_variants(transcripts, tuple(known))
    added = tuple(v for v in variants if v not in {_norm(k) for k in known} and v not in known)
    weak = learn_weak_variants(transcripts, variants, tuple(known_weak))
    weak_added = tuple(w for w in weak if w not in known_weak)
    return CalibrationResult(list(transcripts), variants, added, weak, weak_added)


def calibrate(stt, recordings: list[bytes], known: tuple, known_weak: tuple = ()) -> CalibrationResult:
    transcripts = [t for t in (transcribe(stt, pcm) for pcm in recordings) if t]
    return learn(transcripts, known, known_weak)


def calibrate_live(core, *, repetitions: int = 3, seconds: float = 4.0,
                   prompt: Callable[[str], None] | None = None, cancel=None) -> CalibrationResult:
    """Calibração com o JARVIS aberto: usa a captura em andamento (diagnostic_tap), sem abrir outro
    fluxo de microfone. Grava as formas aprendidas nas configurações."""
    import queue
    pipeline = core.voice
    if not pipeline.capturing or pipeline.stt is None:
        raise RuntimeError(pipeline.reason or pipeline.stt_reason or "captura de voz indisponível")
    heard: queue.Queue = queue.Queue()
    transcripts: list[str] = []
    pipeline.diagnostic_tap = lambda kind, data: heard.put(data.get("text", "")) if kind == "final" else None
    try:
        for number in range(1, repetitions + 1):
            if cancel is not None and getattr(cancel, "cancelled", False):
                break
            if prompt:
                prompt(f"[{number}/{repetitions}] Diga apenas \"Jarvis\".")
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                try:
                    text = heard.get(timeout=0.2)
                except queue.Empty:
                    continue
                if text:
                    transcripts.append(text)
                    break
    finally:
        pipeline.diagnostic_tap = None
    s = core.settings()
    result = learn(transcripts, tuple(s.wake_variants), tuple(s.wake_weak_variants))
    if result.added or result.weak_added:
        core.settings_manager.update(wake_variants=list(result.variants), wake_weak_variants=list(result.weak))
    return result


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
        input(f"[{number}/{repetitions}] Pressione Enter e diga apenas \"Jarvis\".")
        recordings.append(record(2.5))
    result = calibrate(stt, recordings, tuple(s.wake_variants), tuple(s.wake_weak_variants))
    print("Ouvido:", "; ".join(result.transcripts) or "(nada reconhecido)")
    if result.added or result.weak_added:
        manager.update(wake_variants=list(result.variants), wake_weak_variants=list(result.weak))
        if result.added:
            print("Formas fortes adicionadas:", ", ".join(result.added))
        if result.weak_added:
            print("Formas fracas adicionadas (exigem comando):", ", ".join(result.weak_added))
    else:
        print("Nenhuma forma nova. As formas atuais já cobrem a sua pronúncia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
