"""Benchmark da TARDIS — sala de controle e motor — com números MEDIDOS, nada estimado.

    python tools/benchmark_tardis_room.py                  1280×720 e 1920×1080, todos os perfis
    python tools/benchmark_tardis_room.py --out sala.json   grava os números em JSON
    python tools/benchmark_tardis_room.py --quick           menos quadros (verificação rápida)

Mede, por perfil e resolução, o custo do quadro da sala (QPainter na CPU, Qt offscreen) em quatro modos
do rotor (repouso, processando, consulta do JARVIS, falha) com a câmera parada — paredes, piso e console
vêm do cache — e durante a volta da câmera até um painel (camadas refeitas a cada quadro). Mede também
a sobrecarga do motor (fila, thread, banco e histórico) com um analisador que não faz nada. Os números
valem para a máquina onde o script rodou — registre-a junto.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="ultron-bench-")
os.environ.setdefault("ULTRON_DATA_DIR", _TMP)

from PySide6 import QtGui, QtWidgets  # noqa: E402

from ultron.hud.tardis_room.scene import RoomScene  # noqa: E402
from ultron.hud.tardis_room.view import QUALITY, RoomRenderer  # noqa: E402

MODES = {
    "repouso": {"mode": "repouso"},
    "processando": {"mode": "processando", "queued": 1, "running": {"kind_label": "planejamento"}},
    "consulta_jarvis": {"mode": "jarvis", "running": {"kind_label": "consulta contextual"}},
    "falha": {"mode": "falha", "fault": True, "fault_text": "consulta contextual: nada encontrado"},
}
RESOLUTIONS = ((1280, 720), (1920, 1080))
SCREENS = {"left": ("FILA", ["1 na fila", "executando: planejamento", "última hora: 3 concluída(s), 0 falha(s)"],
                    (255, 179, 71)),
           "right": ("ÚLTIMA: ORGANIZAÇÃO", ["concluída", "1 grupo de duplicados e 2 tarefas sem data."],
                     (220, 238, 255))}


def _stats(times: list[float]) -> dict:
    ordered = sorted(times)
    mean = statistics.fmean(ordered)
    return {"mean_ms": round(mean * 1000, 2), "p50_ms": round(ordered[len(ordered) // 2] * 1000, 2),
            "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1000, 2),
            "max_fps_if_alone": round(1.0 / mean, 1) if mean else None}


def measure(width: int, height: int, profile: str, mode: str, frames: int, *, moving: bool = False) -> dict:
    scene = RoomScene()
    quality = QUALITY[profile]
    effects = profile != "economy"
    scene.set_motes(quality.motes if effects else 0)
    scene.set_engine_state(MODES[mode])
    scene.screens = dict(SCREENS)
    if mode == "processando":
        scene.task_event("TARDIS_TASK_STARTED", {"kind": "planejamento"})
    renderer = RoomRenderer()
    image = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
    times = []
    for index in range(frames + 6):
        if moving and index == 6:
            scene.select("telemetria")                     # a câmera gira até o painel (~1 s)
        scene.step(1 / 30)
        started = time.perf_counter()
        painter = QtGui.QPainter(image)
        renderer.render(painter, width, height, scene, quality=quality, effects=effects)
        painter.end()
        if index >= 6:                                    # descarta o aquecimento (caches)
            times.append(time.perf_counter() - started)
    return _stats(times)


def engine_overhead(tasks: int) -> dict:
    """Ida e volta de uma tarefa (fila → thread → analisador vazio → banco → histórico → evento)."""
    from ultron.core.activity import ActivityLog
    from ultron.memory.store import Database
    from ultron.tardis.engine import TardisEngine
    from ultron.tardis.protocol import TaskResult
    from ultron.tardis.store import TardisStore

    db = Database(Path(_TMP) / "bench.sqlite3")
    engine = TardisEngine(TardisStore(db), activity=ActivityLog(db),
                          analyzers={"coordenacao": lambda run, data: TaskResult("ok")})
    engine.start()
    times = []
    try:
        for _ in range(tasks):
            started = time.perf_counter()
            task = engine.request("coordenacao", {})
            times.append(time.perf_counter() - started)
            assert task.state == "DONE", task.error
    finally:
        engine.stop()
        db.close()
    return _stats(times)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", help="arquivo JSON de saída")
    parser.add_argument("--quick", action="store_true", help="menos quadros")
    args = parser.parse_args()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    frames = 15 if args.quick else 45
    report = {"machine": {"python": platform.python_version(), "system": platform.platform(),
                          "processor": platform.machine(), "cpus": os.cpu_count(),
                          "qt_platform": os.environ.get("QT_QPA_PLATFORM", "")},
              "frames_per_case": frames, "render": {}, "camera_turn": {}}
    for width, height in RESOLUTIONS:
        key = f"{width}x{height}"
        report["render"][key] = {}
        report["camera_turn"][key] = {}
        for profile in QUALITY:
            report["render"][key][profile] = {mode: measure(width, height, profile, mode, frames) for mode in MODES}
            report["camera_turn"][key][profile] = measure(width, height, profile, "repouso", min(frames, 30),
                                                          moving=True)
            line = " · ".join(f"{mode} {values['p50_ms']} ms" for mode, values in report["render"][key][profile].items())
            print(f"{key} {profile:10} {line} · câmera girando {report['camera_turn'][key][profile]['p50_ms']} ms")
    report["engine_round_trip"] = engine_overhead(20 if args.quick else 100)
    print(f"motor: ida e volta de uma tarefa vazia {report['engine_round_trip']['p50_ms']} ms (mediana)")
    del app
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"gravado em {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
