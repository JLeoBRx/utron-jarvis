"""A biblioteca de base não conhece nenhum dos dois serviços."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "safra_foundation"
SERVICES = {"safra", "safra_portal"}


def test_foundation_imports_neither_service():
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = [node.module or ""]
            assert not {name.split(".")[0] for name in names} & SERVICES, f"{path.name} importa um serviço"


def test_foundation_has_no_routes_and_no_tables_of_its_own():
    text = "".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.py"))
    assert "@app.get(" not in text and "@app.post(" not in text and "create_table(" not in text
