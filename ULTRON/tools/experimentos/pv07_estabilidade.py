"""PV-07 — Estabilidade em execução prolongada.

Mantém o MESMO ``NeuralCore`` rodando por ``--minutos`` (padrão: 480 = 8 h, a meta RNF10), enviando um ciclo de
pedidos a cada ``--intervalo`` segundos (horas, anotação e consulta na memória pessoal, estado do sistema e
uma pergunta ao modelo), e amostra a cada minuto: memória do processo (RSS), número de threads, eventos
descartados pelo Event Bus e pedidos sem resposta. No fim, encerra o núcleo e confere se sobrou thread.

Métricas: falhas fatais, pedidos sem resposta, crescimento de memória (MB/h, regressão linear sobre as
amostras), threads restantes após o encerramento. Sem ``--ollama``, as perguntas usam um servidor local que
responde na hora (a inferência real não entra na medida).

Uso:  python tools/experimentos/pv07_estabilidade.py --minutos 480 [--ollama URL] [--rotulo NOME]
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum as C  # noqa: E402

CICLO = ("que horas são", "anote uma ideia: teste de estabilidade", "liste minhas ideias", "status do sistema",
         "explique em uma frase o que é um algoritmo")


def _inclinacao(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return None if den == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


AQUECIMENTO_MIN = 5.0     # caches, banco e módulos importados sob demanda enchem nos primeiros minutos


def crescimento(amostras: list[dict]) -> dict:
    """Inclinação da memória (MB/h): na série inteira e DEPOIS do aquecimento (sem os 5 minutos iniciais ou os
    primeiros 10 % da execução, o que for maior). A meta RNF10 é avaliada pela segunda."""
    xs = [a["t_min"] / 60 for a in amostras]
    ys = [a["rss_mb"] for a in amostras]
    corte = max(AQUECIMENTO_MIN, 0.1 * (amostras[-1]["t_min"] if amostras else 0))
    estavel = [(a["t_min"] / 60, a["rss_mb"]) for a in amostras if a["t_min"] >= corte]
    total = _inclinacao(xs, ys)
    depois = _inclinacao([x for x, _ in estavel], [y for _, y in estavel])
    return {"rss_inicial_mb": ys[0] if ys else None, "rss_final_mb": ys[-1] if ys else None,
            "aquecimento_min": corte,
            "crescimento_mb_por_hora": None if total is None else round(total, 2),
            "crescimento_mb_por_hora_apos_aquecimento": None if depois is None else round(depois, 2)}


def main() -> int:
    args = C.argumentos(__doc__.splitlines()[0], extra=lambda p: (
        p.add_argument("--minutos", type=float, default=480.0),
        p.add_argument("--intervalo", type=float, default=5.0),
        p.add_argument("--ollama", default=""), p.add_argument("--modelo", default="qwen2.5:3b")))
    C.preparar()
    import psutil
    from fake_ollama import FakeOllama
    from ultron.config import paths
    from ultron.config.settings import SettingsManager
    from ultron.core.events import EventType
    from ultron.core.neural_core import NeuralCore
    falso = None if args.ollama else FakeOllama([args.modelo], responder=lambda p: "Resposta simulada.").__enter__()
    gerente = SettingsManager(paths.data_file("settings.json"))
    gerente.load()
    gerente.settings.apply({"ollama_url": args.ollama or falso.url, "model": args.modelo, "network_discovery": False,
                            "auto_backup": False, "voice_enabled": False, "ollama_autostart": False})
    antes = {t.ident for t in threading.enumerate()}
    core = NeuralCore(gerente, voice=False, perception=False, plugins=False)
    core.boot()
    processo = psutil.Process()
    respostas = {"n": 0}
    core.bus.subscribe(EventType.RESPONSE_READY,
                       lambda e: respostas.__setitem__("n", respostas["n"] + (0 if e.payload.get("partial") else 1)),
                       name="pv07")
    minutos = 1.0 if args.rapido else args.minutos
    fim = time.monotonic() + minutos * 60
    amostras, enviados, erros = [], 0, []
    proxima_amostra = time.monotonic()
    inicio = time.monotonic()
    while time.monotonic() < fim:
        for texto in CICLO:
            try:
                if core.submit(texto, source="text"):
                    enviados += 1
                limite = time.monotonic() + 120
                while core.busy and time.monotonic() < limite:
                    time.sleep(0.02)
            except Exception as exc:                                # registrado, nunca escondido
                erros.append(f"{type(exc).__name__}: {exc}")
        if time.monotonic() >= proxima_amostra:
            stats = getattr(core.bus, "stats", None)
            amostras.append({"t_min": round((time.monotonic() - inicio) / 60, 2),
                             "rss_mb": round(processo.memory_info().rss / 2 ** 20, 1),
                             "threads": threading.active_count(), "enviados": enviados, "respostas": respostas["n"],
                             "descartes_bus": getattr(stats, "dropped", None)})
            proxima_amostra += 60
        time.sleep(args.intervalo)
    core.shutdown()
    time.sleep(1.0)
    if falso is not None:
        falso.__exit__(None, None, None)
    restantes = [t.name for t in threading.enumerate() if t.ident not in antes and t.is_alive()]
    metricas_memoria = crescimento(amostras)
    metricas = {"duracao_min": round(minutos, 2), "pedidos_enviados": enviados, "respostas": respostas["n"],
                "sem_resposta": max(0, enviados - respostas["n"]), "erros": len(erros),
                **metricas_memoria, "threads_restantes_apos_encerrar": restantes}
    resultado = {"protocolo": "PV-07", "real": ["NeuralCore completo sem voz/percepção/plugins"],
                 "simulado": [] if args.ollama else ["inferência do modelo (servidor local de 0 ms)"],
                 "ambiente": C.ambiente(), "rapido": args.rapido, "metricas": metricas, "amostras": amostras,
                 "erros": erros[:50]}
    caminho = C.gravar("pv07_estabilidade", resultado, rotulo=args.rotulo)
    print(metricas)
    print(f"resultado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
