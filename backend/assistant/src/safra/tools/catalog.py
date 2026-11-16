"""Ferramentas cadastradas e execuções registradas. Nesta fase não há executor: nada é executado."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage.models import Tool, ToolExecution

EXECUTOR = {
    "situacao": "nao_implementado",
    "fase": 7,
    "mensagem": "O executor de ferramentas ainda não existe: o SAFRA não executa nenhuma ação no computador.",
}


def overview(db: Session) -> dict[str, Any]:
    tools = db.scalars(select(Tool).order_by(Tool.category, Tool.name))
    executions = db.scalars(select(ToolExecution).order_by(ToolExecution.requested_at.desc()).limit(20))
    return {
        "executor": EXECUTOR,
        "tools": [{"name": t.name, "category": t.category, "risk": t.risk, "enabled": t.enabled, "description": t.description}
                  for t in tools],
        "executions": [{"id": e.id, "tool": e.tool_name, "status": e.status, "verified": e.verified,
                        "requested_at": e.requested_at.isoformat()} for e in executions],
    }
