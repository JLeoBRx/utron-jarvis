"""Gera `tokens.css` a partir de `tokens.json` (fonte única da identidade visual) e o copia para quem usa:
o site público do Portal e o painel administrativo. Uso: python packages/design-tokens/build.py [--check]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TARGETS = (REPO / "backend" / "portal" / "src" / "safra_portal" / "static" / "css" / "tokens.css",
           REPO / "apps" / "admin" / "src" / "tokens.css")
PREFIX = {"color": "cor", "space": "espaco", "radius": "raio", "font": "fonte", "motion": "tempo"}


def load() -> dict:
    return json.loads((HERE / "tokens.json").read_text(encoding="utf-8"))


def luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    a, b = luminance(first), luminance(second)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def css(tokens: dict) -> str:
    lines = ["/* GERADO por packages/design-tokens/build.py a partir de tokens.json. Não edite este arquivo. */", ":root {"]
    for group, prefix in PREFIX.items():
        for name, value in tokens[group].items():
            lines.append(f"  --{prefix}-{name}: {value};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    tokens = load()
    text = css(tokens)
    if "--check" in argv:
        stale = [str(t.relative_to(REPO)) for t in TARGETS if t.parent.is_dir() and (not t.is_file() or t.read_text(encoding="utf-8") != text)]
        if stale:
            print("desatualizados: " + ", ".join(stale))
            return 1
        return 0
    for target in TARGETS:
        if target.parent.is_dir():
            target.write_text(text, encoding="utf-8")
            print("gerado", target.relative_to(REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
