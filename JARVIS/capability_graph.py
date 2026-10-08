"""J.A.R.V.I.S. // CAPABILITY GRAPH
Grafo operacional que relaciona capacidades, ferramentas, evidências e estados.
Não executa ferramentas e não concede permissões.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import capability_discovery
import capability_model

@dataclass(frozen=True)
class GraphNode:
    kind: str
    name: str
    data: dict
    def to_dict(self): return asdict(self)


def build():
    nodes, edges = [], []
    seen = set()
    def add(kind, name, data=None):
        key=(kind,name)
        if key not in seen:
            seen.add(key); nodes.append(GraphNode(kind,name,data or {}))
    for cap in capability_model.all_capabilities():
        add("capability", cap["name"], {"description":cap["description"],"risk":cap["risk"]})
        for ev in cap.get("evidence", ()):
            add("evidence", ev); edges.append({"from":("capability",cap["name"]),"to":("evidence",ev),"relation":"produces"})
    for item in capability_discovery.catalog():
        tool=item["tool"]; add("tool",tool,{"description":item["description"],"risk":item["risk"],"available":item.get("available",True)})
        for cap in item.get("capabilities", ()):
            add("capability",cap); edges.append({"from":("tool",tool),"to":("capability",cap),"relation":"provides"})
    return {"nodes":[n.to_dict() for n in nodes],"edges":edges}


def tools_for(capabilities, *, max_tools=12, risk=None):
    wanted={str(x) for x in (capabilities or ())}
    result=[]
    for item in capability_discovery.catalog():
        if wanted.intersection(item.get("capabilities", ())):
            if risk and item.get("risk") not in risk: continue
            result.append(item)
    result.sort(key=lambda x:(x.get("risk")!="low", x["tool"]))
    return result[:max(1,int(max_tools))]


def capabilities_for(tool_name):
    item=capability_discovery.by_tool(tool_name)
    return list(item.get("capabilities",())) if item else []


def summary():
    g=build();
    return {"nodes":len(g["nodes"]),"edges":len(g["edges"]),
            "tools":sum(n["kind"]=="tool" for n in g["nodes"]),
            "capabilities":sum(n["kind"]=="capability" for n in g["nodes"]),
            "evidence":sum(n["kind"]=="evidence" for n in g["nodes"])}
