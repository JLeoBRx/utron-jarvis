"""Telemetria do Noctário: métricas MEDIDAS das voltas gravadas — nunca dados inventados.

Cada volta (``ctx.noctario_runs(limit)``, mais recente primeiro) é gravada pelo serviço do Noctário a partir
da telemetria recebida do robô — ou do simulador, sempre rotulado como tal:

    {"id", "started" (epoch), "duration_s", "result" (concluida | interrompida | linha_perdida | emergencia),
     "source" (robo | simulador), "params": {"base_pwm", "max_pwm", "kp", "kd", "error_range", ...},
     "samples": [{"t", "error", "corr", "pwm_l", "pwm_r", "lost", "cross"}, ...], "crossings": [t, ...],
     "losses": n (opcional, contado pelo firmware)}

Métricas: tempo de volta, RMS do erro, oscilação (cruzamentos por zero e frequência dominante por FFT),
fração do tempo com PWM saturado, perdas de linha, intervalos entre cruzamentos e comparação entre voltas.

As sugestões são HIPÓTESES explicadas a partir dessas métricas. Nenhuma é aplicada: com a skill
``noctario.set_params`` disponível, a TARDIS só PROPÕE um ajuste (o JARVIS pede confirmação) — e nunca a
partir de voltas do simulador. Nenhuma sugestão promete um tempo de volta.
"""
from __future__ import annotations

import math

from ..protocol import ProposedAction, TaskFailed, TaskResult
from . import DETERMINISTIC, Run

SATURATION_MARGIN = 0.98          # |PWM| a partir de 98% do máximo conta como saturado
MIN_SAMPLES_FFT = 64
OSCILLATION_HZ = 2.5              # oscilação acima disso, com amplitude relevante, indica pouco amortecimento
AMPLITUDE_RELEVANT = 0.12         # RMS do erro / faixa do erro
AMPLITUDE_SLUGGISH = 0.25
SATURATION_HIGH = 0.25
SLOWER_PCT = 3.0                  # a última volta é "mais lenta" que a melhor acima disso
TUNED = ("kp", "kd", "base_pwm", "max_pwm")
RESULT_LABELS = {"concluida": "concluída", "interrompida": "interrompida", "linha_perdida": "linha perdida",
                 "emergencia": "parada de emergência"}
NO_GUARANTEE = "Nenhuma sugestão garante um tempo de volta: meça de novo depois de cada ajuste."


def _num(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _series(samples: list[dict], key: str) -> tuple[list[float], list[float]]:
    times, values = [], []
    for sample in samples:
        t, v = _num(sample.get("t")), _num(sample.get(key))
        if t is not None and v is not None:
            times.append(t)
            values.append(v)
    return times, values


def zero_crossings(values: list[float], deadband: float = 0.0) -> int:
    """Trocas de lado do erro (esquerda ↔ direita da linha), ignorando o ruído dentro da banda morta."""
    count, side = 0, 0
    for value in values:
        current = 1 if value > deadband else -1 if value < -deadband else 0
        if current and side and current != side:
            count += 1
        if current:
            side = current
    return count


def dominant_frequency(times: list[float], values: list[float]) -> float | None:
    """Frequência (Hz) de maior energia no erro, por FFT sobre uma grade uniforme. None se há pouco dado."""
    if len(values) < MIN_SAMPLES_FFT:
        return None
    import numpy as np
    t = np.asarray(times, dtype=float)
    v = np.asarray(values, dtype=float)
    order = np.argsort(t, kind="stable")
    t, v = t[order], v[order]
    span = float(t[-1] - t[0])
    if span < 2.0:
        return None
    n = 1 << int(math.ceil(math.log2(len(v))))
    grid = np.linspace(t[0], t[-1], n)
    signal = np.interp(grid, t, v)
    signal = signal - signal.mean()
    if not np.any(np.abs(signal) > 1e-12):
        return None
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=span / (n - 1))
    useful = freqs >= 0.2
    if not useful.any():
        return None
    return float(freqs[useful][int(np.argmax(spectrum[useful]))])


def _crossing_times(lap: dict, samples: list[dict]) -> list[float]:
    explicit = [t for t in (_num(x) for x in lap.get("crossings") or []) if t is not None]
    if explicit:
        return sorted(explicit)
    times, counter = [], None
    for sample in samples:
        value, t = _num(sample.get("cross")), _num(sample.get("t"))
        if value is None or t is None:
            continue
        if counter is not None and value > counter:
            times.append(t)
        counter = value
    return times


def lap_metrics(lap: dict) -> dict:
    """Métricas de UMA volta. Campos sem dado ficam None (nunca estimados)."""
    samples = [s for s in lap.get("samples") or [] if isinstance(s, dict)]
    params = {k: v for k, v in dict(lap.get("params") or {}).items()}
    times, error = _series(samples, "error")
    duration = _num(lap.get("duration_s"))
    if duration is None and len(times) >= 2:
        duration = times[-1] - times[0]
    metrics = {"id": str(lap.get("id") or ""), "source": str(lap.get("source") or "robo"),
               "result": str(lap.get("result") or ""), "started": _num(lap.get("started")), "duration_s": duration,
               "samples": len(samples), "params": params, "error_rms": None, "error_max": None,
               "error_rms_norm": None, "zero_cross_hz": None, "dominant_hz": None, "saturation": None,
               "losses": None, "crossings": 0, "crossing_intervals": []}
    if error:
        rms = math.sqrt(sum(e * e for e in error) / len(error))
        peak = max(abs(e) for e in error)
        error_range = _num(params.get("error_range"))
        metrics.update(error_rms=rms, error_max=peak,
                       error_rms_norm=rms / error_range if error_range else None)
        span = times[-1] - times[0] if len(times) >= 2 else 0.0
        if span > 0:
            deadband = 0.05 * (error_range or peak)
            metrics["zero_cross_hz"] = zero_crossings(error, deadband) / span
        metrics["dominant_hz"] = dominant_frequency(times, error)
    max_pwm = _num(params.get("max_pwm"))
    pwm = [(_num(s.get("pwm_l")), _num(s.get("pwm_r"))) for s in samples]
    pwm = [(a, b) for a, b in pwm if a is not None and b is not None]
    if max_pwm and pwm:
        limit = SATURATION_MARGIN * max_pwm
        metrics["saturation"] = sum(1 for a, b in pwm if max(abs(a), abs(b)) >= limit) / len(pwm)
    if lap.get("losses") is not None:
        metrics["losses"] = int(_num(lap.get("losses"), 0))
    elif any("lost" in s for s in samples):
        losses, previous = 0, False
        for sample in samples:
            lost = bool(sample.get("lost"))
            losses += lost and not previous
            previous = lost
        metrics["losses"] = losses
    crossings = _crossing_times(lap, samples)
    metrics["crossings"] = len(crossings)
    start = times[0] if times else 0.0
    marks = [start] + crossings
    metrics["crossing_intervals"] = [round(b - a, 2) for a, b in zip(marks, marks[1:])]
    return metrics


def _fmt(value, pattern: str, missing: str = "n/d") -> str:
    return pattern.format(value) if value is not None else missing


def describe(metrics: dict) -> str:
    params = metrics["params"]
    parts = [f"erro RMS {_fmt(metrics['error_rms'], '{:.0f}')}"
             + (f" ({metrics['error_rms_norm']:.0%} da faixa)" if metrics["error_rms_norm"] is not None else ""),
             f"oscilação {_fmt(metrics['dominant_hz'], '{:.1f} Hz')}",
             f"saturação {_fmt(metrics['saturation'], '{:.0%}')}",
             f"perdas de linha {_fmt(metrics['losses'], '{}')}",
             f"cruzamentos {metrics['crossings']}"]
    tuning = " ".join(f"{k} {params[k]}" for k in TUNED if params.get(k) is not None)
    return " · ".join(parts) + (f" · {tuning}" if tuning else "")


def _completed(laps: list[dict]) -> list[dict]:
    return [m for m in laps if m["duration_s"] and m["result"] in ("concluida", "")]


def _changed(a: dict, b: dict) -> dict:
    return {k: (a.get(k), b.get(k)) for k in TUNED if _num(a.get(k)) != _num(b.get(k))}


def suggest(latest: dict, laps: list[dict]) -> list[dict]:
    """Hipóteses ordenadas por prioridade: [{"title", "reason", "params"}] — params = ajuste proposto."""
    out: list[dict] = []
    params = latest["params"]
    kp, kd, base = _num(params.get("kp")), _num(params.get("kd")), _num(params.get("base_pwm"))
    completed = _completed(laps)
    best = min(completed, key=lambda m: m["duration_s"]) if completed else None
    if best is not None and latest["duration_s"] and best["id"] != latest["id"]:
        slower = (latest["duration_s"] - best["duration_s"]) / best["duration_s"] * 100.0
        changed = _changed(best["params"], params)
        if slower > SLOWER_PCT and changed:
            diff = ", ".join(f"{k} {old} → {new}" for k, (old, new) in changed.items())
            out.append({"title": "Voltar aos parâmetros da melhor volta medida",
                        "reason": f"a última volta levou {latest['duration_s']:.1f} s, {slower:.0f}% acima da "
                                  f"melhor ({best['duration_s']:.1f} s); desde ela mudou: {diff}",
                        "params": {k: old for k, (old, _new) in changed.items() if old is not None}})
    amplitude = latest["error_rms_norm"]
    frequency = latest["dominant_hz"] or 0.0
    zero_hz = (latest["zero_cross_hz"] or 0.0) / 2.0          # dois cruzamentos por ciclo
    if max(frequency, zero_hz) >= OSCILLATION_HZ and amplitude is not None and amplitude >= AMPLITUDE_RELEVANT:
        proposal = {"kd": round(kd * 1.15, 4)} if kd else {}
        out.append({"title": "Amortecer a oscilação: Kd +15% (ou Kp −10% se persistir)",
                    "reason": f"o erro oscila a {max(frequency, zero_hz):.1f} Hz com RMS de {amplitude:.0%} da "
                              f"faixa: o PD reage demais e passa da linha de um lado para o outro",
                    "params": proposal})
    saturation = latest["saturation"]
    if saturation is not None and saturation >= SATURATION_HIGH:
        proposal = {"base_pwm": int(round(base * 0.95))} if base else {}
        out.append({"title": "Reduzir a velocidade base em ~5%",
                    "reason": f"o PWM ficou no limite em {saturation:.0%} da volta: a correção pedida pelo PD passa "
                              f"do que o motor entrega, e a curva sai mais aberta",
                    "params": proposal})
    if amplitude is not None and amplitude >= AMPLITUDE_SLUGGISH and frequency < 1.0 \
            and (saturation is None or saturation < 0.1):
        proposal = {"kp": round(kp * 1.10, 5)} if kp else {}
        out.append({"title": "Correção lenta: Kp +10%",
                    "reason": f"o erro fica grande ({amplitude:.0%} da faixa) e muda devagar, sem saturar o PWM: "
                              f"o PD corrige pouco",
                    "params": proposal})
    if latest["losses"]:
        out.append({"title": "Verificar calibração e velocidade nas curvas",
                    "reason": f"o robô perdeu a linha {latest['losses']} vez(es) nesta volta (pista preta, linha "
                              f"branca): recalibre os sensores e reduza a velocidade onde a perda ocorreu",
                    "params": {}})
    return out


def telemetria(run: Run, data: dict) -> TaskResult:
    if run.ctx.noctario_runs is None:
        raise TaskFailed("NO_DATA", "o serviço do Noctário não está disponível: não há telemetria para analisar")
    limit = max(1, min(int(_num(data.get("limit"), 10) or 10), 50))
    laps_raw = list(run.ctx.noctario_runs(limit) or [])
    wanted = str(data.get("run") or "")
    if wanted:
        laps_raw = [lap for lap in laps_raw if str(lap.get("id")) == wanted] or laps_raw[:0]
    if not laps_raw:
        raise TaskFailed("NO_DATA", "nenhuma volta do Noctário registrada" + (f" com o id {wanted}" if wanted else "")
                         + ": conecte o robô e grave uma volta para analisar")
    run.envelope.model = DETERMINISTIC
    laps = []
    for lap in laps_raw:
        run.check()
        laps.append(lap_metrics(lap))
    latest = laps[0]
    simulated = latest["source"] == "simulador"
    origin = "simulador" if simulated else "telemetria do robô"
    items = []
    for index, metrics in enumerate(laps):
        source = "simulador" if metrics["source"] == "simulador" else "telemetria do robô"
        result = RESULT_LABELS.get(metrics["result"], metrics["result"] or "sem resultado")
        items.append({"title": f"Volta {metrics['id'] or index + 1}: {_fmt(metrics['duration_s'], '{:.1f} s')} "
                               f"({result})",
                      "detail": describe(metrics), "source": f"{source} ({metrics['id']})"})
    hypotheses = suggest(latest, laps)
    for hypothesis in hypotheses:
        items.append({"title": f"Hipótese: {hypothesis['title']}", "detail": hypothesis["reason"],
                      "source": "métricas acima", "severity": "média"})
    actions = []
    proposal = next((h for h in hypotheses if h["params"]), None)
    if proposal is not None and not simulated and run.ctx.has_skill("noctario.set_params"):
        actions.append(ProposedAction("ajustar no Noctário: " + ", ".join(f"{k} = {v}" for k, v in
                                                                         proposal["params"].items()),
                                      "noctario.set_params", dict(proposal["params"]),
                                      f"{proposal['reason']} (hipótese; meça a próxima volta)"))
    completed = _completed(laps)
    best = min(completed, key=lambda m: m["duration_s"]) if completed else None
    head = (f"{len(laps)} volta(s) analisada(s) ({origin}" + (", NÃO são dados do robô" if simulated else "") + "). "
            f"Última: {_fmt(latest['duration_s'], '{:.1f} s')}")
    if best is not None:
        head += f"; melhor: {best['duration_s']:.1f} s"
    head += f". {describe(latest)}."
    if hypotheses:
        head += f" {len(hypotheses)} hipótese(s) de ajuste; a primeira: {hypotheses[0]['title'].lower()}. " + NO_GUARANTEE
    else:
        head += " Nenhuma métrica fora das faixas de atenção."
    sources = sorted({"simulador" if m["source"] == "simulador" else "telemetria do robô" for m in laps})
    return TaskResult(head, items, sources, actions,
                      {"laps": laps, "best": best["id"] if best else None, "suggestions": hypotheses,
                       "simulated": simulated})
