"""J.A.R.V.I.S. // SKILL SYSTEM (Fase 33)
Skills são descrições declarativas de capacidades. Registrar uma skill não
concede autorização de execução.
"""
from __future__ import annotations
import threading

_LOCK=threading.RLock(); _SKILLS={}


def register(name, *, capabilities=(), tools=(), description="", risk="low"):
    key=str(name).strip().lower()
    if not key: raise ValueError("nome da skill vazio")
    item={"name":key,"capabilities":sorted({str(x) for x in capabilities}),
          "tools":sorted({str(x) for x in tools}),"description":str(description)[:500],
          "risk":str(risk)}
    with _LOCK: _SKILLS[key]=item
    return dict(item)


def discover():
    with _LOCK: return [dict(x) for x in _SKILLS.values()]


def find_for(capability):
    cap=str(capability).strip()
    with _LOCK:
        return [dict(x) for x in _SKILLS.values() if cap in x["capabilities"]]


def snapshot():
    with _LOCK: return {k:dict(v) for k,v in _SKILLS.items()}


def bootstrap():
    register("vision", capabilities=("read_screen","understand_ui"), tools=("take_screenshot","ocr_screen"), description="Percepção visual e OCR", risk="low")
    register("windows", capabilities=("inspect_windows","control_ui"), tools=("open_app","focus_window"), description="Estado e controle estrutural do Windows", risk="medium")
    register("files", capabilities=("search_files","inspect_files"), tools=("search_files",), description="Localização e inspeção de arquivos", risk="low")
    register("browser", capabilities=("navigate_web","search_web"), tools=("open_url","search_web"), description="Navegação web permitida", risk="medium")
    register("computer", capabilities=("interact_ui","keyboard_input"), tools=("click","type_text","hotkey"), description="Mouse e teclado", risk="medium")
    return discover()
