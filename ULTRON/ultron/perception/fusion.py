"""PERCEPTION FUSION — combina evidências de vários sensores em hipóteses de contexto.

Exemplo (do enunciado do projeto)::

    SCREEN   VS Code em foco
    OCR      ModuleNotFoundError
    PROCESS  python.exe ativo
    TERMINAL execução falhou
    MEMORY   este projeto já apresentou esse erro
    ───────────────────────────────────────────────
    CONTEXT  Python project currently has an import failure.   CONFIDENCE 0.97

Combinação por *noisy-OR* das evidências independentes. Uma hipótese sustentada por um
único sensor tem a confiança limitada (``SINGLE_SOURCE_CAP``): o sistema não age a partir
de um único sensor.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .base import Percept

SINGLE_SOURCE_CAP = 0.6
MAX_AGE = {"vision": 120.0, "ocr": 120.0, "window": 10.0, "process": 30.0, "filesystem": 120.0,
           "network": 120.0, "device": 300.0, "system": 10.0, "screen": 30.0, "memory": 600.0}

IDE_PROCESSES = {"code.exe", "code", "pycharm64.exe", "idea64.exe", "devenv.exe", "sublime_text.exe"}
TERMINAL_PROCESSES = {"windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "bash", "zsh",
                      "gnome-terminal-server", "konsole", "conhost.exe"}
PYTHON_PROCESSES = {"python.exe", "pythonw.exe", "python", "python3", "py.exe"}
ERROR_TITLE_RE = re.compile(r"\berro\b|\berror\b|exception|falha|failed|fatal|traceback|"
                            r"n[aã]o est[aá] respondendo|not responding|parou de funcionar|crash", re.I)
IMPORT_ERROR_RE = re.compile(r"(ModuleNotFoundError|ImportError)[:\s]+(?:No module named\s+)?['\"]?([\w.\-]+)?", re.I)


@dataclass
class Evidence:
    source: str
    detail: str
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Hypothesis:
    kind: str
    description: str
    confidence: float
    evidence: list = field(default_factory=list)
    data: dict = field(default_factory=dict)

    @property
    def sources(self) -> set[str]:
        return {e.source for e in self.evidence}

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "description": self.description, "confidence": round(self.confidence, 3),
                "evidence": [e.to_dict() for e in self.evidence], "sources": sorted(self.sources),
                "data": dict(self.data)}


def noisy_or(weights: list[float]) -> float:
    product = 1.0
    for w in weights:
        product *= (1.0 - max(0.0, min(0.99, w)))
    return 1.0 - product


def _finalize(kind: str, description: str, evidence: list[Evidence], **data: Any) -> Hypothesis | None:
    if not evidence:
        return None
    confidence = noisy_or([e.weight for e in evidence])
    if len({e.source for e in evidence}) < 2:
        confidence = min(confidence, SINGLE_SOURCE_CAP)
    return Hypothesis(kind, description, confidence, evidence, data)


class PerceptionFusion:
    def __init__(self, memory_probe: Callable[[str], list[str]] | None = None):
        self._latest: dict[str, Percept] = {}
        self._lock = threading.Lock()
        self._memory_probe = memory_probe
        self.last: dict[str, Any] = {}

    def ingest(self, percept: Percept | None) -> None:
        if percept is None:
            return
        with self._lock:
            self._latest[percept.source] = percept

    def _fresh(self, source: str) -> dict | None:
        with self._lock:
            percept = self._latest.get(source)
        if percept is None or percept.age > MAX_AGE.get(source, 60.0):
            return None
        return percept.data

    # ------------------------------------------------------------ regras
    def _error_hypothesis(self, fg: dict, vision: dict | None, ocr: dict | None, procs: dict | None,
                          app: str) -> Hypothesis | None:
        evidence: list[Evidence] = []
        error_text = ""
        if vision and vision.get("error_visible"):
            error_text = vision.get("error_text") or ""
            evidence.append(Evidence("vision", f"erro visível: {error_text[:120] or 'sem texto'}",
                                     0.55 + 0.35 * float(vision.get("confidence", 0.5))))
        if ocr and ocr.get("errors"):
            error_text = error_text or ocr["errors"][0]
            evidence.append(Evidence("ocr", f"texto de erro lido: {ocr['errors'][0][:120]}", 0.7))
        if ERROR_TITLE_RE.search(fg.get("title") or ""):
            evidence.append(Evidence("window", f"título da janela indica erro: {fg.get('title', '')[:80]}", 0.45))
        if not evidence:
            return None
        process = (fg.get("process") or "").lower()
        running = {p.lower() for p in (procs or {}).get("important", [])}
        python_ctx = bool(IMPORT_ERROR_RE.search(error_text) or "python" in error_text.lower()
                          or "traceback" in error_text.lower())
        if process in IDE_PROCESSES:
            evidence.append(Evidence("window", f"{app} em foco", 0.25))
        if process in TERMINAL_PROCESSES:
            evidence.append(Evidence("window", "terminal em foco", 0.2))
        if python_ctx and running & PYTHON_PROCESSES:
            evidence.append(Evidence("process", "processo Python ativo", 0.25))
        if self._memory_probe and error_text:
            similar = self._memory_probe(error_text)
            if similar:
                evidence.append(Evidence("memory", f"erro semelhante já registrado: {similar[0][:100]}", 0.35))
        match = IMPORT_ERROR_RE.search(error_text)
        if match:
            module = match.group(2) or ""
            return _finalize("dependency_error",
                             f"Projeto Python com falha de importação{f' (módulo {module})' if module else ''}.",
                             evidence, module=module, error_text=error_text[:300], application=app)
        return _finalize("visible_error", f"Erro visível em {app or 'aplicação ativa'}.", evidence,
                         error_text=error_text[:300], application=app)

    def _hung_hypothesis(self, windows: dict | None, vision: dict | None) -> Hypothesis | None:
        if not windows:
            return None
        hung = [w for w in windows.get("windows", []) if w.get("hung")]
        fg = windows.get("foreground") or {}
        if fg.get("hung"):
            hung.append(fg)
        if not hung:
            return None
        target = hung[0]
        evidence = [Evidence("window", f"janela sem resposta: {target.get('title', '')[:80]}", 0.85)]
        if vision and re.search(r"n[aã]o est[aá] respondendo|not responding", vision.get("summary", ""), re.I):
            evidence.append(Evidence("vision", "a tela mostra 'não está respondendo'", 0.7))
        return _finalize("application_hung", f"{target.get('application') or target.get('process')} não está respondendo.",
                         evidence, process=target.get("process"), pid=target.get("pid"), hwnd=target.get("hwnd"))

    def _development_hypothesis(self, fg: dict, vision: dict | None, fs: dict | None, app: str) -> Hypothesis | None:
        evidence: list[Evidence] = []
        if (fg.get("process") or "").lower() in IDE_PROCESSES:
            evidence.append(Evidence("window", f"{app} em foco", 0.5))
        if vision and vision.get("activity") == "programando":
            evidence.append(Evidence("vision", "atividade: programando", 0.5))
        changes = (fs or {}).get("changes") or []
        project_changes = [c for c in changes if c.get("project")]
        if project_changes:
            evidence.append(Evidence("filesystem", f"projeto {project_changes[0]['project']} modificado", 0.4))
        project = project_changes[0]["project"] if project_changes else ""
        return _finalize("development", f"Sessão de desenvolvimento{f' no projeto {project}' if project else ''}.",
                         evidence, project=project)

    def _network_hypothesis(self, net: dict | None, vision: dict | None) -> Hypothesis | None:
        if not net:
            return None
        evidence: list[Evidence] = []
        if not net.get("online"):
            evidence.append(Evidence("network", "nenhuma interface ativa", 0.8))
        elif not net.get("gateway"):
            evidence.append(Evidence("network", "sem gateway padrão", 0.6))
        if vision and re.search(r"sem (conex[aã]o|internet)|no internet|offline|err_internet",
                                f"{vision.get('summary', '')} {vision.get('error_text', '')}", re.I):
            evidence.append(Evidence("vision", "a tela indica falta de conexão", 0.6))
        if not evidence:
            return None
        return _finalize("network_problem", "Problema de conectividade de rede.", evidence)

    # ------------------------------------------------------------ fusão
    def fuse(self) -> dict[str, Any]:
        windows = self._fresh("window")
        vision = self._fresh("vision")
        if vision and vision.get("discarded"):
            vision = None
        ocr = self._fresh("ocr")
        procs = self._fresh("process")
        fs = self._fresh("filesystem")
        net = self._fresh("network")
        fg = (windows or {}).get("foreground") or {}
        app = fg.get("application") or (vision or {}).get("app") or fg.get("process") or ""
        hypotheses = [h for h in (
            self._error_hypothesis(fg, vision, ocr, procs, app),
            self._hung_hypothesis(windows, vision),
            self._development_hypothesis(fg, vision, fs, app),
            self._network_hypothesis(net, vision),
        ) if h is not None]
        hypotheses.sort(key=lambda h: -h.confidence)
        top = hypotheses[0] if hypotheses else None
        context = {
            "timestamp": time.time(),
            "application": app,
            "window": fg.get("title", ""),
            "activity": (vision or {}).get("activity", ""),
            "summary": (vision or {}).get("summary", ""),
            "hypotheses": [h.to_dict() for h in hypotheses],
            "top": top.to_dict() if top else None,
            "confidence": round(top.confidence, 3) if top else 0.0,
            "sources": sorted({s for h in hypotheses for s in h.sources}),
        }
        self.last = context
        return context
