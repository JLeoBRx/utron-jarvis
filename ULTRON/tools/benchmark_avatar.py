"""Benchmark do avatar holográfico (rosto 3D) e da trilha labial — números MEDIDOS, nada estimado.

    python tools/benchmark_avatar.py                    1280×720 e 1920×1080, todos os perfis
    python tools/benchmark_avatar.py --out avatar.json  grava os números em JSON
    python tools/benchmark_avatar.py --quick            menos quadros (verificação rápida)

Mede, por perfil de qualidade e resolução, o custo do quadro do avatar (animador + renderização com
QPainter na CPU, Qt offscreen) em três estados representativos: EM ESPERA, FALANDO (boca aberta com
a grade de voz) e ESCUTANDO (halo pelo nível do microfone). Mede também o tempo para montar a trilha
labial de 3 s de áudio. Os números valem para a máquina onde o script rodou — registre-a junto.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PySide6 import QtGui, QtWidgets  # noqa: E402

from ultron.hud.avatar.animator import Animator  # noqa: E402
from ultron.hud.avatar.renderer import QUALITY, AvatarRenderer  # noqa: E402
from ultron.hud.avatar.states import AvatarSignals, resolve  # noqa: E402
from ultron.voice.lipsync import LipSyncTrack, Segment  # noqa: E402

SCENARIOS = {
    "em_espera": (dict(booted=True, runtime_state="IDLE"), None, 0.0, 0.0),
    "falando": (dict(booted=True, runtime_state="IDLE", audible=True),
                {"open": 0.7, "wide": 0.3, "round": 0.1, "press": 0.0, "teeth": 0.5, "energy": 0.8}, 0.0, 0.15),
    "escutando": (dict(booted=True, runtime_state="IDLE", listening=True), None, 0.2, 0.0),
}
RESOLUTIONS = ((1280, 720), (1920, 1080))


def measure(width: int, height: int, profile: str, scenario: str, frames: int) -> dict:
    renderer = AvatarRenderer()
    animator = Animator()
    values, mouth, mic, out = SCENARIOS[scenario]
    signals = AvatarSignals(now=time.time(), **values)
    image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
    quality = QUALITY[profile]
    times = []
    for index in range(frames + 8):
        started = time.perf_counter()
        rig = animator.step(1 / 30, resolve(signals), mouth=mouth, mic_level=mic, out_level=out)
        painter = QtGui.QPainter(image)
        renderer.render(painter, width, height, rig, animator.t, quality)
        painter.end()
        if index >= 8:                                     # descarta o aquecimento (caches)
            times.append(time.perf_counter() - started)
    ordered = sorted(times)
    return {"mean_ms": round(statistics.mean(times) * 1000, 2), "p50_ms": round(ordered[len(ordered) // 2] * 1000, 2),
            "p95_ms": round(ordered[int(len(ordered) * 0.95) - 1] * 1000, 2),
            "max_fps_if_alone": round(1.0 / statistics.mean(times), 1), "draw_calls": renderer.last_stats["draw_calls"]}


def lipsync_cost() -> dict:
    rate = 22050
    t = np.arange(int(3.0 * rate)) / rate
    audio = (0.5 * np.sin(2 * np.pi * 180 * t) * (np.sin(2 * np.pi * 2.5 * t) > 0)).astype(np.float32)
    phonemes = list("ˈpa ˈma ˈte ˈso ˈbi ˈlu " * 4)
    started = time.perf_counter()
    for _ in range(20):
        LipSyncTrack(audio, rate, [Segment(0, len(audio), phonemes)])
    return {"track_3s_ms": round((time.perf_counter() - started) / 20 * 1000, 2)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="grava os resultados em JSON")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    frames = 20 if args.quick else 60
    results: dict = {"machine": {"python": platform.python_version(), "system": platform.platform(),
                                 "processor": platform.processor() or platform.machine(),
                                 "cpus": os.cpu_count(), "qt_platform": os.environ.get("QT_QPA_PLATFORM")},
                     "frames_per_case": frames, "render": {}, "lipsync": lipsync_cost()}
    print(f"Avatar — {frames} quadros por caso · {results['machine']['system']}")
    for width, height in RESOLUTIONS:
        for profile in QUALITY:
            for scenario in SCENARIOS:
                value = measure(width, height, profile, scenario, frames)
                results["render"].setdefault(f"{width}x{height}", {}).setdefault(profile, {})[scenario] = value
                print(f"  {width}×{height}  {profile:9s}  {scenario:10s}  média {value['mean_ms']:6.2f} ms  "
                      f"p95 {value['p95_ms']:6.2f} ms  chamadas {value['draw_calls']}")
    print(f"  trilha labial de 3 s: {results['lipsync']['track_3s_ms']} ms")
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"gravado em {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
