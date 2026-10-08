"""J.A.R.V.I.S. // TOOL REGISTRY
Registro unificado de ferramentas, capacidades, risco e evidências.
O registry descreve o sistema; a allowlist em tools.py continua sendo a autoridade de execução.
"""
from __future__ import annotations
import capability_discovery
import capability_graph


def snapshot():
    items=capability_discovery.catalog()
    return {"tools":items,"graph":capability_graph.build(),"validation":capability_discovery.validate()}


def get(tool_name):
    return capability_discovery.by_tool(tool_name)


def candidates(capabilities, *, max_tools=8, safe_only=False):
    risk = {"low"} if safe_only else None
    return capability_graph.tools_for(capabilities,max_tools=max_tools,risk=risk)


def capabilities(tool_name):
    return capability_graph.capabilities_for(tool_name)


def validate():
    return capability_discovery.validate()
