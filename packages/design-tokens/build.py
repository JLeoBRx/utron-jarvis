"""Gera os artefatos da identidade visual a partir da fonte única (`tokens.json`, `icons.json`, `symbol.json`,
`fonts/`) e os copia para quem usa: o pacote npm `@safra/design-tokens` (painel e interface do Assistant) e o
site público do Portal, que é Python e não passa pelo npm.

Uso: python packages/design-tokens/build.py [--check]
"""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GENERATED = HERE / "generated"
PORTAL = REPO / "backend" / "portal" / "src" / "safra_portal"
FONTS = ("inter-latin-wght-normal.woff2", "jetbrains-mono-latin-wght-normal.woff2",
         "OFL-inter.txt", "OFL-jetbrains-mono.txt")
FONT_FACES = (("Inter Variable", "inter-latin-wght-normal.woff2"),
              ("JetBrains Mono Variable", "jetbrains-mono-latin-wght-normal.woff2"))
LATIN = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,"
         "U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD")
PREFIX = {"color": "cor", "space": "espaco", "radius": "raio", "font": "fonte", "shadow": "sombra",
          "motion": "tempo", "easing": "curva", "layer": "camada", "width": "largura", "size": "medida"}
HEADER = "GERADO por packages/design-tokens/build.py a partir da fonte única. Não edite este arquivo."


def load() -> dict:
    return json.loads((HERE / "tokens.json").read_text(encoding="utf-8"))


def load_icons() -> dict:
    return {k: v for k, v in json.loads((HERE / "icons.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}


def load_symbol() -> dict:
    return {k: v for k, v in json.loads((HERE / "symbol.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}


def luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    a, b = luminance(first), luminance(second)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# ------------------------------------------------------------------ CSS
def css(tokens: dict) -> str:
    lines = [f"/* {HEADER} */", ":root {"]
    for group, prefix in PREFIX.items():
        for name, value in tokens[group].items():
            lines.append(f"  --{prefix}-{name}: {value};")
    for role, spec in tokens["type"].items():
        lines.append(f"  --tipo-{role}: {spec['peso']} {spec['tamanho']}/{spec['linha']} var(--fonte-{spec['fonte']});")
        lines.append(f"  --tipo-{role}-espacamento: {spec['espacamento']};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def fonts_css() -> str:
    faces = [f"/* {HEADER} */", "/* Fontes sob a SIL Open Font License 1.1 (OFL-*.txt, ao lado dos arquivos). */"]
    for family, file in FONT_FACES:
        faces.append("@font-face {\n"
                     f"  font-family: \"{family}\";\n  font-style: normal;\n  font-display: swap;\n"
                     f"  font-weight: 100 900;\n  src: url(\"../fonts/{file}\") format(\"woff2-variations\"),\n"
                     f"       url(\"../fonts/{file}\") format(\"woff2\");\n  unicode-range: {LATIN};\n}}")
    return "\n".join(faces) + "\n"


# ------------------------------------------------------------------ TypeScript
def tokens_ts(tokens: dict) -> str:
    public = {k: v for k, v in tokens.items() if k != "contrast"}
    return (f"// {HEADER}\n"
            f"export const tokens = {json.dumps(public, ensure_ascii=False, indent=2)} as const;\n\n"
            "/** Larguras em que o leiaute muda (px), as mesmas das regras de CSS. */\n"
            "export const breakpoints = { estreita: 600, media: 900, larga: 1200, maxima: 1600 } as const;\n")


def icons_ts(icons: dict) -> str:
    names = " | ".join(json.dumps(n) for n in icons)
    body = json.dumps(icons, ensure_ascii=False, indent=2)
    return (f"// {HEADER}\n"
            "export type IconTag = \"path\" | \"circle\" | \"rect\" | \"ellipse\";\n"
            "export type IconNode = readonly [IconTag, Readonly<Record<string, string>>];\n"
            f"export type IconName = {names};\n"
            f"export const ICONS: Readonly<Record<IconName, readonly IconNode[]>> = {body} as const;\n")


def symbol_ts(symbol: dict) -> str:
    return f"// {HEADER}\nexport const SYMBOL = {json.dumps(symbol, ensure_ascii=False, indent=2)} as const;\n"


# ------------------------------------------------------------------ SVG e Jinja para o Portal
def _attrs(attrs: dict) -> str:
    return " ".join(f'{k}="{escape(str(v))}"' for k, v in attrs.items())


def icons_sprite(icons: dict) -> str:
    parts = ['<svg xmlns="http://www.w3.org/2000/svg">', f"<!-- {HEADER} -->"]
    for name, nodes in icons.items():
        inner = "".join(f"<{tag} {_attrs(attrs)}/>" for tag, attrs in nodes)
        parts.append(f'<symbol id="{name}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" '
                     f'stroke-linecap="round" stroke-linejoin="round">{inner}</symbol>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def symbol_svg(symbol: dict, tokens: dict) -> str:
    color, icon = tokens["color"], symbol["icone"]
    lines = "".join(f'<path d="{d}" opacity="{symbol["opacidades"][i]}"/>' for i, d in enumerate(icon["sulcos"]))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{symbol["viewBox"]}" role="img" aria-label="SAFRA">'
            f'<!-- {HEADER} -->'
            f'<rect {_attrs(symbol["profundidade"])} fill="{color["vermelho-profundo"]}"/>'
            f'<rect {_attrs(symbol["placa"])} fill="{color["superficie"]}" stroke="{color["borda"]}"/>'
            f'<g fill="none" stroke="{color["vermelho"]}" stroke-linecap="round" stroke-width="{icon["espessura"]}">'
            f"{lines}</g></svg>\n")


def symbol_macro(symbol: dict) -> str:
    def group(paths: list[str], width: float) -> str:
        return (f'<g class="simbolo__sulcos" fill="none" stroke-linecap="round" stroke-width="{width}">'
                + "".join(f'<path class="sulco sulco--{i + 1}" d="{d}"/>' for i, d in enumerate(paths)) + "</g>")
    head = (f'<svg class="simbolo simbolo--{{{{ size }}}}{{% if state %}} simbolo--{{{{ state }}}}{{% endif %}}" '
            f'viewBox="{symbol["viewBox"]}" xmlns="http://www.w3.org/2000/svg" '
            '{% if label %}role="img" aria-label="{{ label }}"{% else %}aria-hidden="true" focusable="false"{% endif %}>')
    plates = (f'<rect class="simbolo__fundo" {_attrs(symbol["profundidade"])}/>'
              f'<rect class="simbolo__placa" {_attrs(symbol["placa"])}/>')
    return (f"{{# {HEADER} #}}\n"
            "{# Símbolo do SAFRA (estudo \"Sulcos\"). Tamanho \"pequeno\" usa a versão de ícone, com três sulcos. #}\n"
            '{% macro symbol(size="medio", label="", state="") %}\n'
            f"{head}{plates}\n"
            f'{{% if size == "pequeno" %}}{group(symbol["icone"]["sulcos"], symbol["icone"]["espessura"])}'
            f'{{% else %}}{group(symbol["sulcos"], symbol["espessura"])}{{% endif %}}\n'
            "</svg>\n{% endmacro %}\n")


# ------------------------------------------------------------------ saída
def outputs() -> dict[Path, bytes]:
    tokens, icons, symbol = load(), load_icons(), load_symbol()
    text = {
        GENERATED / "tokens.css": css(tokens),
        GENERATED / "fonts.css": fonts_css(),
        GENERATED / "tokens.ts": tokens_ts(tokens),
        GENERATED / "icons.ts": icons_ts(icons),
        GENERATED / "symbol.ts": symbol_ts(symbol),
        GENERATED / "symbol.svg": symbol_svg(symbol, tokens),
        PORTAL / "static" / "css" / "tokens.css": css(tokens),
        PORTAL / "static" / "css" / "fonts.css": fonts_css(),
        PORTAL / "static" / "img" / "symbol.svg": symbol_svg(symbol, tokens),
        PORTAL / "static" / "img" / "icons.svg": icons_sprite(icons),
        PORTAL / "templates" / "_symbol.html": symbol_macro(symbol),
    }
    result = {path: value.encode("utf-8") for path, value in text.items()}
    for name in FONTS:
        result[PORTAL / "static" / "fonts" / name] = (HERE / "fonts" / name).read_bytes()
    return result


def main(argv: list[str]) -> int:
    files = outputs()
    if "--check" in argv:
        stale = [str(p.relative_to(REPO)) for p, data in files.items() if not p.is_file() or p.read_bytes() != data]
        if stale:
            print("desatualizados: " + ", ".join(stale))
            return 1
        return 0
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
            print("gerado", path.relative_to(REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
