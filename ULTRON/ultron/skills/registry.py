"""SKILL ROUTER — registro e descoberta de skills.

O registro é a única autoridade sobre o que pode ser executado. Nomes fora dele (inclusive
"shell", "powershell", "python", "eval"...) são recusados antes de qualquer validação.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
import threading
from typing import Iterable

from .base import Skill

log = logging.getLogger("ultron.skills")

FORBIDDEN = frozenset({"run_shell", "shell", "powershell", "cmd", "bash", "python", "python_exec", "eval",
                       "exec", "os_system", "subprocess", "run_code", "disable_defender", "disable_firewall",
                       "disable_uac"})

SKILL_PACKAGES = ("windows", "applications", "automation", "filesystem", "browser", "vision", "network",
                  "devices", "diagnostics", "development", "audio", "memory", "imagination", "system", "secondbrain",
                  "assistant", "tardis", "noctario")


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._lock = threading.RLock()

    def register(self, skill: Skill, *, replace: bool = False) -> Skill:
        name = skill.name
        if not name or name in FORBIDDEN:
            raise ValueError(f"nome de skill proibido: {name!r}")
        with self._lock:
            if name in self._skills and not replace:
                raise ValueError(f"skill já registrada: {name}")
            self._skills[name] = skill
        return skill

    def unregister(self, name: str) -> None:
        with self._lock:
            self._skills.pop(name, None)

    def get(self, name: str) -> Skill | None:
        if name in FORBIDDEN:
            return None
        with self._lock:
            return self._skills.get(name)

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._skills)

    def all(self) -> list[Skill]:
        with self._lock:
            return [self._skills[n] for n in sorted(self._skills)]

    def available(self) -> list[Skill]:
        return [s for s in self.all() if s.available()[0]]

    def by_category(self, category: str) -> list[Skill]:
        return [s for s in self.all() if s.category == category]

    def schemas(self, *, names: Iterable[str] | None = None, llm_only: bool = True) -> list[dict]:
        wanted = set(names) if names is not None else None
        return [s.schema() for s in self.available()
                if (wanted is None or s.name in wanted) and (s.expose_to_llm or not llm_only)]

    def relevant(self, text: str, *, limit: int = 12) -> list[str]:
        """Skills mais relevantes para um pedido (reduz o prompt enviado a modelos locais pequenos)."""
        import re
        import unicodedata

        def norm(value: str) -> set[str]:
            value = unicodedata.normalize("NFD", value.casefold())
            value = "".join(c for c in value if unicodedata.category(c) != "Mn")
            return {w for w in re.findall(r"[a-z]{3,}", value)}

        words = norm(text)
        scored = []
        for skill in self.available():
            if not skill.expose_to_llm:
                continue
            tokens = norm(f"{skill.name.replace('.', ' ').replace('_', ' ')} {skill.description} {skill.category}")
            score = len(words & tokens) + (0.5 if skill.risk.value in ("none", "low") else 0.0)
            scored.append((score, skill.name))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [name for _score, name in scored[:limit]]

    def catalog(self) -> list[dict]:
        return [s.info() for s in self.all()]

    def catalog_text(self, limit: int = 60) -> str:
        """Lista para o planejador do modelo: só as skills que o modelo pode escolher (``expose_to_llm``)."""
        lines = []
        for skill in [s for s in self.available() if s.expose_to_llm][:limit]:
            props = ", ".join(skill.inputs.get("properties", {}).keys())
            lines.append(f"- {skill.name}({props}) [{skill.risk.value}]: {skill.description}")
        return "\n".join(lines)

    def __len__(self) -> int:
        with self._lock:
            return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None


def load_builtin(registry: SkillRegistry) -> SkillRegistry:
    """Importa ``ultron.skills.<pacote>`` e registra o que cada um expõe em ``SKILLS``."""
    for package in SKILL_PACKAGES:
        try:
            module = importlib.import_module(f"ultron.skills.{package}")
        except Exception:
            log.exception("pacote de skills %s não pôde ser carregado", package)
            continue
        for skill_cls in getattr(module, "SKILLS", ()):
            try:
                registry.register(skill_cls())
            except Exception:
                log.exception("skill %s não pôde ser registrada", getattr(skill_cls, "name", skill_cls))
    return registry


def discover_modules() -> list[str]:
    import ultron.skills as pkg
    return sorted(m.name for m in pkgutil.iter_modules(pkg.__path__) if m.ispkg)
