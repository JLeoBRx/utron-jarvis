from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
ASSISTANT_SRC = BACKEND / "assistant" / "src" / "safra"
PORTAL_SRC = BACKEND / "portal" / "src" / "safra_portal"
FOUNDATION_SRC = BACKEND / "foundation" / "src" / "safra_foundation"
