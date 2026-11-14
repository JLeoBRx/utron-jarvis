"""Regras de arquitetura conferidas a cada execução (AD-01, AD-02, AD-08).

* um módulo só importa os de camadas abaixo da sua; não há ciclos;
* o SAFRA Portal só importa a camada de base do Core;
* construções perigosas são proibidas;
* a nova versão não importa nada do legado;
* nomes e elementos de terceiros não aparecem no código novo.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SRC = BACKEND / "src"

LAYERS = {
    "core": 0,
    "storage": 1, "security": 1,
    "monitoring": 2, "platform": 2, "memory": 2, "ai_gateway": 2, "voice": 2, "communication": 2,
    "projects": 3, "tools": 3, "intelligence": 3,
    "api": 4,
}
SAME_LAYER_ALLOWED = {("security", "storage")}                 # security pode guardar sessões pelo storage
PORTAL_MAY_IMPORT = {"safra.core", "safra.storage", "safra.security", "safra.monitoring", "safra.api.foundation"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_ATTRS = {("os", "system"), ("os", "popen"), ("subprocess", "getoutput"), ("subprocess", "getstatusoutput")}
FORBIDDEN_IMPORTS = {"pickle", "cPickle", "marshal", "shelve", "dill"}
LEGACY_PACKAGES = {"ult" + "ron"}
_FOREIGN = [part.replace("_", "") for part in ("tar_dis", "noc_tario", "jar_vis", "ult_ron", "doctor_who", "gal_lifrey")]
FOREIGN_NAMES = re.compile("|".join(_FOREIGN), re.IGNORECASE)


def _modules(package: str):
    for path in sorted((SRC / package).rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _absolute(path: Path, node: ast.ImportFrom) -> str:
    """Nome absoluto do módulo importado, resolvendo importações relativas."""
    if not node.level:
        return node.module or ""
    package = list(path.relative_to(SRC).with_suffix("").parts)[:-1]     # pacote que contém o arquivo
    base = package[: len(package) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


def _imports(path: Path, tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = _absolute(path, node)
            found.add(name)
            found.update(f"{name}.{alias.name}" for alias in node.names)
    return found


def _module_of(path: Path) -> str:
    return path.relative_to(SRC / "safra").parts[0]


def test_the_thirteen_modules_exist_and_are_all_layered():
    present = {p.name for p in (SRC / "safra").iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    assert present == set(LAYERS)


def test_modules_only_import_lower_layers():
    violations = []
    for path, tree in _modules("safra"):
        if path.parent == SRC / "safra":
            continue
        source = _module_of(path)
        for name in _imports(path, tree):
            parts = name.split(".")
            if parts[0] != "safra" or len(parts) < 2 or parts[1] not in LAYERS or parts[1] == source:
                continue
            target = parts[1]
            if LAYERS[target] < LAYERS[source] or (source, target) in SAME_LAYER_ALLOWED:
                continue
            violations.append(f"{path.relative_to(SRC)}: {source} (camada {LAYERS[source]}) importa "
                              f"{target} (camada {LAYERS[target]})")
    assert not violations, "\n".join(violations)


def test_core_imports_no_other_module():
    for path, tree in _modules("safra"):
        if path.parent != SRC / "safra" and _module_of(path) == "core":
            others = {n for n in _imports(path, tree) if n.startswith("safra.") and n.split(".")[1] in LAYERS
                      and n.split(".")[1] != "core"}
            assert not others, f"{path.name}: {others}"


def test_portal_only_imports_the_foundation_layer():
    for path, tree in _modules("safra_portal"):
        for name in _imports(path, tree):
            if name == "safra" or name.startswith("safra."):
                assert any(name == ok or name.startswith(ok + ".") for ok in PORTAL_MAY_IMPORT), (
                    f"{path.relative_to(SRC)} importa {name}: o Portal não pode alcançar dados do assistente")


def test_core_never_imports_the_portal():
    for path, tree in _modules("safra"):
        assert not any(n.split(".")[0] == "safra_portal" for n in _imports(path, tree)), path


def test_dangerous_constructs_are_absent():
    problems = []
    for package in ("safra", "safra_portal"):
        for path, tree in _modules(package):
            where = str(path.relative_to(SRC))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                        problems.append(f"{where}:{node.lineno} chama {func.id}()")
                    if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                            and (func.value.id, func.attr) in FORBIDDEN_ATTRS):
                        problems.append(f"{where}:{node.lineno} chama {func.value.id}.{func.attr}()")
                    for keyword in node.keywords:
                        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value:
                            problems.append(f"{where}:{node.lineno} usa shell=True")
                        if keyword.arg == "verify" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                            problems.append(f"{where}:{node.lineno} desliga a verificação de TLS")
            roots = {name.split(".")[0] for name in _imports(path, tree)}
            for bad in sorted(roots & FORBIDDEN_IMPORTS):
                problems.append(f"{where} importa {bad}")
    assert not problems, "\n".join(problems)


def test_new_code_does_not_depend_on_the_legacy():
    for package in ("safra", "safra_portal"):
        for path, tree in _modules(package):
            roots = {name.split(".")[0] for name in _imports(path, tree)}
            assert not roots & LEGACY_PACKAGES, f"{path.relative_to(SRC)} importa o legado"


def test_no_third_party_names_in_the_new_platform():
    """Código, configuração e interface da nova versão. Documentos e scripts de medição do legado ficam de fora."""
    hits = []
    for folder in ("backend", "frontend", "desktop", "infra"):
        root = REPO / folder
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if (not path.is_file() or path == Path(__file__).resolve()
                    or any(part in {"node_modules", ".venv", "__pycache__", "dist", "target", ".pytest_cache"}
                           or part.endswith(".egg-info") for part in path.parts)):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if FOREIGN_NAMES.search(line):
                    hits.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:80]}")
    assert not hits, "\n".join(hits[:20])
