"""Gerenciador de plugins.

Procura plugins em ``<ULTRON>/plugins`` e em ``<dados do usuário>/plugins``: um arquivo
``nome.py`` ou uma pasta ``nome/`` com ``plugin.py`` (ou ``__init__.py``). O módulo expõe
``PLUGIN`` (instância), ``create_plugin()`` ou uma subclasse de ``Plugin``.

Cada plugin passa por: verificação de requisitos → ``initialize`` com tempo limite →
estado ``ACTIVE``. Falha em um plugin nunca impede o ULTRON de iniciar; o motivo fica
registrado e visível no diagnóstico.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .. import __version__
from ..config import paths
from .base import CAPABILITIES, Plugin, PluginContext

log = logging.getLogger("ultron.plugins")

INIT_TIMEOUT = 10.0


@dataclass
class PluginRecord:
    name: str
    path: str
    version: str = ""
    description: str = ""
    capabilities: tuple = ()
    status: str = "DISCOVERED"       # DISCOVERED | ACTIVE | SKIPPED | FAILED | STOPPED
    reason: str = ""
    seconds: float = 0.0
    plugin: Plugin | None = field(default=None, repr=False)
    context: PluginContext | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": self.path, "version": self.version, "description": self.description,
                "capabilities": list(self.capabilities), "status": self.status, "reason": self.reason,
                "seconds": round(self.seconds, 3)}


def _version_tuple(text: str) -> tuple:
    parts = []
    for piece in str(text).split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def check_requirements(plugin: Plugin) -> str:
    """Devolve o motivo de não poder carregar, ou ''."""
    req = plugin.requirements or {}
    platform = req.get("platform")
    if platform and not sys.platform.startswith(platform):
        return f"requer a plataforma {platform}"
    for module in req.get("modules", ()):
        if importlib.util.find_spec(module) is None:
            return f"módulo {module} não instalado"
    minimum = req.get("ultron")
    if minimum and _version_tuple(__version__) < _version_tuple(minimum):
        return f"requer ULTRON {minimum} ou superior"
    unknown = set(plugin.capabilities) - set(CAPABILITIES)
    if unknown:
        return f"capacidades desconhecidas: {sorted(unknown)}"
    return ""


def _instantiate(module) -> Plugin | None:
    candidate = getattr(module, "PLUGIN", None)
    if isinstance(candidate, Plugin):
        return candidate
    factory = getattr(module, "create_plugin", None)
    if callable(factory):
        made = factory()
        if isinstance(made, Plugin):
            return made
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, Plugin) and obj is not Plugin and obj.__module__ == module.__name__:
            return obj()
    return None


class PluginManager:
    name = "plugins"

    def __init__(self, *, context_factory: Callable[[Plugin], PluginContext],
                 settings_getter: Callable[[], Any] | None = None, directories: list[Path] | None = None):
        self._context_factory = context_factory
        self._settings = settings_getter or (lambda: None)
        self.directories = directories if directories is not None else [paths.plugins_dir(),
                                                                         paths.data_dir() / "plugins"]
        self.records: dict[str, PluginRecord] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ descoberta
    def discover(self) -> list[tuple[str, Path]]:
        found: list[tuple[str, Path]] = []
        for directory in self.directories:
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir()):
                if entry.name.startswith(("_", ".")):
                    continue
                if entry.is_file() and entry.suffix == ".py":
                    found.append((entry.stem, entry))
                elif entry.is_dir():
                    for main in ("plugin.py", "__init__.py"):
                        if (entry / main).is_file():
                            found.append((entry.name, entry / main))
                            break
        return found

    def _load_module(self, name: str, path: Path):
        module_name = f"ultron_plugin_{name}"
        spec = importlib.util.spec_from_file_location(module_name, path,
                                                      submodule_search_locations=[str(path.parent)]
                                                      if path.name == "__init__.py" else None)
        if spec is None or spec.loader is None:
            raise ImportError(f"não foi possível carregar {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        return module

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        s = self._settings()
        if not getattr(s, "plugins", True):
            log.info("plugins desativados nas configurações")
            return
        enabled = set(getattr(s, "plugins_enabled", ()) or ())
        disabled = set(getattr(s, "plugins_disabled", ()) or ())
        for name, path in self.discover():
            record = PluginRecord(name, str(path))
            with self._lock:
                duplicate = name in self.records
                self.records[f"{name}@{path.parent}" if duplicate else name] = record
            if duplicate:
                record.status, record.reason = "SKIPPED", "já existe um plugin com este nome"
                continue
            try:
                plugin = _instantiate(self._load_module(name, path))
            except Exception as exc:
                record.status, record.reason = "FAILED", f"erro ao importar: {type(exc).__name__}: {exc}"
                log.warning("plugin %s: %s", name, record.reason)
                continue
            if plugin is None:
                record.status, record.reason = "FAILED", "nenhum Plugin exportado (PLUGIN, create_plugin ou classe)"
                continue
            record.plugin = plugin
            record.version, record.description = plugin.version, plugin.description
            record.capabilities = tuple(plugin.capabilities)
            if name in disabled or plugin.name in disabled:
                record.status, record.reason = "SKIPPED", "desativado nas configurações"
                continue
            if not plugin.default_enabled and not ({name, plugin.name} & enabled):
                record.status, record.reason = "SKIPPED", "desativado por padrão (ative em plugins_enabled)"
                continue
            reason = check_requirements(plugin)
            if reason:
                record.status, record.reason = "SKIPPED", reason
                continue
            self._initialize(record)

    def _initialize(self, record: PluginRecord) -> None:
        ctx = self._context_factory(record.plugin)
        record.context = ctx
        errors: list[BaseException] = []
        done = threading.Event()

        def runner() -> None:
            try:
                record.plugin.initialize(ctx)
            except BaseException as exc:
                errors.append(exc)
            finally:
                done.set()

        started = time.perf_counter()
        threading.Thread(target=runner, name=f"plugin-init-{record.name}", daemon=True).start()
        if not done.wait(INIT_TIMEOUT):
            record.status, record.reason = "FAILED", f"initialize() excedeu {INIT_TIMEOUT:.0f}s"
            ctx.cleanup()
            return
        record.seconds = time.perf_counter() - started
        if errors:
            record.status, record.reason = "FAILED", f"{type(errors[0]).__name__}: {errors[0]}"
            ctx.cleanup()
            log.warning("plugin %s falhou: %s", record.name, record.reason)
            return
        record.status = "ACTIVE"
        log.info("plugin %s %s ativo", record.name, record.version)

    def stop(self) -> None:
        for record in reversed(list(self.records.values())):
            if record.status != "ACTIVE":
                continue
            try:
                record.plugin.shutdown()
            except Exception as exc:
                log.warning("plugin %s falhou ao encerrar: %s", record.name, exc)
            if record.context is not None:
                record.context.cleanup()
            record.status = "STOPPED"

    def health(self) -> dict:
        active = [r for r in self.records.values() if r.status == "ACTIVE"]
        failed = [r for r in self.records.values() if r.status == "FAILED"]
        detail = f"{len(active)} ativo(s)" + (f", {len(failed)} com falha: " + ", ".join(r.name for r in failed)
                                               if failed else "")
        return {"status": "WARN" if failed else "OK", "detail": detail}

    def list(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records.values()]
