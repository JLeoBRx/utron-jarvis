"""Utilidades dos experimentos do TCC (protocolos PV-01…PV-07 em docs/research/PROTOCOLOS_DE_VALIDACAO.md).

Regras que todos os experimentos seguem:

* os dados do usuário NUNCA são lidos nem alterados: a pasta de dados aponta para uma pasta temporária ANTES de
  qualquer import do pacote (``preparar()``);
* cada resultado registra o ambiente (sistema, CPU, memória, Python, versões, commit) e o que foi REAL e o que
  foi SIMULADO — o JSON vai para ``docs/research/resultados/``;
* números são calculados dos dados brutos, que também ficam no JSON (para conferência e reanálise).
"""
from __future__ import annotations

import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]                 # ULTRON/
RESULTADOS = RAIZ / "docs" / "research" / "resultados"


def preparar(prefixo: str = "safra-exp-") -> Path:
    """Pasta de dados temporária para o experimento (antes de importar ``ultron``)."""
    pasta = Path(tempfile.mkdtemp(prefix=prefixo))
    os.environ["SAFRA_DATA_DIR"] = str(pasta)
    os.environ["JARVIS_DATA_DIR"] = str(pasta)
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))
    if str(RAIZ / "tests") not in sys.path:
        sys.path.append(str(RAIZ / "tests"))
    return pasta


def _versao(pacote: str) -> str:
    try:
        import importlib.metadata as md
        return md.version(pacote)
    except Exception:
        return "ausente"


def _commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True,
                             timeout=10, stdin=subprocess.DEVNULL)
        sujo = subprocess.run(["git", "status", "--porcelain", "--", "ultron"], cwd=RAIZ, capture_output=True,
                              text=True, timeout=10, stdin=subprocess.DEVNULL)
        return out.stdout.strip() + ("+alterações" if sujo.stdout.strip() else "")
    except Exception:
        return "desconhecido"


def ambiente(extra: dict | None = None) -> dict:
    try:
        import psutil
        memoria = round(psutil.virtual_memory().total / 2 ** 30, 1)
        cpus = psutil.cpu_count(logical=True)
    except Exception:
        memoria, cpus = None, os.cpu_count()
    info = {
        "sistema": f"{platform.system()} {platform.release()}",
        "maquina": platform.machine(),
        "processador": platform.processor() or "não informado",
        "cpus_logicas": cpus,
        "memoria_gb": memoria,
        "python": platform.python_version(),
        "pacotes": {p: _versao(p) for p in ("PySide6-Essentials", "vosk", "piper-tts", "numpy", "psutil")},
        "commit": _commit(),
        "data_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if extra:
        info.update(extra)
    return info


def resumo(valores: list[float]) -> dict:
    """Estatística descritiva (n, média, desvio, mediana, p95, mínimo, máximo e IC 95 % da média)."""
    v = [float(x) for x in valores if x is not None and math.isfinite(float(x))]
    if not v:
        return {"n": 0}
    v.sort()
    n = len(v)
    media = statistics.fmean(v)
    desvio = statistics.stdev(v) if n > 1 else 0.0
    p95 = v[min(n - 1, int(math.ceil(0.95 * n)) - 1)]
    meia = 1.96 * desvio / math.sqrt(n) if n > 1 else 0.0          # aproximação normal
    return {"n": n, "media": round(media, 4), "desvio": round(desvio, 4), "mediana": round(statistics.median(v), 4),
            "p95": round(p95, 4), "min": round(v[0], 4), "max": round(v[-1], 4),
            "ic95": [round(media - meia, 4), round(media + meia, 4)]}


def proporcao(acertos: int, total: int) -> dict:
    """Proporção com intervalo de Wilson (95 %), adequado a amostras pequenas."""
    if total <= 0:
        return {"acertos": acertos, "total": total, "taxa": None}
    z = 1.96
    p = acertos / total
    centro = (p + z * z / (2 * total)) / (1 + z * z / total)
    meia = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return {"acertos": acertos, "total": total, "taxa": round(p, 4),
            "ic95_wilson": [round(max(0.0, centro - meia), 4), round(min(1.0, centro + meia), 4)]}


def wer(referencia: str, hipotese: str) -> float:
    """Taxa de erro de palavras (WER) por distância de edição entre listas de palavras normalizadas."""
    from ultron.voice.wake_word import _norm
    r, h = _norm(referencia).split(), _norm(hipotese).split()
    if not r:
        return 0.0 if not h else 1.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / len(r)


def gravar(nome: str, dados: dict, *, rotulo: str = "") -> Path:
    """Grava ``docs/research/resultados/<nome>_<rotulo-ou-data>.json`` e devolve o caminho."""
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    sufixo = rotulo or datetime.now().strftime("%Y%m%d-%H%M")
    caminho = RESULTADOS / f"{nome}_{sufixo}.json"
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho


class Cronometro:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.s = time.perf_counter() - self.t0
        return False


def argumentos(descricao: str, *, extra=None):
    import argparse
    p = argparse.ArgumentParser(description=descricao)
    p.add_argument("--rotulo", default="", help="sufixo do arquivo de resultado (ex.: pc-referencia, conteiner)")
    p.add_argument("--rapido", action="store_true", help="amostra reduzida (verificação do instrumento)")
    if extra:
        extra(p)
    return p.parse_args()
