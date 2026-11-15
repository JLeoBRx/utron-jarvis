"""A identidade visual tem fonte única e respeita o contraste mínimo (WCAG 2.x)."""
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("tokens_build", REPO / "packages" / "design-tokens" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
TOKENS = build.load()
AUTHOR_PALETTE = {"fundo": "#101114", "superficie": "#191B20", "superficie-elevada": "#23262D", "vermelho": "#E32636",
                  "vermelho-profundo": "#8F1725", "texto": "#F2F2F2", "texto-secundario": "#A6A8AF"}


def test_the_seven_colours_defined_by_the_author_are_untouched():
    for name, value in AUTHOR_PALETTE.items():
        assert TOKENS["color"][name] == value, name


def test_every_declared_pair_meets_its_minimum_contrast():
    assert len(TOKENS["contrast"]) >= 20
    for pair in TOKENS["contrast"]:
        ratio = build.contrast(TOKENS["color"][pair["texto"]], TOKENS["color"][pair["fundo"]])
        assert ratio >= pair["minimo"], f'{pair["texto"]} sobre {pair["fundo"]}: {ratio:.2f} < {pair["minimo"]}'


def test_generated_css_is_in_sync_with_the_source():
    assert build.main(["--check"]) == 0


def test_stylesheets_use_tokens_instead_of_loose_colours():
    """Nos estilos, cor só vem de variável. Exceções: transparências em rgba() e o arquivo de tokens gerado."""
    sheets = [REPO / "backend" / "portal" / "src" / "safra_portal" / "static" / "css" / "site.css"]
    admin = REPO / "apps" / "admin" / "src"
    if admin.is_dir():
        sheets += [p for p in admin.rglob("*.css") if p.name != "tokens.css"]
    for sheet in sheets:
        text = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S)
        loose = re.findall(r"#[0-9a-fA-F]{3,8}\b", text)
        assert not loose, f"{sheet.name}: cores fora dos tokens {sorted(set(loose))}"
