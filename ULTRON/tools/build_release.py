"""Gera e valida o pacote de entrega do JARVIS (``JARVIS_FINAL.zip``).

    python tools/build_release.py                 gera ../JARVIS_FINAL.zip e valida
    python tools/build_release.py --out CAMINHO   outro destino
    python tools/build_release.py --check ZIP     só valida um pacote existente

Regras (as mesmas da validação):

* só entram arquivos VERSIONADOS no Git (nada de ``.venv``, caches, ``__pycache__``, logs,
  bancos, configurações ou dados pessoais — eles nem estão no repositório);
* modelos grandes de IA ficam de fora (``assets/stt`` e ``assets/voices``): o instalador
  copia os que faltam de uma instalação anterior, sem apagar nada, ou indica a fonte oficial;
* tudo vai dentro de uma pasta ``JARVIS/`` no ZIP.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent          # pasta do programa (ULTRON/)
PREFIX = "JARVIS/"
EXCLUDE = ("assets/stt/*", "assets/voices/*", "*.pyc", "*/__pycache__/*", ".venv/*", "venv/*",
           "*.sqlite3*", "*.sqlite3-*", "*.db", "*.db-*", "settings.json", "settings.*.json",
           "logs/*", "*.log", "*.zip", "*.partial", "world_model.json", "autorizacoes_permanentes.json",
           ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", ".DS_Store", "Thumbs.db")
FORBIDDEN = (".venv/", "venv/", "__pycache__/", ".pyc", ".sqlite3", ".db", "settings.json", "/logs/",
             ".git/", ".onnx", "final.mdl", "HCLr.fst", "autorizacoes_permanentes.json",
             ".env", ".pem", ".key", ".p12", ".pfx")
REQUIRED = ("main.py", "requirements.txt", "INSTALL_JARVIS.bat", "START_JARVIS.bat", "ATUALIZAR_JARVIS.bat",
            "DIAGNOSTICO_JARVIS.bat", "README_JARVIS.md", "CHANGELOG_JARVIS.md", "ARCHITECTURE_JARVIS.md",
            "PERFORMANCE_REPORT.md", "VOICE_DIAGNOSTICS.md", "TEST_REPORT.md", "TEST_JARVIS.py",
            "ultron/app.py", "ultron/hud/tardis.py", "assets/LEIA-ME.txt", "tests/test_tardis.py")
MAX_BYTES = 25 * 1024 * 1024


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z", "--", "."], cwd=PROJECT, capture_output=True, check=True)
    return sorted(p for p in out.stdout.decode("utf-8").split("\0") if p)


def excluded(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXCLUDE)


def build(out: Path) -> list[str]:
    files = [p for p in tracked_files() if not excluded(p) and (PROJECT / p).is_file()]
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel in files:
            info = zipfile.ZipInfo.from_file(PROJECT / rel, PREFIX + rel)
            info.compress_type = zipfile.ZIP_DEFLATED
            with (PROJECT / rel).open("rb") as handle:
                archive.writestr(info, handle.read(), compresslevel=9)
    partial.replace(out)
    return files


def unsafe_zip_path(name: str) -> bool:
    """Rejeita travessia Unix e separadores Windows mesmo quando a validação roda em Linux."""
    return name.startswith("/") or "\\" in name or ".." in Path(name).parts


def check(path: Path) -> list[str]:
    """Problemas encontrados no pacote (lista vazia = aprovado)."""
    problems = []
    if not path.is_file():
        return [f"pacote não encontrado: {path}"]
    if path.stat().st_size > MAX_BYTES:
        problems.append(f"pacote grande demais: {path.stat().st_size / 2 ** 20:.1f} MB")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            problems.append(f"arquivo corrompido no ZIP: {bad}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            problems.append("há caminhos duplicados no ZIP")
        for name in names:
            if unsafe_zip_path(name):
                problems.append(f"caminho inseguro no ZIP: {name}")
            if not name.startswith(PREFIX):
                problems.append(f"fora da pasta {PREFIX}: {name}")
            if any(token in name for token in FORBIDDEN):
                problems.append(f"não deveria estar no pacote: {name}")
        for required in REQUIRED:
            if PREFIX + required not in names:
                problems.append(f"falta no pacote: {required}")
        for name in names:
            if name.endswith(".bat"):
                data = archive.read(name)
                if b"\r\n" not in data or any(b > 127 for b in data):
                    problems.append(f"script .bat sem CRLF ou com caracteres não ASCII: {name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera e valida o JARVIS_FINAL.zip")
    parser.add_argument("--out", default=str(PROJECT.parent / "JARVIS_FINAL.zip"))
    parser.add_argument("--check", metavar="ZIP")
    args = parser.parse_args(argv)
    if args.check:
        target = Path(args.check)
    else:
        target = Path(args.out)
        files = build(target)
        print(f"{len(files)} arquivos em {target} ({target.stat().st_size / 2 ** 20:.2f} MB)")
    problems = check(target)
    for problem in problems:
        print("PROBLEMA:", problem)
    print("pacote APROVADO" if not problems else f"pacote REPROVADO ({len(problems)} problema(s))")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
