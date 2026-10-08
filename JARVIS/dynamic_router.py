"""J.A.R.V.I.S. // DYNAMIC ROUTER (Fase 35)
Roteamento baseado em complexidade, modalidade, disponibilidade e histórico.
Ollama local continua sendo fallback padrão.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import os
import config

@dataclass
class DynamicRoute:
    route:str; model:str; reason:str; confidence:float; fallback:str="OLLAMA_LOCAL"
    def to_dict(self): return asdict(self)

def _complexity(goal, context):
    text=str(goal or "").lower(); score=0.2
    score += min(0.35, len(text)/1200)
    for marker in ("depure","investigue","implemente","integre","compare","planeje","corrija"):
        if marker in text: score += .08
    if context.get("visual") or context.get("windows"): score += .08
    if context.get("memory"): score += .03
    return min(1.0,score)

def decide(goal, context=None, *, prefer_local=True):
    context=context or {}; c=_complexity(goal,context)
    openai=bool(getattr(config,"OPENAI_ENABLED",False) and os.environ.get("OPENAI_API_KEY"))
    if openai and not prefer_local and c>=.70:
        return DynamicRoute("OPENAI",getattr(config,"OPENAI_MODEL",""),"complexidade alta e provedor remoto explicitamente permitido",.86)
    return DynamicRoute("OLLAMA_LOCAL",getattr(config,"OLLAMA_MODEL",""),"local é a rota padrão e preserva autonomia sem custo de API",.92)
