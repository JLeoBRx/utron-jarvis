"""Sensor de sistema de arquivos: mudanças em pastas observadas e detecção de projetos.

Por varredura de metadados (mtime/tamanho), com limite de arquivos por pasta e pastas
pesadas ignoradas. Não lê conteúdo de arquivos.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from .base import Percept, Sensor

IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache",
                "dist", "build", ".idea", ".vs", ".vscode", "target", "bin", "obj", ".next", ".cache"}
PROJECT_MARKERS = {
    "pyproject.toml": "Python", "requirements.txt": "Python", "setup.py": "Python", "Pipfile": "Python",
    "package.json": "JavaScript/TypeScript", "Cargo.toml": "Rust", "go.mod": "Go", "pom.xml": "Java",
    "build.gradle": "Java/Kotlin", "CMakeLists.txt": "C/C++", "platformio.ini": "Embarcados",
}


def detect_project(path: Path) -> dict | None:
    try:
        names = {p.name for p in path.iterdir()}
    except OSError:
        return None
    language = next((lang for marker, lang in PROJECT_MARKERS.items() if marker in names), None)
    if not language and ".git" not in names and not any(n.endswith((".csproj", ".sln")) for n in names):
        return None
    if not language and any(n.endswith((".csproj", ".sln")) for n in names):
        language = "C#"
    venv = next((n for n in (".venv", "venv", "env") if (path / n).is_dir()), "")
    return {"name": path.name, "path": str(path), "language": language or "desconhecida",
            "git": ".git" in names, "venv": venv,
            "markers": sorted(n for n in names if n in PROJECT_MARKERS)}


def scan_tree(root: Path, limit: int = 2000) -> dict[str, tuple[float, int]]:
    result: dict[str, tuple[float, int]] = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for name in files:
            path = os.path.join(folder, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            result[path] = (st.st_mtime, st.st_size)
            if len(result) >= limit:
                return result
    return result


class FilesystemSensor(Sensor):
    name = "filesystem"
    kind = "structural"

    def __init__(self, dirs: Callable[[], list[str]], interval: float = 10.0, *, limit: int = 2000):
        super().__init__(interval)
        self._dirs = dirs
        self.limit = limit
        self._snapshots: dict[str, dict[str, tuple[float, int]]] = {}

    def sense(self) -> Percept | None:
        roots = [Path(d) for d in (self._dirs() or []) if d and Path(d).is_dir()][:12]
        if not roots:
            return Percept("filesystem", "structural", {"watched": [], "changes": [], "projects": []}, 1.0)
        changes, projects = [], []
        for root in roots:
            key = str(root)
            current = scan_tree(root, self.limit)
            previous = self._snapshots.get(key)
            self._snapshots[key] = current
            project = detect_project(root)
            if project:
                projects.append(project)
            if previous is None:
                continue
            created = [p for p in current if p not in previous]
            deleted = [p for p in previous if p not in current]
            modified = [p for p in current if p in previous and current[p] != previous[p]]
            if created or deleted or modified:
                changes.append({"root": key, "created": len(created), "deleted": len(deleted),
                                "modified": len(modified),
                                "samples": [os.path.relpath(p, key) for p in (modified + created + deleted)[:6]],
                                "project": project["name"] if project else ""})
        return Percept("filesystem", "structural", {"watched": [str(r) for r in roots], "changes": changes,
                                                    "projects": projects, "timestamp": time.time()}, 1.0)
