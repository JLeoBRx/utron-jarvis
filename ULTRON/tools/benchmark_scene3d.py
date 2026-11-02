"""Mede a central 3D NESTA máquina: quadros por segundo da página (medidos por ela), chamadas de desenho,
triângulos, degrau de qualidade adaptativa e o custo na thread da interface do Python (envio dos sinais).

    python tools/benchmark_scene3d.py                  # 20 s em cada perfil visual, estado "falando"
    python tools/benchmark_scene3d.py --seconds 10 --profiles balanced high

Não inicia o núcleo (sem microfone, rede ou robô) e não grava nada nos dados do JARVIS (pasta temporária).
Os números valem para ESTA máquina e ESTA janela (tamanho padrão 1280×760).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import tempfile
import time

os.environ.setdefault("JARVIS_DATA_DIR", tempfile.mkdtemp(prefix="jarvis-bench3d-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--profiles", nargs="*", default=["economy", "balanced", "high", "cinematic"])
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=760)
    args = parser.parse_args()
    from ultron.hud.scene3d import availability, prepare_qt
    prepare_qt()
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication(sys.argv[:1])
    ok, reason = availability(None, platform_name=app.platformName())
    if not ok:
        print(f"cena 3D indisponível: {reason}")
        return 2
    from ultron.hud.scene3d.view import Scene3DView

    t0 = time.monotonic()

    def mouth():                                   # boca e energia sintéticas, só para manter a cena ativa
        e = abs(math.sin((time.monotonic() - t0) * 7.0))
        return {"open": 0.7 * e, "wide": 0.3, "round": 0.1, "energy": e}

    view = Scene3DView(mouth=mouth, caption=lambda: {"text": "", "progress": 0.0, "active": False},
                       audible=lambda: True)
    view.resize(args.width, args.height)
    view.show()

    def pump(seconds, condition=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents(QtCore.QEventLoop.AllEvents, 10)
            if condition is not None and condition():
                return True
        return False

    pump(90, lambda: view.is_ready or bool(view.failed))
    if not view.is_ready:
        print(f"a cena não abriu: {view.failed or 'sem resposta'}")
        return 3
    print(f"WebGL 2: {view.info.get('renderer')} · three r{view.info.get('three')} · "
          f"{(view.info.get('avatar') or {}).get('vertices')} vértices no holograma")
    view.on_state({"runtime_state": "IDLE", "boot": {"total": 1, "done": 1}, "active_model": "medição"})
    view.on_event("SYSTEM_READY", {})
    results = []
    for profile in args.profiles:
        view.set_profile(profile, effects=profile != "economy")
        view.frame_times.clear()
        samples = []
        end = time.monotonic() + args.seconds
        last = time.perf_counter()
        while time.monotonic() < end:                     # o relógio do controlador: 30 passos por segundo
            now = time.perf_counter()
            view.on_telemetry({"mic_level": 0.0, "out_level": 0.6, "speaking": True})
            view.step(now - last)
            last = now
            pump(1 / 30)
            if view.stats.get("fps"):
                samples.append(dict(view.stats))
        push_ms = [t * 1000 for t in view.frame_times]
        fps = [s["fps"] for s in samples[len(samples) // 3:]] or [0]   # depois da adaptação inicial
        last_stats = samples[-1] if samples else {}
        row = {"perfil": profile, "q/s mediana": statistics.median(fps), "alvo": last_stats.get("target"),
               "redução": last_stats.get("level"), "desenhos": last_stats.get("drawCalls"),
               "triângulos": last_stats.get("triangles"),
               "python ms/passo": round(statistics.mean(push_ms), 3) if push_ms else None}
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), "| última medição:", json.dumps(last_stats, ensure_ascii=False))
    view.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
