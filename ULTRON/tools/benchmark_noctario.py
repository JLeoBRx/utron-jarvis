"""Benchmark do Noctário no PC — números MEDIDOS com o SIMULADOR (não é Bluetooth nem o robô real).

    python tools/benchmark_noctario.py                   todas as medidas
    python tools/benchmark_noctario.py --out noct.json   grava os números em JSON
    python tools/benchmark_noctario.py --quick           menos repetições

Mede o lado do PC: ida e volta de um comando (PING) e da PARADA DE EMERGÊNCIA até o ESTOP confirmado,
pelo serviço real e o transporte do simulador (o simulador processa em lotes de 10 ms, então os tempos
incluem essa espera — no robô real entra a latência do Bluetooth, que este script NÃO mede); o custo da
página NOCTÁRIO com telemetria chegando (atualização dos valores e pintura do gráfico, Qt offscreen, CPU)
e o espaço que uma volta inteira ocupa no banco. Os números valem para a máquina onde o script rodou.
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

from ultron.config.settings import Settings  # noqa: E402
from ultron.memory.store import Database  # noqa: E402
from ultron.noctario.service import NoctarioService  # noqa: E402
from ultron.noctario.simulator import NoctarioSimulator  # noqa: E402
from ultron.noctario.transport import SimulatorTransport  # noqa: E402


def _stats(times: list[float]) -> dict:
    ordered = sorted(times)
    return {"n": len(ordered), "mean_ms": round(statistics.fmean(ordered) * 1000, 2),
            "p50_ms": round(ordered[len(ordered) // 2] * 1000, 2),
            "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1000, 2),
            "max_ms": round(ordered[-1] * 1000, 2)}


def _service(speed: float) -> tuple[NoctarioService, NoctarioSimulator]:
    settings = Settings()
    settings.apply({"noctario_transport": "simulator"}, source="benchmark")
    sim = NoctarioSimulator(speed=speed, seed=2)
    service = NoctarioService(lambda: settings, db=Database(Path(_TMP) / "bench.sqlite3"),
                              transport_factory=lambda: SimulatorTransport(sim))
    if not service.connect(timeout=5.0)["ok"]:
        raise SystemExit("o simulador não respondeu")
    return service, sim


def _ready(service: NoctarioService) -> None:
    if service.confirmed.get("state") == "ESTOP":
        service.clear()
    if not service.wait_confirmed({"READY", "STOP", "DONE"}, 0.1):
        service.calibrate(ms=1000)
        if not service.wait_confirmed({"READY"}, 10):
            raise SystemExit("calibração do simulador não terminou")


def measure_commands(repeats: int) -> dict:
    service, sim = _service(speed=1.0)
    try:
        pings = []
        for _ in range(repeats):
            started = time.perf_counter()
            result = service.command("PING")
            if result.ok:
                pings.append(time.perf_counter() - started)
        estops = []
        for _ in range(max(3, repeats // 5)):
            _ready(service)
            if not service.start_run().ok:
                raise SystemExit("o simulador recusou a partida")
            time.sleep(0.2)
            started = time.perf_counter()
            service.estop(origin="benchmark")
            while service.confirmed.get("state") != "ESTOP" and time.perf_counter() - started < 2.0:
                time.sleep(0.001)                          # 1 ms de resolução (wait_confirmed olha a cada 20 ms)
            if service.confirmed.get("state") == "ESTOP":
                estops.append(time.perf_counter() - started)
        return {"ping_round_trip": _stats(pings), "estop_until_confirmed": _stats(estops)}
    finally:
        service.disconnect(quiet=True)
        sim.close()


def measure_lap() -> dict:
    service, sim = _service(speed=25.0)
    try:
        _ready(service)
        started = time.perf_counter()
        service.start_run()
        if not service.wait_confirmed({"DONE"}, 30):
            raise SystemExit("a volta simulada não terminou")
        wall = time.perf_counter() - started
        end = time.monotonic() + 2
        while service.last_run is None and time.monotonic() < end:
            time.sleep(0.02)
        row = service.store.db.query("SELECT length(samples) AS size FROM noctario_runs ORDER BY started DESC "
                                     "LIMIT 1")[0]
        run = service.store.runs(1)[0]
        return {"lap_simulated_s": run["duration_s"], "lap_wall_s_at_25x": round(wall, 2),
                "samples": len(run["samples"]), "telemetry_hz": service.params.get("tel"),
                "stored_bytes": row["size"], "crossings": len(run["crossings"])}
    finally:
        service.disconnect(quiet=True)
        sim.close()


def measure_page(frames: int) -> dict:
    from PySide6 import QtWidgets

    from ultron.hud.noctario_page import NoctarioPage

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    service, sim = _service(speed=1.0)

    class Core:
        noctario = service
        tardis = None

        def run_skill(self, *args, **kwargs):
            return {}

    try:
        _ready(service)
        service.start_run()
        page = NoctarioPage(Core())
        page.resize(1440, 860)
        page.show()
        deadline = time.monotonic() + 30                   # janela cheia: 20 s de telemetria a 20 Hz
        while len(service.recent_series(page.graph.window)) < 380 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        refresh, paint = [], []
        for _ in range(frames):
            app.processEvents()
            started = time.perf_counter()
            page.refresh()
            refresh.append(time.perf_counter() - started)
            started = time.perf_counter()
            page.graph.grab()
            paint.append(time.perf_counter() - started)
        samples = len(page.graph.samples)
        page.shutdown()
        page.close()
        return {"size": "1440x860", "graph_samples": samples, "refresh": _stats(refresh), "graph_paint": _stats(paint),
                "refresh_hz_connected": 20}
    finally:
        service.disconnect(quiet=True)
        sim.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="arquivo JSON para os resultados")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    repeats, frames = (15, 40) if args.quick else (50, 150)
    result = {"what": "SIMULADOR no PC — não é Bluetooth nem o robô real",
              "machine": {"python": platform.python_version(), "system": platform.platform(),
                          "cpu": platform.processor() or platform.machine(), "cpus": os.cpu_count()},
              "commands": measure_commands(repeats), "lap": measure_lap(), "page": measure_page(frames)}
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
