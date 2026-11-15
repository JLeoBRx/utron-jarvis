"""Regras que valem para toda a nova geração: nada do legado, nada de terceiros, nenhum segredo."""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NEW_PLATFORM = ("backend", "apps", "packages", "deployment", "desktop", "scripts/e2e", "scripts/licenses", "tests")
SKIP_PARTS = {"node_modules", ".venv", "__pycache__", "dist", "target", ".pytest_cache", "gen"}
_FOREIGN = [part.replace("_", "") for part in ("tar_dis", "noc_tario", "jar_vis", "ult_ron", "doctor_who", "gal_lifrey")]
FOREIGN_NAMES = re.compile("|".join(_FOREIGN), re.IGNORECASE)
SECRETS = (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9]{20,}"), re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
           re.compile(r"(?i)\b(password|senha|secret|token|api_key)\s*=\s*[\"'][^\"'\s]{12,}[\"']"))
TEST_VALUES = ("senha de teste", "senha-que-ninguem-usa", "senha nova", "senha recuperada", "uma senha", "outra senha",
               "senha errada", "qualquer senha", "hunter2", "senha-secreta-123")


def _files():
    for folder in NEW_PLATFORM:
        root = REPO / folder
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not (set(path.parts) & SKIP_PARTS) and not any(p.endswith(".egg-info") for p in path.parts):
                yield path


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def test_no_third_party_names_in_the_new_platform():
    hits = []
    for path in _files():
        if path == Path(__file__).resolve():
            continue
        text = _text(path)
        if text is None:
            continue
        hits += [f"{path.relative_to(REPO)}:{n}: {line.strip()[:80]}" for n, line in enumerate(text.splitlines(), 1)
                 if FOREIGN_NAMES.search(line)]
    assert not hits, "\n".join(hits[:20])


def test_new_code_does_not_import_the_legacy():
    legacy = "ult" + "ron"
    for path in _files():
        if path.suffix != ".py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else [])
            assert not any(name.split(".")[0] == legacy for name in names), path


def test_no_secret_is_committed_in_the_new_platform():
    hits = []
    for path in _files():
        text = _text(path)
        if text is None or path == Path(__file__).resolve():
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(value in line for value in TEST_VALUES):
                continue
            if any(pattern.search(line) for pattern in SECRETS):
                hits.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:80]}")
    assert not hits, "\n".join(hits[:20])
    assert not list(REPO.glob("backend/**/.env")) and not list(REPO.glob("deployment/**/.env"))


def test_the_legacy_folder_is_not_referenced_as_a_dependency():
    for manifest in list((REPO / "backend").rglob("pyproject.toml")) + list((REPO / "apps").rglob("package.json")):
        assert ("ULT" + "RON") not in manifest.read_text(encoding="utf-8"), manifest
