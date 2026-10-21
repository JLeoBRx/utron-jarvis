"""Diagnóstico e coordenação — leitura do estado REAL dos módulos (determinístico, sem modelo).

Diagnóstico: verificações do monitor de saúde (a última, se recente; senão uma nova dentro do prazo),
componentes que falharam na inicialização, workers parados ou com fila acumulada, microfone, Noctário e
falhas recentes da própria TARDIS — cada achado com a fonte e a gravidade. Para voz e rede, PROPÕE rodar o
diagnóstico completo (skills de leitura; o JARVIS executa só com confirmação).

Coordenação: uma fotografia dos módulos agora — estado do JARVIS, workers, fila da TARDIS, voz e
Noctário. Nada aqui altera o estado de nenhum módulo.
"""
from __future__ import annotations

import time

from ...core.runtime import run_with_timeout
from ..protocol import ProposedAction, TaskFailed, TaskResult
from . import DETERMINISTIC, Run

SEVERITY = {"FAIL": "alta", "WARN": "média", "UNAVAILABLE": "baixa", "UNKNOWN": "baixa"}
SEVERITY_ORDER = {"alta": 0, "média": 1, "baixa": 2}
STATUS_LABELS = {"FAIL": "falha", "WARN": "atenção", "UNAVAILABLE": "indisponível", "UNKNOWN": "desconhecido"}
CHECK_LABELS = {"CPU": "Processador", "RAM": "Memória RAM", "GPU": "GPU", "DISK": "Disco",
                "OLLAMA": "Modelos (Ollama)", "VOICE": "Voz", "VISION": "Visão", "NETWORK": "Rede",
                "MEMORY": "Banco de memória", "HUD": "Interface", "SECOND_BRAIN": "Memória pessoal",
                "TARDIS": "TARDIS", "NOCTARIO": "Noctário"}
HEALTH_MAX_AGE = 120.0
QUEUE_BACKLOG = 20
STATE_LABELS = {"IDLE": "em repouso", "LISTENING": "escutando", "THINKING": "pensando", "SPEAKING": "falando",
                "EXECUTING": "executando", "BOOTING": "inicializando", "DREAMING": "em repouso (sonho)",
                "REMINDING": "avisando um lembrete", "SHUTDOWN": "encerrando"}


def health_report(run: Run) -> tuple[dict | None, str]:
    """(relatório, de onde veio). Usa a última verificação se recente; senão verifica dentro do prazo."""
    health = run.ctx.health
    if health is None:
        return None, "monitor de saúde indisponível"
    last = dict(getattr(health, "last", None) or {})
    age = time.time() - float(last.get("timestamp") or 0.0)
    if last.get("checks") and age <= HEALTH_MAX_AGE:
        return last, f"verificação de saúde de {age:.0f} s atrás"
    budget = run.remaining() - 2.0
    if budget < 3.0:
        return (last or None), "sem tempo para uma verificação nova"
    try:
        report = run_with_timeout(health.check_all, budget)
    except TimeoutError:
        return (last or None), f"a verificação de saúde não terminou em {budget:.0f} s"
    return report, "verificação de saúde feita agora"


def _noctario_status(ctx) -> dict | None:
    service = ctx.noctario
    if service is None or not callable(getattr(service, "status", None)):
        return None
    try:
        return dict(service.status() or {})
    except Exception as exc:
        return {"link": "erro", "detail": f"{type(exc).__name__}: {exc}"[:160]}


def diagnostico(run: Run, data: dict) -> TaskResult:
    ctx = run.ctx
    if ctx.health is None and ctx.lifecycle is None and ctx.runtime is None:
        raise TaskFailed("NO_DATA", "nenhuma fonte de diagnóstico disponível (saúde, componentes, workers)")
    run.envelope.model = DETERMINISTIC
    items: list[dict] = []
    sources: list[str] = []
    actions: list[ProposedAction] = []

    def add(title: str, detail: str, source: str, severity: str) -> None:
        if not any(i["title"] == title for i in items):
            items.append({"title": title, "detail": detail[:240], "source": source, "severity": severity})

    report, origin = health_report(run)
    run.note(origin)
    checks = (report or {}).get("checks") or {}
    if report is not None:
        sources.append(f"monitor de saúde ({origin})")
        for name, check in checks.items():
            status = str(check.get("status", "UNKNOWN"))
            if status in SEVERITY:
                add(f"{CHECK_LABELS.get(name, name.title())}: {STATUS_LABELS[status]}", str(check.get("detail", "")),
                    "monitor de saúde", SEVERITY[status])
    else:
        add("Saúde não verificada", origin, "monitor de saúde", "média")
    run.check()
    if ctx.lifecycle is not None:
        sources.append("componentes")
        for name, status in ctx.lifecycle.statuses().items():
            if status == "FAILED":
                detail = getattr(ctx.lifecycle.health_of(name), "detail", "") or "falhou ao iniciar"
                add(f"Componente {name} falhou", detail, "componentes", "alta")
    if ctx.runtime is not None:
        sources.append("workers")
        for name, worker in ctx.runtime.status().items():
            if not worker.get("alive", True):
                add(f"Worker {name} parado", "a fila deste worker não está sendo processada", "workers", "alta")
            elif int(worker.get("pending") or 0) >= QUEUE_BACKLOG:
                add(f"Worker {name} com fila acumulada", f"{worker['pending']} tarefa(s) aguardando; em execução: "
                    f"{worker.get('current') or 'nada'}", "workers", "média")
    voice = None
    if ctx.voice_probe is not None:
        try:
            voice = ctx.voice_probe() or {}
        except Exception as exc:
            voice = {"reason": f"{type(exc).__name__}: {exc}"}
        sources.append("microfone")
        reason = str(voice.get("reason") or "")
        if reason and not any(reason in i["detail"] for i in items):
            add("Microfone com aviso", reason, "microfone", "média")
        if voice.get("enabled") and not voice.get("capturing") and not reason:
            add("Microfone habilitado sem captura", "a captura não está ativa", "microfone", "média")
    noctario = _noctario_status(ctx)
    if noctario is not None:
        sources.append("Noctário")
        link = str(noctario.get("link") or "desconhecido")
        if link not in ("conectado", "simulador"):
            add(f"Noctário: {link}", str(noctario.get("detail") or "sem conexão com o robô"), "Noctário", "baixa")
        if noctario.get("last_failure"):
            add("Noctário: última falha registrada", str(noctario["last_failure"]), "Noctário", "média")
    if ctx.store is not None:
        hour_ago = time.time() - 3600
        failed = [t for t in ctx.store.recent(50) if t.state == "FAILED" and (t.finished or 0) >= hour_ago
                  and t.id != run.envelope.id]
        if failed:
            codes = ", ".join(sorted({(t.error or {}).get("code", "?") for t in failed}))
            add(f"TARDIS: {len(failed)} análise(s) falharam na última hora", f"códigos: {codes}", "TARDIS", "baixa")
    voice_bad = any(i["title"].startswith(("Voz", "Microfone")) and i["severity"] != "baixa" for i in items)
    if voice_bad and ctx.has_skill("voice.diagnose"):
        actions.append(ProposedAction("rodar o diagnóstico de voz completo", "voice.diagnose", {},
                                      "a voz ou o microfone reportou problema; o diagnóstico só lê o estado"))
    network = checks.get("NETWORK") or {}
    if network.get("status") in ("FAIL", "WARN") and ctx.has_skill("network.diagnose"):
        actions.append(ProposedAction("diagnosticar a conectividade (interface, gateway, DNS, internet)",
                                      "network.diagnose", {}, f"a rede reportou: {network.get('detail', '')}"[:200]))
    items.sort(key=lambda i: SEVERITY_ORDER.get(i["severity"], 3))
    counts = {level: sum(1 for i in items if i["severity"] == level) for level in SEVERITY_ORDER}
    total_checks = len(checks)
    if not items:
        summary = (f"Nenhum problema encontrado: {total_checks} verificação(ões) de saúde, componentes e workers "
                   f"em ordem ({origin}).")
    else:
        summary = (f"{len(items)} ponto(s) de atenção: {counts['alta']} crítico(s), {counts['média']} aviso(s) e "
                   f"{counts['baixa']} informativo(s). Mais grave: {items[0]['title']} — {items[0]['detail']}")
    return TaskResult(summary, items, sources, actions,
                      {"counts": counts, "health_origin": origin, "overall": (report or {}).get("overall")})


def coordenacao(run: Run, data: dict) -> TaskResult:
    ctx = run.ctx
    run.envelope.model = DETERMINISTIC
    items: list[dict] = []
    sources: list[str] = []
    snapshot: dict = {}
    if ctx.state is not None:
        state = ctx.state.runtime_state
        phase = ctx.state.get("cognitive_phase", "") or ""
        snapshot["jarvis"] = {"state": state, "phase": phase}
        items.append({"title": f"JARVIS {STATE_LABELS.get(state, state.lower())}",
                      "detail": f"fase: {phase}" if phase else "sem pedido em andamento", "source": "estado"})
        sources.append("estado")
    if ctx.runtime is not None:
        workers = ctx.runtime.status()
        snapshot["workers"] = workers
        busy = {n: w for n, w in workers.items() if w.get("current") or w.get("pending")}
        dead = [n for n, w in workers.items() if not w.get("alive", True)]
        detail = ", ".join(f"{n}: {w.get('current') or '—'} (+{w.get('pending', 0)})" for n, w in busy.items())
        items.append({"title": f"Workers: {len(workers) - len(dead)}/{len(workers)} ativos, {len(busy)} ocupado(s)",
                      "detail": detail or "todos livres", "source": "workers",
                      **({"severity": "alta"} if dead else {})})
        sources.append("workers")
    if ctx.engine is not None:
        queue = ctx.engine.snapshot()
        snapshot["tardis"] = queue
        running = queue.get("running")
        items.append({"title": f"TARDIS: {queue.get('queued', 0)} na fila"
                               + (f", executando {running['kind_label']}" if running else ", nada em execução"),
                      "detail": f"modo {queue.get('mode_label', queue.get('mode', ''))}; "
                                f"{queue.get('failed_recent', 0)} falha(s) recente(s)", "source": "TARDIS"})
        sources.append("TARDIS")
    if ctx.voice_probe is not None:
        try:
            voice = ctx.voice_probe() or {}
        except Exception as exc:
            voice = {"reason": f"{type(exc).__name__}: {exc}"}
        snapshot["voice"] = {k: voice.get(k) for k in ("enabled", "capturing", "listening", "conversation", "stt",
                                                        "reason")}
        mic = "fechado" if not voice.get("enabled") else "capturando" if voice.get("capturing") else "sem captura"
        items.append({"title": f"Voz: microfone {mic}" + (", escutando" if voice.get("listening") else ""),
                      "detail": str(voice.get("reason") or voice.get("stt") or ""), "source": "microfone"})
        sources.append("microfone")
    noctario = _noctario_status(ctx)
    if noctario is not None:
        snapshot["noctario"] = noctario
        items.append({"title": f"Noctário: {noctario.get('link', 'desconhecido')}",
                      "detail": str(noctario.get("state_label") or noctario.get("detail") or ""), "source": "Noctário"})
        sources.append("Noctário")
    if not items:
        raise TaskFailed("NO_DATA", "nenhum módulo disponível para coordenar")
    summary = "; ".join(i["title"] for i in items) + "."
    return TaskResult(summary, items, sources, data=snapshot)
