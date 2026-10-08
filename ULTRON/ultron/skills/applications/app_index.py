"""Índice dos programas instalados (menu Iniciar do Windows).

Preservado do JARVIS (onde estava escrito mas nunca conectado). O que o usuário ou o modelo
fornecem é apenas um NOME comparado com o índice; nunca vira comando — o programa é aberto
pelo atalho/AppID que já estava no índice.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import threading
import time

from ...config import paths
from ...platform import system
from .._util import norm

CONFIDENT = 0.82
REFRESH_MIN_INTERVAL = 120
_lock = threading.RLock()
_index: dict[str, dict] = {}
_last_refresh = 0.0

_START_APPS = "$ErrorActionPreference='Stop';Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
_SKIP = re.compile(r"\b(uninstall|desinstal\w*|remover|remove)\b")
_APPID_OK = re.compile(r"^[\w .!{}\\:()\-,+]+$", re.UNICODE)

ALIASES = {
    "chome": "chrome", "cromo": "chrome", "crome": "chrome", "grome": "chrome", "xrome": "chrome",
    "espotifai": "spotify", "spotifai": "spotify", "espotify": "spotify",
    "discorde": "discord", "discordi": "discord", "ecsel": "excel", "uord": "word", "edji": "edge",
    "peint": "paint", "vis code": "visual studio code", "vi esco de": "visual studio code",
    "vs code": "visual studio code", "uatsap": "whatsapp", "zap": "whatsapp", "estim": "steam",
    "zum": "zoom", "obs": "obs studio", "fotoxop": "photoshop", "calculador": "calculadora",
}


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", norm(text)).split())


def _cache_path():
    return paths.data_file("apps_index.json")


def _roots() -> list[str]:
    roots = []
    for var in ("ProgramData", "APPDATA"):
        base = os.environ.get(var)
        if base:
            roots.append(os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs"))
    return roots


def _build() -> dict[str, dict]:
    entries: dict[str, dict] = {}

    def add(name: str, kind: str, target: str) -> None:
        key = _key(name)
        if key and not _SKIP.search(key) and key not in entries:
            entries[key] = {"name": name.strip(), "kind": kind, "target": target}

    if system.IS_WINDOWS:
        result = system.powershell(_START_APPS, timeout=45)
        if result.ok and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                for item in data if isinstance(data, list) else [data]:
                    name, appid = str(item.get("Name") or ""), str(item.get("AppID") or "")
                    if name and appid and _APPID_OK.match(appid):
                        add(name, "appid", appid)
            except ValueError:
                pass
        for root in _roots():
            for folder, _dirs, files in os.walk(root):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        add(os.path.splitext(file)[0], "lnk", os.path.join(folder, file))
    return entries


def refresh(force: bool = False) -> int:
    global _last_refresh
    with _lock:
        if not force and time.time() - _last_refresh < 60:
            return len(_index)
        _last_refresh = time.time()
    entries = _build()
    if entries:
        with _lock:
            _index.clear()
            _index.update(entries)
        try:
            tmp = _cache_path().with_suffix(".tmp")
            tmp.write_text(json.dumps(list(entries.values()), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, _cache_path())
        except OSError:
            pass
    return len(_index)


def _load_cache() -> None:
    try:
        for entry in json.loads(_cache_path().read_text(encoding="utf-8")):
            _index.setdefault(_key(entry["name"]), entry)
    except (OSError, ValueError, KeyError):
        pass


def _match(query: str) -> tuple[dict | None, float]:
    keys = list(_index)
    if query in _index:
        return _index[query], 1.0
    words = set(query.split())
    subset = [k for k in keys if words and words <= set(k.split())]
    if subset:
        return _index[min(subset, key=len)], (0.95 if len(subset) == 1 else 0.8)
    starts = [k for k in keys if k.startswith(query)]
    if len(query) >= 3 and starts:
        best = min(starts, key=len)
        return _index[best], min(0.9, 0.6 + 0.4 * len(query) / len(best))
    close = difflib.get_close_matches(query, keys, n=1, cutoff=0.6)
    if close:
        return _index[close[0]], difflib.SequenceMatcher(None, query, close[0]).ratio()
    return None, 0.0


def find(spoken: str) -> tuple[dict | None, float]:
    query = _key(spoken)
    if len(query) < 2:
        return None, 0.0
    query = ALIASES.get(query, ALIASES.get(query.replace(" ", ""), query))
    with _lock:
        if not _index:
            _load_cache()
    if not _index:
        refresh(force=True)
    entry, score = _match(query)
    if (entry is None or score < CONFIDENT) and time.time() - _last_refresh > REFRESH_MIN_INTERVAL:
        refresh(force=True)
        entry, score = _match(query)
    return entry, score


def launch(entry: dict) -> None:
    kind, target = entry.get("kind"), entry.get("target", "")
    if kind == "appid":
        if not _APPID_OK.match(target):
            raise ValueError("identificador de aplicativo inválido")
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + target], creationflags=system.NO_WINDOW)
        return
    if kind == "lnk":
        real = os.path.realpath(target)
        roots = [os.path.realpath(r) for r in _roots()]
        if not real.lower().endswith(".lnk") or not any(real.lower().startswith(r.lower() + os.sep) for r in roots):
            raise ValueError("atalho fora do menu Iniciar")
        if not os.path.isfile(real):
            raise FileNotFoundError("o atalho não existe mais")
        os.startfile(real)  # type: ignore[attr-defined]
        return
    raise ValueError("tipo de entrada desconhecido")


def count() -> int:
    return len(_index)
