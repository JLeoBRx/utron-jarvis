"""WORLD MODEL — modelo interno persistente do ambiente.

Estrutura::

    COMPUTER      os, cpu, gpu, ram, storage, battery
    APPLICATIONS  aplicações observadas (processo, janelas, uso)
    WINDOWS       janelas abertas e a janela ativa
    PROCESSES     resumo de processos relevantes
    FILES         arquivos e pastas observados
    PROJECTS      projetos conhecidos (caminho, linguagem, ambiente)
    NETWORK       interfaces, roteador, gateway, DNS, dispositivos
    PERIPHERALS   câmera, microfone, alto-falantes, teclado, mouse, USB
    USER_CONTEXT  atividade e foco do usuário
    CURRENT_GOALS objetivos ativos
    ENVIRONMENT   horário, energia, locale

Cada seção guarda ``data``, ``source``, ``confidence`` e ``updated_at``. A persistência é
atômica (JSON) e com escrita adiada para não gravar a cada sensor.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from ..config import paths
from ..core.events import EventType

log = logging.getLogger("ultron.world")

SECTIONS = ("computer", "applications", "windows", "processes", "files", "projects", "network",
            "peripherals", "user_context", "current_goals", "environment")


class WorldModel:
    name = "world_model"

    def __init__(self, path: Path | None = None, *, bus=None, state=None, save_delay: float = 5.0):
        self.path = Path(path) if path else paths.data_file("world_model.json")
        self._bus = bus
        self._state = state
        self._lock = threading.RLock()
        self._sections: dict[str, dict[str, Any]] = {name: {"data": {}, "source": "", "confidence": 0.0,
                                                            "updated_at": 0.0} for name in SECTIONS}
        self._dirty = False
        self._save_delay = save_delay
        self._timer: threading.Timer | None = None
        self.revision = 0

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        self.load()
        self.update("environment", {"started_at": time.time(), "pid": os.getpid()}, source="runtime",
                    confidence=1.0, merge=True)

    def stop(self) -> None:
        self.flush()

    def health(self) -> dict:
        with self._lock:
            fresh = sum(1 for s in self._sections.values() if time.time() - s["updated_at"] < 600)
        return {"status": "OK", "detail": f"{fresh}/{len(SECTIONS)} seções atualizadas recentemente"}

    # ------------------------------------------------------------ persistência
    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("world_model.json ilegível (%s); iniciando vazio", exc)
            return
        with self._lock:
            for name in SECTIONS:
                section = data.get(name)
                if isinstance(section, dict) and isinstance(section.get("data"), dict):
                    self._sections[name] = {"data": section["data"], "source": str(section.get("source", "")),
                                            "confidence": float(section.get("confidence", 0.0)),
                                            "updated_at": float(section.get("updated_at", 0.0))}
            # Estado volátil de sessões anteriores não é verdade agora.
            for volatile in ("windows", "processes", "user_context", "current_goals"):
                self._sections[volatile]["confidence"] = 0.0

    def flush(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if not self._dirty:
                return
            payload = copy.deepcopy(self._sections)
            self._dirty = False
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("não consegui gravar o world model: %s", exc)

    def _schedule_save(self) -> None:
        if self._timer is not None or self._save_delay <= 0:
            if self._save_delay <= 0:
                self.flush()
            return
        self._timer = threading.Timer(self._save_delay, self._timed_flush)
        self._timer.daemon = True
        self._timer.start()

    def _timed_flush(self) -> None:
        with self._lock:
            self._timer = None
        self.flush()

    # ------------------------------------------------------------ atualização
    def update(self, section: str, data: dict[str, Any], *, source: str, confidence: float = 1.0,
               merge: bool = False) -> bool:
        if section not in SECTIONS:
            raise KeyError(f"seção desconhecida do world model: {section}")
        with self._lock:
            current = self._sections[section]
            new_data = dict(current["data"]) if merge else {}
            new_data.update(data or {})
            changed = new_data != current["data"]
            self._sections[section] = {"data": new_data, "source": source,
                                       "confidence": max(0.0, min(1.0, float(confidence))),
                                       "updated_at": time.time()}
            if changed:
                self.revision += 1
                self._dirty = True
                self._schedule_save()
            revision = self.revision
        if changed and self._bus is not None:
            self._bus.publish(EventType.WORLD_MODEL_UPDATED, {"section": section, "revision": revision,
                                                              "source": source}, source="world")
        if changed and self._state is not None:
            self._state.update(_source="world", world_model=self.summary_dict())
        return changed

    def upsert_item(self, section: str, key: str, item: dict[str, Any], *, source: str,
                    confidence: float = 1.0, limit: int = 500) -> None:
        """Atualiza um item dentro de uma seção do tipo coleção (apps, projetos, dispositivos)."""
        with self._lock:
            data = dict(self._sections[section]["data"])
            previous = dict(data.get(key) or {})
            previous.update(item)
            previous["last_seen"] = time.time()
            previous.setdefault("first_seen", previous["last_seen"])
            data[key] = previous
            if len(data) > limit:
                oldest = sorted(data, key=lambda k: data[k].get("last_seen", 0))[: len(data) - limit]
                for old in oldest:
                    data.pop(old, None)
        self.update(section, data, source=source, confidence=confidence)

    # ------------------------------------------------------------ leitura
    def get(self, section: str) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._sections[section]["data"])

    def section(self, section: str) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._sections[section])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._sections)

    def summary_dict(self) -> dict[str, Any]:
        with self._lock:
            comp = self._sections["computer"]["data"]
            net = self._sections["network"]["data"]
            ctx = self._sections["user_context"]["data"]
            return {
                "os": comp.get("os", ""),
                "cpu": comp.get("cpu_name", ""),
                "ram_gb": comp.get("ram_total_gb"),
                "gpu": comp.get("gpu_name", ""),
                "active_app": ctx.get("application", ""),
                "active_window": ctx.get("window", ""),
                "applications": len(self._sections["applications"]["data"]),
                "projects": len(self._sections["projects"]["data"]),
                "network_devices": len(net.get("devices") or {}),
                "gateway": net.get("gateway", ""),
                "peripherals": len(self._sections["peripherals"]["data"]),
                "revision": self.revision,
            }

    def describe(self, max_chars: int = 1400) -> str:
        """Resumo textual compacto para o contexto do modelo de linguagem."""
        s = self.summary_dict()
        with self._lock:
            ctx = self._sections["user_context"]["data"]
            projects = list(self._sections["projects"]["data"].items())[:5]
            goals = self._sections["current_goals"]["data"].get("goals", [])
        parts = [f"Sistema: {s['os'] or 'desconhecido'}; CPU {s['cpu'] or '?'}; RAM {s['ram_gb'] or '?'} GB; "
                 f"GPU {s['gpu'] or 'não detectada'}."]
        if s["active_app"] or s["active_window"]:
            parts.append(f"Em foco: {s['active_app']} — {s['active_window'][:80]}.")
        if ctx.get("activity"):
            parts.append(f"Atividade observada: {ctx['activity']}.")
        if projects:
            parts.append("Projetos conhecidos: " + ", ".join(f"{v.get('name', k)} ({v.get('language', '?')})"
                                                            for k, v in projects) + ".")
        if s["gateway"]:
            parts.append(f"Rede: gateway {s['gateway']}, {s['network_devices']} dispositivos conhecidos.")
        if goals:
            parts.append("Objetivos ativos: " + "; ".join(str(g)[:80] for g in goals[:3]) + ".")
        text = " ".join(parts)
        return text[:max_chars]
