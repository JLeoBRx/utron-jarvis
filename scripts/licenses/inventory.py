"""Inventário de licenças das dependências da nova geração do SAFRA (diretas e transitivas).

Lê o que está INSTALADO/TRAVADO — não o que se imagina usar:
* Python: os pacotes do ambiente onde este script roda (instale antes: foundation, assistant[dev], portal[dev,postgres]);
* npm: apps/admin/package-lock.json e os package.json em apps/admin/node_modules;
* Rust: `cargo metadata --locked` em desktop/poc-tauri.

Gera docs/engineering/licenses/{python,npm,rust}.csv e imprime o resumo por licença.
Uso:  python scripts/licenses/inventory.py
"""
from __future__ import annotations

import collections
import csv
import json
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "engineering" / "licenses"
OWN = {"safra-foundation", "safra-assistant", "safra-portal", "safra-poc-tauri"}
ROLES = {  # papel de cada pacote próprio; a dependência herda o papel de quem a pede
    "safra-foundation": "Assistant e Portal (execução)",
    "safra-assistant": "Assistant (execução, distribuído no instalador)",
    "safra-portal": "Portal (execução no servidor, não distribuído)",
}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    declared = (meta.get("License") or "").strip().splitlines()[0][:80] if meta.get("License") else ""
    if classifiers:
        return " / ".join(classifiers)
    return declared or "NÃO DECLARADA"


def requirements(dist: metadata.Distribution, extras: set[str]) -> list[str]:
    """Nomes pedidos por ``dist`` com os ``extras`` dados. Marcadores de plataforma são mantidos (inventário
    conservador); um pedido como ``psycopg[binary]`` traz junto os pedidos do extra ``binary``."""
    names = []
    for requirement in dist.requires or []:
        spec, _, marker = requirement.partition(";")
        extra = re.search(r"extra\s*==\s*['\"]([^'\"]+)['\"]", marker)
        if extra and extra.group(1) not in extras:
            continue
        match = re.match(r"\s*([A-Za-z0-9_.\-]+)\s*(?:\[([^\]]+)\])?", spec)
        if not match:
            continue
        name = normalize(match.group(1))
        names.append(name)
        if match.group(2):
            try:
                inner = metadata.distribution(name)
            except metadata.PackageNotFoundError:
                continue
            wanted = {e.strip() for e in match.group(2).split(",")}
            names += [n for n in requirements(inner, wanted) if n not in requirements(inner, set())]
    return names


def python_rows() -> list[dict]:
    installed = {normalize(d.metadata["Name"]): d for d in metadata.distributions()}
    rows: dict[str, dict] = {}
    for own, role in ROLES.items():
        if own not in installed:
            print(f"aviso: {own} não está instalado neste ambiente", file=sys.stderr)
            continue
        for extras, kind in ((set(), "execução"), ({"dev"}, "desenvolvimento"), ({"postgres"}, "execução (produção do Portal)")):
            direct = [n for n in requirements(installed[own], extras) if n not in OWN]
            if extras:
                direct = [n for n in direct if n not in requirements(installed[own], set())]
            queue = [(n, True) for n in direct]
            seen = set()
            while queue:
                name, is_direct = queue.pop()
                if name in seen or name not in installed:
                    continue
                seen.add(name)
                dist = installed[name]
                row = rows.setdefault(name, {"pacote": dist.metadata["Name"], "versão": dist.version,
                                             "licença": python_license(dist), "direta_de": set(), "usada_por": set(), "tipo": set()})
                row["usada_por"].add(role)
                row["tipo"].add(kind)
                if is_direct:
                    row["direta_de"].add(own)
                queue += [(n, False) for n in requirements(dist, set()) if n not in OWN]
    return [{**r, "direta_de": ", ".join(sorted(r["direta_de"])) or "transitiva", "usada_por": "; ".join(sorted(r["usada_por"])),
             "tipo": ", ".join(sorted(r["tipo"]))} for r in sorted(rows.values(), key=lambda r: r["pacote"].lower())]


def npm_rows() -> list[dict]:
    lock = json.loads((REPO / "apps" / "admin" / "package-lock.json").read_text(encoding="utf-8"))
    root = lock["packages"][""]
    direct = set(root.get("dependencies", {})) | set(root.get("devDependencies", {}))
    rows = []
    for path, info in lock["packages"].items():
        if not path.startswith("node_modules/"):
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        rows.append({"pacote": name, "versão": info.get("version", ""), "licença": info.get("license", "NÃO DECLARADA"),
                     "direta_de": "painel" if name in direct and path.count("node_modules/") == 1 else "transitiva",
                     "usada_por": "painel administrativo",
                     "tipo": "desenvolvimento (não vai para o navegador)" if info.get("dev") else "incluída na compilação entregue ao navegador"})
    return sorted(rows, key=lambda r: r["pacote"])


def rust_rows() -> list[dict]:
    folder = REPO / "desktop" / "poc-tauri"
    data = json.loads(subprocess.run(["cargo", "metadata", "--format-version", "1", "--locked"], cwd=folder,
                                     capture_output=True, text=True, check=True).stdout)
    root = next(p for p in data["packages"] if p["name"] == "safra-poc-tauri")
    direct = {d["name"] for d in root["dependencies"]}
    rows = []
    for package in data["packages"]:
        if package["name"] in OWN:
            continue
        rows.append({"pacote": package["name"], "versão": package["version"], "licença": package.get("license") or "NÃO DECLARADA",
                     "direta_de": "prova de conceito" if package["name"] in direct else "transitiva",
                     "usada_por": "prova de conceito da casca (não distribuída)",
                     "tipo": "compilada no executável (o arquivo de trava inclui todas as plataformas)"})
    return sorted(rows, key=lambda r: (r["pacote"], r["versão"]))


def write(name: str, rows: list[dict]) -> collections.Counter:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pacote", "versão", "licença", "direta_de", "usada_por", "tipo"])
        writer.writeheader()
        writer.writerows(rows)
    counter = collections.Counter(r["licença"] for r in rows)
    print(f"\n{name}: {len(rows)} pacotes ({sum(1 for r in rows if r['direta_de'] != 'transitiva')} diretos)")
    for license_name, count in counter.most_common():
        print(f"  {count:4d}  {license_name}")
    return counter


def main() -> int:
    write("python", python_rows())
    write("npm", npm_rows())
    try:
        write("rust", rust_rows())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"\nrust: não foi possível ler (cargo ausente?): {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
