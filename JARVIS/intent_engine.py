"""J.A.R.V.I.S. // INTENT ENGINE
Inferência conservadora de intenção/objetivo a partir do contexto.
É deliberadamente separada do executor: inferir não significa executar.
"""
from __future__ import annotations
import re

ERROR_RE=re.compile(r"erro|error|exception|traceback|failed|falha|crash|não responde|not responding",re.I)
DEV_RE=re.compile(r"code|código|python|javascript|typescript|java|unity|arduino|esp32|terminal|debug|projeto|build|compile",re.I)

def infer(context, explicit_text=""):
    c=context.get("current",{}); recent=context.get("recent",[])
    text=" ".join([c.get("title",""),c.get("summary",""),explicit_text])
    evidence=[]
    if c.get("error") or ERROR_RE.search(text):
        goal=f"Investigar o erro observado em {c.get('app','aplicativo atual')} e, se seguro e permitido, corrigi-lo."
        kind="troubleshooting"; confidence=.88
        evidence.append("erro observável")
    elif DEV_RE.search(text) or c.get("development"):
        goal=f"Acompanhar o trabalho de desenvolvimento em {c.get('app','aplicativo atual')} e intervir somente quando houver uma necessidade clara."
        kind="development"; confidence=.70
        evidence.append("contexto de desenvolvimento")
    elif c.get("work"):
        goal=f"Acompanhar o trabalho atual em {c.get('app','aplicativo atual')} sem interromper desnecessariamente."
        kind="work"; confidence=.58
        evidence.append("contexto de trabalho")
    else:
        goal="Acompanhar o contexto atual e não agir sem evidência suficiente de uma necessidade."
        kind="observe"; confidence=.45
    stability=1.0 if c.get("stable_context") else .7
    confidence=round(min(0.98, confidence*stability + (0.04 if len(recent)>=3 else 0)),2)
    actionability=kind in {"troubleshooting"}
    return {"kind":kind,"goal":goal,"confidence":confidence,"actionable":actionability,
            "evidence":evidence,"reason":"; ".join(evidence) or "contexto insuficiente",
            "requires_confirmation":False if kind=="troubleshooting" else True}
