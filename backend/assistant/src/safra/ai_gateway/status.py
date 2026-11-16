"""Estado do gateway de IA. Nesta fase ele NÃO existe: o Assistant não gera respostas e diz isso, sem simular."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage.models import AiProvider

UNAVAILABLE = {
    "situacao": "nao_implementado",
    "fase": 5,
    "mensagem": "O gateway de IA ainda não foi implementado: o SAFRA ainda não gera respostas. "
                "Suas mensagens são guardadas no seu computador e ficam na conversa.",
}


def gateway_status(db: Session) -> dict[str, Any]:
    providers = db.scalars(select(AiProvider).order_by(AiProvider.priority, AiProvider.name))
    return {
        "gateway": UNAVAILABLE,
        # nunca o segredo nem o nome dele no cofre: só se há uma credencial associada
        "providers": [{"id": p.id, "name": p.name, "kind": p.kind, "enabled": p.enabled, "default_model": p.default_model,
                       "allows_private": p.allows_private, "has_credential": bool(p.credential_ref)} for p in providers],
        "selection_allowed": False,
    }
