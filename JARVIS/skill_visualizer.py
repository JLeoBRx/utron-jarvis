"""J.A.R.V.I.S. // Fase 39 — Skill Visualizer
Traduz Skills registradas em módulos visuais. Registro não implica execução.
"""
from __future__ import annotations

def active_skill_modules(skills):
    result=[]
    for skill in skills or []:
        name=str(skill.get("name","")).upper()
        if name: result.append(name[:14])
    return sorted(set(result))
