"""Benchmark reproduzível do ULTRON (HUB e núcleo), para comparar versões nas mesmas condições.

    python tools/benchmark.py                       mede esta árvore
    python tools/benchmark.py --root CAMINHO        mede outra cópia do projeto (ex.: versão anterior)
    python tools/benchmark.py --out resultado.json  grava os números em JSON
    python tools/benchmark.py --quick               menos quadros/segundos (verificação rápida)

Tudo roda isolado: pasta de dados temporária, Ollama simulado por HTTP local
(``tests/fake_ollama.py``), sem microfone e sem tocar nos dados reais do usuário.
Requer PySide6 (renderização offscreen). Mede:

* ``render``: custo por quadro da cena + desenho do cérebro (1320×820) em cenários fixos;
* ``ui``: atraso do laço de eventos da interface, quadros por segundo, CPU e tempo gasto na
  thread da interface com o Core real em repouso e em atividade;
* ``core``: cópia do estado central, snapshot do grafo e latência de resposta (com o tempo
  de inferência simulado separado).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _setup_paths(root: Path) -> None:
    os.environ["ULTRON_DATA_DIR"] = tempfile.mkdtemp(prefix="ultron-bench-")
    os.environ["HOME"] = os.environ["USERPROFILE"] = tempfile.mkdtemp(prefix="ultron-bench-home-")
    for path in (root, root / "tests"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)

    def pct(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]

    return {"n": len(values), "mean": statistics.fmean(values), "p50": pct(50), "p95": pct(95), "p99": pct(99),
            "max": ordered[-1]}


def _ms(stats: dict[str, float]) -> dict[str, float]:
    return {k: (round(v * 1000, 3) if k != "n" else v) for k, v in stats.items()}


# ------------------------------------------------------------------ cenários da cena
TYPES = ("MEMORY", "IDEA", "CONCEPT", "SKILL", "PROJECT", "WORLD", "SCENARIO", "DEVICE", "APPLICATION")
COMPONENTS = ("privacy", "memory", "world_model", "models", "goals", "network", "skills", "agent", "imagination",
              "voice_output", "neural_audio", "voice", "perception", "proactive", "plugins", "health")


def _graph(n_nodes: int, seed: int = 7) -> dict:
    rng = random.Random(seed)
    nodes = [{"id": f"{t.lower()}:{i}", "type": t, "label": f"{t} {i}", "strength": rng.random()}
             for i, t in enumerate(rng.choices(TYPES, k=n_nodes))]
    edges = []
    for _ in range(n_nodes * 2):
        a, b = rng.sample(nodes, 2)
        edges.append({"src": a["id"], "dst": b["id"], "type": "RELATED", "weight": rng.random()})
    return {"nodes": nodes, "edges": edges, "total_nodes": len(nodes), "total_edges": len(edges)}


def bench_render(frames: int) -> dict:
    from PySide6 import QtGui, QtWidgets

    from ultron.hud.brain_view import BrainView
    from ultron.hud.scene import NeuralScene

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    results = {}
    plan = {"steps": [{"id": f"s{i}", "description": f"etapa {i}", "status": "DONE" if i < 3 else "PENDING"}
                      for i in range(10)]}
    scenarios = {
        "idle_young": (0, "IDLE"),
        "idle_mature": (800, "IDLE"),
        "active_mature": (800, "EXECUTING"),
        "camera_moves": (400, "CYCLE"),
    }
    for name, (n_nodes, runtime) in scenarios.items():
        clock = [1000.0]
        scene = NeuralScene(clock=lambda: clock[0])
        graph = _graph(n_nodes)
        scene.load_graph(graph)
        for component in COMPONENTS:
            scene.on_event("COMPONENT_STARTED", {"component": component})
        state = {"runtime_state": "IDLE" if runtime == "CYCLE" else runtime, "privacy": {"local_mode": True},
                 "active_model": "qwen2.5:3b"}
        if runtime == "EXECUTING":
            state["current_plan"] = plan
        scene.on_state(state)
        view = BrainView(scene)
        view.resize(1320, 820)
        image = QtGui.QImage(view.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
        rng = random.Random(3)
        ids = [n["id"] for n in graph["nodes"]]
        cycle = ("LISTENING", "THINKING", "EXECUTING", "SPEAKING", "IDLE")
        times = []
        for frame in range(frames + 30):
            clock[0] += 1 / 60
            if runtime == "EXECUTING" and frame % 20 == 0:
                scene.on_event("ACTION_STARTED", {"skill": "fs.list"})
                if ids:
                    scene.on_event("GRAPH_ACTIVATED", {"ids": rng.sample(ids, min(24, len(ids)))})
            if runtime == "CYCLE" and frame % 90 == 0:
                scene.on_state({**state, "runtime_state": cycle[(frame // 90) % len(cycle)]})
            started = time.perf_counter()
            scene.step(1 / 60)
            view.render(image)
            if frame >= 30:
                times.append(time.perf_counter() - started)
        results[name] = _ms(_stats(times))
        results[name]["over_16ms"] = sum(1 for t in times if t > 1 / 60)
    return results


# ------------------------------------------------------------------ interface com o Core real
def _timed(cls, name: str, sink: dict) -> None:
    original = getattr(cls, name)

    def wrapper(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            sink.setdefault(name, []).append(time.perf_counter() - started)

    wrapper.__name__ = name
    setattr(cls, name, wrapper)


def bench_ui(seconds: float) -> dict:
    import psutil
    from PySide6 import QtCore, QtWidgets

    from fake_ollama import FakeOllama
    from ultron.config.settings import SettingsManager
    from ultron.core.neural_core import NeuralCore
    from ultron.hud import controller as controller_module
    from ultron.hud.brain_view import BrainView

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ui_time: dict[str, list[float]] = {}
    for name in ("_pull_state", "_pull_telemetry", "_on_event", "_tick"):
        if hasattr(controller_module.HudController, name):
            _timed(controller_module.HudController, name, ui_time)
    _timed(BrainView, "paintEvent", ui_time)

    def responder(payload):
        time.sleep(0.25)                             # inferência simulada fixa (separada no relatório)
        return "Entropia mede a dispersão de energia de um sistema."

    out = {}
    with FakeOllama(["qwen2.5:3b", "qwen2.5vl:3b"], responder=responder) as fake:
        manager = SettingsManager()
        manager.load()
        manager.settings.ollama_url = fake.url
        manager.settings.network_discovery = False
        core = NeuralCore(manager, voice=False, perception=True, plugins=False)
        for i in range(120):                           # memória prévia: o grafo tem corpo
            core.memory.remember_fact(f"projeto {i}", f"usa a biblioteca {i % 17} e roda no servidor {i % 9}")
        ctrl = controller_module.HudController(core)
        ctrl.window.resize(1320, 820)
        ctrl.show()
        proc = psutil.Process()

        def pump(duration: float) -> dict:
            lags: list[float] = []
            last = [time.perf_counter()]

            def beat() -> None:
                now = time.perf_counter()
                lags.append(max(0.0, now - last[0] - 0.005))
                last[0] = now

            timer = QtCore.QTimer()
            timer.setTimerType(QtCore.Qt.PreciseTimer)
            timer.timeout.connect(beat)
            timer.start(5)
            for values in ui_time.values():
                values.clear()
            proc.cpu_percent(None)
            ticks_before = len(ui_time.get("_tick", []))
            started = time.perf_counter()
            while time.perf_counter() - started < duration:
                app.processEvents(QtCore.QEventLoop.AllEvents, 5)
                time.sleep(0.001)
            elapsed = time.perf_counter() - started
            cpu = proc.cpu_percent(None)
            timer.stop()
            busy = {k: round(sum(v) / elapsed * 1000, 2) for k, v in ui_time.items()}       # ms por segundo
            return {"event_loop_lag": _ms(_stats(lags)), "cpu_percent": round(cpu, 1),
                    "rss_mb": round(proc.memory_info().rss / 2 ** 20, 1),
                    "ticks_per_s": round((len(ui_time.get("_tick", [])) - ticks_before) / elapsed, 1),
                    "paints_per_s": round(len(ui_time.get("paintEvent", [])) / elapsed, 1),
                    "paint_ms": _ms(_stats(ui_time.get("paintEvent", []))),
                    "ui_busy_ms_per_s": busy,
                    "threads": threading.active_count()}

        threading.Thread(target=core.boot, daemon=True).start()
        deadline = time.time() + 30
        while not core.booted and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        settle = time.perf_counter()
        while time.perf_counter() - settle < 3.0:      # fim da sequência de inicialização
            app.processEvents()
            time.sleep(0.005)
        out["idle"] = pump(seconds)
        settle = time.perf_counter()
        while time.perf_counter() - settle < 8.0:      # repouso estável (sem a acomodação pós-boot)
            app.processEvents()
            time.sleep(0.005)
        out["idle_steady"] = pump(seconds)

        latencies: list[float] = []
        done = threading.Event()

        def on_response(event) -> None:
            if not event.payload.get("partial"):
                done.set()

        from ultron.core.events import EventType
        core.bus.subscribe(EventType.RESPONSE_READY, on_response, name="bench")

        def activity() -> None:
            requests = ["o que é entropia?", "lembre que o projeto Atlas usa Flask", "o que é entropia?",
                        "lembre que o servidor de testes fica na sala 3", "o que é entropia?"]
            for text in requests:
                done.clear()
                started = time.perf_counter()
                core.submit(text, source="text")
                if done.wait(20):
                    latencies.append(time.perf_counter() - started)
            for i in range(80):                        # crescimento do grafo durante o uso
                core.memory.remember_fact(f"nota {i}", f"ideia sobre o módulo {i % 11} do projeto {i % 5}")
                time.sleep(0.02)

        worker = threading.Thread(target=activity, daemon=True)
        worker.start()
        out["busy"] = pump(seconds)
        worker.join(30)
        out["response_latency"] = _ms(_stats(latencies))
        out["simulated_inference_ms"] = 250.0
        threads_before_shutdown = threading.active_count()
        ctrl.quit() if hasattr(ctrl, "quit") else None
        core.shutdown()
        time.sleep(1.0)
        out["threads_before_shutdown"] = threads_before_shutdown
        out["threads_after_shutdown"] = threading.active_count()
        out["threads_left"] = sorted(t.name for t in threading.enumerate() if t is not threading.main_thread())
    return out


# ------------------------------------------------------------------ custos do núcleo
def bench_core(repeats: int) -> dict:
    from ultron.core.event_bus import EventBus
    from ultron.core.state import StateStore
    from ultron.graph.neural_graph import NeuralGraph
    from ultron.memory.store import Database

    out = {}
    state = StateStore(EventBus())
    plan = {"id": "p", "steps": [{"id": f"s{i}", "description": "etapa " * 8, "status": "PENDING",
                                  "result": {"result": "x" * 600}} for i in range(10)]}
    state.update(current_plan=plan, network_state={"devices_online": 12, "dns": ["1.1.1.1"] * 3},
                 privacy={"external_log": [{"host": "x", "at": 1.0}] * 30, "decisions": [{"a": "b" * 80}] * 20},
                 world_model={"entities": {f"k{i}": {"v": "x" * 40} for i in range(120)}},
                 health={"checks": {f"C{i}": {"status": "OK", "detail": "d" * 40} for i in range(12)}})
    times = []
    for _ in range(repeats):
        started = time.perf_counter()
        state.as_dict()
        times.append(time.perf_counter() - started)
    out["state_as_dict"] = _ms(_stats(times))
    db = Database(Path(tempfile.mkdtemp(prefix="ultron-bench-db-")) / "bench.sqlite3")
    graph = NeuralGraph(db, None)
    rng = random.Random(5)
    ids = []
    for i in range(2000):
        ids.append(graph.add_node(rng.choice(TYPES), f"item {i}").id)
    for _ in range(4000):
        a, b = rng.sample(ids, 2)
        try:
            graph.connect(a, b, "RELATED")
        except (ValueError, KeyError):
            pass
    times = []
    for _ in range(max(3, repeats // 20)):
        started = time.perf_counter()
        graph.snapshot(max_nodes=800)
        times.append(time.perf_counter() - started)
    out["graph_snapshot_800"] = _ms(_stats(times))
    db.close()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--out", default="")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--only", choices=("render", "ui", "core"), action="append")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    _setup_paths(root)
    import logging
    logging.basicConfig(level=logging.ERROR)
    from ultron import __version__
    parts = args.only or ["render", "core", "ui"]
    report = {"root": str(root), "version": __version__, "python": platform.python_version(),
              "platform": f"{platform.system()} {platform.release()}", "cpus": os.cpu_count(),
              "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    if "render" in parts:
        report["render"] = bench_render(120 if args.quick else 600)
    if "core" in parts:
        report["core"] = bench_core(50 if args.quick else 400)
    if "ui" in parts:
        report["ui"] = bench_ui(4.0 if args.quick else 12.0)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    os._exit(0)                                        # threads daemon de terceiros não seguram o processo


if __name__ == "__main__":
    raise SystemExit(main())
