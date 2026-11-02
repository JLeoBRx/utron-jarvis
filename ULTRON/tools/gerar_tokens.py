"""Gera ``ultron/hud/scene3d/web/css/tokens.css`` a partir de ``ultron/hud/design/tokens.json`` (fonte única).

    python tools/gerar_tokens.py            # grava o CSS
    python tools/gerar_tokens.py --check    # só confere se o CSS está em dia (usado pelos testes)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "ultron" / "hud" / "design" / "tokens.json"
CSS = ROOT / "ultron" / "hud" / "scene3d" / "web" / "css" / "tokens.css"


def render() -> str:
    data = json.loads(TOKENS.read_text(encoding="utf-8"))
    lines = ["/* Gerado por tools/gerar_tokens.py a partir de ultron/hud/design/tokens.json — não edite à mão. */",
             ":root {"]
    for group, values in data.items():
        if group.startswith("_"):
            continue
        for key, value in values.items():
            lines.append(f"  --{group}-{key.replace('_', '-')}: {value};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    css = render()
    if "--check" in sys.argv:
        current = CSS.read_text(encoding="utf-8") if CSS.exists() else ""
        if current != css:
            print("tokens.css desatualizado: rode python tools/gerar_tokens.py")
            return 1
        print("tokens.css em dia")
        return 0
    CSS.write_text(css, encoding="utf-8")
    print(f"gravado {CSS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
