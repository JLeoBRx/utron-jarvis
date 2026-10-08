"""
J.A.R.V.I.S. // índice dos programas instalados (menu Iniciar do Windows)

Permite abrir QUALQUER programa instalado pelo nome falado, sem lista fixa:
  * fonte principal: Get-StartApps (apps clássicos e da Microsoft Store), script FIXO;
  * fonte secundária: atalhos .lnk das pastas do menu Iniciar;
  * o que o usuário/modelo fornece é só um NOME, que é comparado com o índice;
    nunca vira comando: o programa é aberto pelo atalho/AppID que já estava no índice.

find(nome) -> (entrada | None, confiança 0..1)
launch(entrada) abre o programa.
"""
import base64
import difflib
import json
import os
import re
import subprocess
import threading
import time
import unicodedata

import config

CONFIDENT = 0.82                 # abaixo disso o JARVIS pergunta "quer dizer X?"
REFRESH_MIN_INTERVAL = 120       # segundos entre varreduras forçadas por "não achei"
_NO_WINDOW = 0x08000000
_lock = threading.RLock()
_index = {}                      # nome normalizado -> {"name", "kind", "target"}
_last_refresh = 0.0
_refreshing = False

_START_APPS_SCRIPT = (
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$ErrorActionPreference='Stop';"
    "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
)
_SKIP = re.compile(r"\b(uninstall|desinstal\w*|remover|remove)\b")
_APPID_OK = re.compile(r"^[\w .!{}\\:()\-,+]+$", re.UNICODE)

# Como o reconhecedor em português costuma "ouvir" nomes em inglês.
ALIASES = {
    "chome": "chrome", "cromo": "chrome", "crome": "chrome", "grome": "chrome", "xrome": "chrome",
    "chorme": "chrome", "crom": "chrome", "gugou crome": "chrome",
    "espotifai": "spotify", "spotifai": "spotify", "espotify": "spotify",
    "discorde": "discord", "discordi": "discord",
    "ecsel": "excel", "uord": "word", "uorde": "word", "edji": "edge",
    "peint": "paint", "painte": "paint",
    "vis code": "visual studio code", "vi esco de": "visual studio code", "vs code": "visual studio code",
    "uatsap": "whatsapp", "uotsap": "whatsapp", "uatizape": "whatsapp", "zap": "whatsapp",
    "estim": "steam", "stim": "steam", "zum": "zoom", "obs": "obs studio",
    "fotoxop": "photoshop", "fotochope": "photoshop", "netfliquis": "netflix",
    "calculador": "calculadora", "bloco": "bloco de notas",
}


def _norm(text):
    value = unicodedata.normalize("NFD", str(text).lower())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


def _cache_path():
    return os.path.join(config.db_dir(), "apps_index.json")


def _start_menu_roots():
    roots = []
    for var in ("ProgramData", "APPDATA"):
        base = os.environ.get(var)
        if base:
            roots.append(os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs"))
    return roots


def _get_start_apps():
    encoded = base64.b64encode(_START_APPS_SCRIPT.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        capture_output=True, timeout=45, creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[:200])
    data = json.loads(result.stdout.decode("utf-8", "replace") or "[]")
    if isinstance(data, dict):
        data = [data]
    return [(str(d.get("Name") or ""), str(d.get("AppID") or "")) for d in data]


def _scan_lnk():
    found = []
    for root in _start_menu_roots():
        for folder, _dirs, files in os.walk(root):
            for file in files:
                if file.lower().endswith(".lnk"):
                    found.append((os.path.splitext(file)[0], os.path.join(folder, file)))
    return found


def _build():
    entries = {}

    def add(name, kind, target):
        key = _norm(name)
        if key and not _SKIP.search(key) and key not in entries:
            entries[key] = {"name": name.strip(), "kind": kind, "target": target}

    try:
        for name, appid in _get_start_apps():
            if name and appid and _APPID_OK.match(appid):
                add(name, "appid", appid)
    except Exception:
        pass
    try:
        for name, path in _scan_lnk():
            add(name, "lnk", path)
    except Exception:
        pass
    return entries


def _save(entries):
    try:
        tmp = _cache_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(list(entries.values()), fh, ensure_ascii=False)
        os.replace(tmp, _cache_path())
    except Exception:
        pass


def _load_cache():
    try:
        with open(_cache_path(), encoding="utf-8") as fh:
            for entry in json.load(fh):
                _index.setdefault(_norm(entry["name"]), entry)
    except Exception:
        pass


def refresh(force=False):
    """Reconstrói o índice (1 a 3 s). Devolve a quantidade de programas."""
    global _last_refresh, _refreshing
    with _lock:
        if _refreshing or (not force and time.time() - _last_refresh < 60):
            return len(_index)
        _refreshing = True
    try:
        entries = _build()
        if entries:
            with _lock:
                _index.clear()
                _index.update(entries)
            _save(entries)
        return len(_index)
    finally:
        with _lock:
            _last_refresh = time.time()
            _refreshing = False


def refresh_async():
    threading.Thread(target=refresh, kwargs={"force": True}, daemon=True).start()


def count():
    return len(_index)


def _match(query):
    keys = list(_index)
    if query in _index:
        return _index[query], 1.0
    words = set(query.split())
    subset = [k for k in keys if words and words <= set(k.split())]
    if subset:
        # vários programas com essa palavra (ex.: "microsoft"): escolhe o mais curto, mas pergunta
        return _index[min(subset, key=len)], (0.95 if len(subset) == 1 else 0.8)
    starts = [k for k in keys if k.startswith(query)]
    if len(query) >= 3 and starts:
        best = min(starts, key=len)
        return _index[best], min(0.9, 0.6 + 0.4 * len(query) / len(best))   # prefixo curto => confirma
    close = difflib.get_close_matches(query, keys, n=1, cutoff=0.6)
    if close:
        return _index[close[0]], difflib.SequenceMatcher(None, query, close[0]).ratio()
    return None, 0.0


def find(spoken):
    query = _norm(spoken)
    if len(query) < 2:
        return None, 0.0
    query = ALIASES.get(query, ALIASES.get(query.replace(" ", ""), query))
    if not _index:
        _load_cache()
    if not _index:
        refresh(force=True)
    entry, score = _match(query)
    if (entry is None or score < CONFIDENT) and time.time() - _last_refresh > REFRESH_MIN_INTERVAL:
        refresh(force=True)                       # talvez o programa tenha sido instalado agora
        entry, score = _match(query)
    return entry, score


def search(query, limit=5):
    query = _norm(query)
    hits = [e["name"] for k, e in _index.items() if query and query in k]
    if not hits:
        keys = difflib.get_close_matches(query, list(_index), n=limit, cutoff=0.5)
        hits = [_index[k]["name"] for k in keys]
    return sorted(set(hits))[:limit]


def launch(entry):
    kind, target = entry.get("kind"), entry.get("target", "")
    if kind == "appid":
        if not _APPID_OK.match(target):
            raise ValueError("Identificador de aplicativo inválido.")
        if re.match(r"^[A-Za-z]:\\", target) and not os.path.isfile(target):
            raise FileNotFoundError("O programa não foi encontrado no disco.")
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + target], creationflags=_NO_WINDOW)
        return
    if kind == "lnk":
        real = os.path.realpath(target)
        roots = [os.path.realpath(r) for r in _start_menu_roots()]
        if not real.lower().endswith(".lnk") or not any(real.lower().startswith(r.lower() + os.sep) for r in roots):
            raise ValueError("Atalho fora do menu Iniciar.")
        if not os.path.isfile(real):
            raise FileNotFoundError("O atalho não existe mais.")
        os.startfile(real)
        return
    raise ValueError("Tipo de entrada desconhecido.")
