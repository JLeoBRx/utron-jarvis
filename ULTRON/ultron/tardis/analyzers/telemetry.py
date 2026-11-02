"""Telemetria do sistema: métricas MEDIDAS do próprio JARVIS — nunca dados inventados.

Fonte única: o ``PerformanceMonitor`` do núcleo (``ctx.metrics``), o mesmo que alimenta DIAGNÓSTICOS:

* processo: CPU, memória residente e threads (psutil; sem psutil, diz que não mediu);
* modelos: latência real dos pedidos (carga, inferência, total) com mediana, p95 e quantidade;
* pedidos: tempo de ponta a ponta das respostas;
* interface: atraso do laço de eventos e custo dos quadros (quando a interface está aberta);
* Event Bus e workers: publicados, entregues, descartados, erros, filas e falhas.

As observações são HIPÓTESES explicadas a partir desses números. Nenhuma é aplicada: a TARDIS não muda
configuração nenhuma. Sem métrica coletada ainda, a tarefa termina com "sem dado" — nunca com um número
de exemplo.
"""
from __future__ import annotations

import math

from ..protocol import TaskFailed, TaskResult
from . import DETERMINISTIC, Run

UI_LAG_HIGH = 0.25            # s: p95 do atraso do laço da interface
MODEL_SLOW = 15.0             # s: p95 do pedido ao modelo
REQUEST_SLOW = 20.0           # s: p95 de ponta a ponta
RSS_HIGH_MB = 1500.0
SERIES = (("model.request", "Pedido ao modelo"), ("model.inference", "Inferência do modelo"),
          ("model.load", "Carga do modelo"), ("request", "Resposta de ponta a ponta"),
          ("ui.lag", "Atraso da interface"), ("ui.frame", "Custo do quadro da interface"),
          ("ui.event_delay", "Atraso de eventos até a interface"))


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _seconds(value) -> str:
    value = _num(value)
    if value is None:
        return "n/d"
    return f"{value * 1000:.0f} ms" if value < 1 else f"{value:.1f} s".replace(".", ",")


def telemetria(run: Run, data: dict) -> TaskResult:
    metrics = run.ctx.metrics
    if metrics is None or not callable(getattr(metrics, "snapshot", None)):
        raise TaskFailed("NO_DATA", "o monitor de desempenho não está disponível nesta execução")
    run.envelope.model = DETERMINISTIC
    try:
        process = metrics.sample_process() if callable(getattr(metrics, "sample_process", None)) else {}
    except Exception as exc:                                   # psutil ausente ou recusado: diz, não inventa
        process = {"error": f"{type(exc).__name__}: {exc}"[:120]}
    snap = metrics.snapshot()
    series = snap.get("series") or {}
    items, hypotheses, sources = [], [], []

    if process and not process.get("error"):
        cpu = process.get("cpu_percent")
        items.append({"title": f"Processo do JARVIS: {process.get('rss_mb', 'n/d')} MB, "
                               f"{process.get('threads', 'n/d')} threads",
                      "detail": f"CPU {cpu}%" if cpu is not None else "CPU: primeira leitura (sem média ainda)",
                      "source": "processo (psutil)"})
        sources.append("processo")
        rss = _num(process.get("rss_mb"))
        if rss is not None and rss > RSS_HIGH_MB:
            hypotheses.append(("Memória do processo alta", f"{rss:.0f} MB em uso: modelos de voz e a interface 3D "
                                                           "pesam; o perfil Econômico reduz a interface"))
    elif process.get("error"):
        items.append({"title": "Processo: não medido", "detail": process["error"], "source": "processo"})

    for key, label in SERIES:
        stats = series.get(key) or {}
        n = int(stats.get("n") or 0)
        if not n:
            continue
        items.append({"title": f"{label}: mediana {_seconds(stats.get('p50'))}, p95 {_seconds(stats.get('p95'))}",
                      "detail": f"{n} medição(ões); máximo {_seconds(stats.get('max'))}", "source": f"métrica {key}"})
        sources.append(key)
    p95 = lambda key: _num((series.get(key) or {}).get("p95"))          # noqa: E731
    if (p95("ui.lag") or 0) > UI_LAG_HIGH and int((series.get("ui.lag") or {}).get("n") or 0) >= 10:
        hypotheses.append(("Interface atrasando", f"o laço da interface atrasou {_seconds(p95('ui.lag'))} (p95): "
                                                  "perfil visual Econômico ou cena 3D desligada aliviam"))
    if (p95("model.request") or 0) > MODEL_SLOW:
        hypotheses.append(("Modelo lento", f"p95 de {_seconds(p95('model.request'))} por pedido: um modelo menor "
                                           "ou o modelo mantido carregado (keep_alive) reduz a espera"))
    if (p95("request") or 0) > REQUEST_SLOW:
        hypotheses.append(("Respostas lentas", f"p95 de {_seconds(p95('request'))} de ponta a ponta"))

    bus = snap.get("bus")
    if bus:
        items.append({"title": f"Event Bus: {bus.get('published', 0)} publicados, {bus.get('dropped', 0)} descartados",
                      "detail": f"entregues {bus.get('delivered', 0)} · erros nos ouvintes {bus.get('handler_errors', 0)}"
                                f" · na fila {bus.get('queued', 0)}", "source": "Event Bus"})
        sources.append("Event Bus")
        if bus.get("dropped"):
            hypotheses.append(("Eventos descartados", f"{bus['dropped']} evento(s) descartado(s) por fila cheia"))
    if "workers" in snap:
        items.append({"title": f"Workers: {snap.get('workers_alive', 0)}/{len(snap['workers'])} ativos, "
                               f"{snap.get('queued', 0)} na fila",
                      "detail": f"falhas acumuladas: {snap.get('worker_failures', 0)}", "source": "workers"})
        sources.append("workers")
    if snap.get("exceptions"):
        items.append({"title": f"Exceções registradas: {snap['exceptions']}",
                      "detail": "erros no registro, falhas de workers e de ouvintes do Event Bus", "source": "registro",
                      "severity": "média"})

    if not items:
        raise TaskFailed("NO_DATA", "nenhuma métrica coletada ainda: use o JARVIS por alguns minutos e analise de novo")
    for title, reason in hypotheses:
        items.append({"title": f"Hipótese: {title}", "detail": reason, "source": "métricas acima", "severity": "média"})
    head = f"{len(items) - len(hypotheses)} leitura(s) do sistema"
    head += (f"; {len(hypotheses)} ponto(s) de atenção: " + "; ".join(t.lower() for t, _ in hypotheses) + "."
             if hypotheses else "; nada fora das faixas de atenção.")
    return TaskResult(head, items=items, sources=sorted(set(sources)), actions=[])
