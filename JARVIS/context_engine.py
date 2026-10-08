"""J.A.R.V.I.S. // CONTEXT ENGINE
Consolida percepções em um estado de contexto temporal.
Não executa ações e não trata texto da tela como instrução.
"""
from __future__ import annotations
import re, time
from collections import deque

_HISTORY = deque(maxlen=32)
_LAST = None

APP_ALIASES = {
    "code.exe":"Visual Studio Code", "chrome.exe":"Chrome", "msedge.exe":"Edge",
    "devenv.exe":"Visual Studio", "idea64.exe":"IntelliJ IDEA", "explorer.exe":"Explorer",
}
ERROR_RE = re.compile(r"erro|error|exception|traceback|failed|falha|crash|não responde|not responding|fatal", re.I)
DEV_RE = re.compile(r"code|código|python|javascript|typescript|java|c#|unity|arduino|esp32|terminal|debug|projeto|programa|compile|build", re.I)
WORK_RE = re.compile(r"document|word|excel|powerpoint|planilha|email|outlook|navegador|browser|arquivo", re.I)

def _txt(v, n=260):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]

def _app(fg):
    p = _txt(fg.get("process"), 100).lower()
    return APP_ALIASES.get(p) or _txt(fg.get("title"), 120) or p or "aplicativo desconhecido"

def update(package):
    global _LAST
    now=time.time(); fg=package.get("foreground",{}); obs=package.get("observation",{}); ev=package.get("evidence",{})
    text=" ".join([_txt(fg.get("title")), _txt(obs.get("atividade")), _txt(obs.get("resumo")), _txt(obs.get("erro_texto")), _txt(ev.get("summary"))])
    error=bool(obs.get("erro_visivel") or ERROR_RE.search(text))
    development=bool(DEV_RE.search(text))
    work=bool(WORK_RE.search(text))
    app=_app(fg)
    signature=(str(fg.get("process","")).lower(), str(fg.get("title","")).lower(), error, development)
    changed=bool(package.get("evidence",{}).get("context_change"))
    continuity = _LAST is not None and _LAST.get("signature")==signature
    if continuity:
        duration=now-_LAST.get("started",now)
    else:
        duration=0.0
    item={"timestamp":now,"app":app,"process":_txt(fg.get("process"),100),"title":_txt(fg.get("title"),180),
          "error":error,"development":development,"work":work,"changed":changed,"continuity":continuity,
          "duration":round(duration,1),"summary":_txt(ev.get("summary") or obs.get("resumo"),600)}
    if not continuity: item["started"]=now
    else: item["started"]=_LAST.get("started",now)
    _HISTORY.append(item); _LAST={"signature":signature,"started":item["started"]}
    return item

def history(limit=10): return list(_HISTORY)[-max(1,min(int(limit),32)):]

def snapshot(): return dict(_LAST or {}), history(10)

def consolidated(package):
    current=update(package); recent=history(8)
    apps=[x["app"] for x in recent if x.get("app")]
    repeated=max(set(apps), key=apps.count) if apps else current["app"]
    errors=sum(1 for x in recent if x.get("error"))
    return {"current":current,"recent":recent,"dominant_app":repeated,"error_count":errors,
            "stable_context":current["continuity"] and current["duration"]>=8}
