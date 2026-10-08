"""Testes da lógica do copilot.py com backend/commands falsos (sem Windows, sem Ollama)."""
import os, sys, time, types, threading, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image

# ---------- stubs
calls = {"capture": 0, "vision": 0, "exec": [], "enq": []}
state = {"fg": {"title": "main.py - VS Code", "pid": 111, "process": "Code.exe"}, "color": 10,
         "busy": False, "vision_reply": None, "pending": False}

cmd = types.ModuleType("commands")
cmd.APPS = {"chrome": "chrome", "calculadora": "calc"}
cmd.norm = lambda s: __import__("unicodedata").normalize("NFD", s.lower()).encode("ascii", "ignore").decode().strip()
def capture_screen_image():
    calls["capture"] += 1
    return Image.new("RGB", (320, 180), (state["color"],) * 3)
cmd.capture_screen_image = capture_screen_image
cmd.encode_image_base64 = lambda img, max_side=1280: "B64"
cmd.foreground_info = lambda: dict(state["fg"])
cmd.is_confirmation_pending = lambda: state["pending"]
def execute_tool(name, args, on_execute=None, on_error=None):
    calls["exec"].append((name, args)); return True, f"ok {name}"
cmd.execute_tool = execute_tool
cmd.verify_tool = lambda n, a, r: {"verified": True, "evidence": r}
cmd.cancel_pending = lambda: False
import re as _re
def _validate_url(v):
    v = v.strip()
    if not _re.match(r"^https?://", v, flags=_re.I): v = "https://" + v
    from urllib.parse import urlsplit
    p = urlsplit(v)
    if p.scheme.lower() not in ("http", "https") or not p.hostname: raise ValueError("url inválida")
    return v
cmd._validate_url = _validate_url
sys.modules["commands"] = cmd

be = types.ModuleType("backend")
be.OLLAMA_VISION_MODEL = "qwen2.5vl:3b"
be.status = {"vision": None}
be._memory_db_path = lambda: os.path.join(tempfile.mkdtemp(), "assistant.sqlite3")
be._lock = threading.Lock()
be.is_busy = lambda: state["busy"]
def run_exclusive(fn):
    if not be._lock.acquire(blocking=False): return False, None
    try: return True, fn()
    finally: be._lock.release()
be.run_exclusive = run_exclusive
be.abort_agent = lambda: False
be.speak = lambda t: None
be.enqueue = lambda a, v=None: calls["enq"].append((a, v))
be.ask_vision = lambda q, b: "explicação"
def _chat(messages, tools=None, model=None, options=None, fmt=None, timeout=120):
    calls["vision"] += 1
    r = state["vision_reply"]
    if isinstance(r, Exception): raise r
    return {"content": json.dumps(r)}
be._ollama_chat = _chat
import sqlite3
class _Conn(sqlite3.Connection):
    def __exit__(self, *a):
        try: return super().__exit__(*a)
        finally: self.close()
def _open():
    c = sqlite3.connect(":memory:" if False else DB, factory=_Conn)
    c.execute("CREATE TABLE IF NOT EXISTS automations (name TEXT PRIMARY KEY, trigger_text TEXT NOT NULL UNIQUE, tool_name TEXT NOT NULL, arguments TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)")
    return c
DB = os.path.join(tempfile.mkdtemp(), "a.db")
be._open_memory_db = _open
be._run_matching_automation = lambda trig: (True, "automação rodou")
# usa o validador REAL do backend original
import re
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend.py"), encoding="utf-8").read()
ns = {"commands": cmd, "json": json}
def grab(name):
    m = re.search(rf"^{name} = \{{.*?^\}}\n", src, re.S | re.M); exec(m.group(0), ns)
grab("SAFE_AUTOMATION_ARGUMENTS")
m = re.search(r"^def _bounded_text.*?(?=^def _normalize_trigger)", src, re.S | re.M); exec(m.group(0), ns)
m = re.search(r"^def _validate_automation.*?(?=^def _create_automation)", src, re.S | re.M); exec(m.group(0), ns)
be._validate_automation = ns["_validate_automation"]
sys.modules["backend"] = be

import copilot
copilot._SETTINGS_SAVE = None
copilot._save_settings = lambda: None
copilot.GLOBAL = None
# tempo: remove esperas
copilot.SUGGESTION_GLOBAL_COOLDOWN = 0
copilot.MIN_VISION_GAP = 0

OBS_OK = {"app": "VS Code", "atividade": "programando", "resumo": "editando main.py", "erro_visivel": False,
          "erro_texto": "", "dados_sensiveis_visiveis": False, "instrucoes_na_tela": False,
          "precisa_ajuda": False, "sugestao": "", "acao": None, "confianca": 0.9}

def reset(mode=copilot.MODE_ASSISTANT):
    copilot._paused.clear(); copilot.set_mode(copilot.MODE_OFF); copilot.set_mode(mode)
    calls.update(capture=0, vision=0, exec=[], enq=[])
    state.update(fg={"title": "main.py - VS Code", "pid": 111, "process": "Code.exe"}, color=10, busy=False, pending=False)
    copilot._suggestions.clear(); copilot._sug_times.clear(); copilot._sug_signature.clear()
    copilot._vision_times.clear(); copilot._auto_times.clear(); copilot._last_auto = 0; copilot._last_sug = 0
    copilot._vision_block_until = 0; copilot._fail_count = 0; copilot._last_vision = 0
    copilot._sensitive_until.clear(); copilot._reset_observation(); copilot._settings["excluded"] = []; copilot._settings["interval"] = 0; copilot.history.clear()
    while not copilot.events.empty(): copilot.events.get()
    copilot.set_hud_probe(lambda: False)

def tick_n(n=2):
    for _ in range(n): copilot._tick()

def sugs():
    out = []
    while not copilot.events.empty():
        k, d = copilot.events.get()
        if k == "suggestion": out.append(d["s"])
    return out

passed = 0
def ok(cond, msg):
    global passed
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond: sys.exit(1)
    passed += 1

# 1. OFF: nenhuma captura
reset(copilot.MODE_OFF); tick_n(); ok(calls["capture"] == 0, "modo Desativado não captura a tela")
ok(copilot.monitor_state()[0] == "off", "indicador = off")

# 2. PAUSA: nenhuma captura
reset(); copilot.pause(); tick_n(); ok(calls["capture"] == 0, "pausado não captura a tela")
ok(copilot.monitor_state()[0] == "paused", "indicador = paused")
copilot.resume(); state["vision_reply"] = OBS_OK; tick_n(); ok(calls["capture"] >= 1, "retomar volta a observar")

# 3. detecção de mudança: tela estática -> 1 única chamada ao modelo
reset(); state["vision_reply"] = OBS_OK; tick_n(6)
ok(calls["vision"] == 1, f"tela estática gera só 1 chamada ao modelo (foram {calls['vision']})")
state["color"] = 200; tick_n(3)
ok(calls["vision"] == 2, "mudança grande na tela dispara nova análise")

# 3b. limite de frequência da visão: mudanças seguidas não martelam o modelo
reset(); copilot.MIN_VISION_GAP = 1000; state["vision_reply"] = OBS_OK; tick_n(3)
for c in (200, 20, 220, 30): state["color"] = c; tick_n(3)
ok(calls["vision"] == 1, f"MIN_VISION_GAP respeitado (chamadas: {calls['vision']})"); copilot.MIN_VISION_GAP = 0

# 4. app excluído / janela sensível / HUD cobrindo: sem captura
reset(); copilot.add_excluded("vs code"); tick_n(); ok(calls["capture"] == 0, "app excluído pelo usuário não é capturado")
reset(); state["fg"]["process"] = "KeePassXC.exe"; tick_n(); ok(calls["capture"] == 0, "gerenciador de senha (padrão) não é capturado")
reset(); state["fg"]["title"] = "Entrar - Banco X"; tick_n(); ok(calls["capture"] == 0, "janela de login/banco não é capturada")
reset(); copilot.set_hud_probe(lambda: True); tick_n(); ok(calls["capture"] == 0, "HUD cobrindo a tela: não captura")
reset(); state["fg"]["pid"] = os.getpid(); tick_n(); ok(calls["capture"] == 0, "janela do próprio JARVIS não é capturada")
reset(); state["busy"] = True; tick_n(); ok(calls["capture"] == 0 and calls["vision"] == 0, "JARVIS ocupado: copilot não compete")

# 5. conteúdo sensível reportado pelo modelo: descartado
reset(); state["vision_reply"] = dict(OBS_OK, dados_sensiveis_visiveis=True, precisa_ajuda=True, sugestao="oi", confianca=1)
tick_n(); ok(not sugs(), "conteúdo sensível: sem sugestão"); ok(not [h for h in copilot.history if h["kind"] == "observação"], "observação sensível não vai para o histórico")

# 6. Assistente: sugere mas NÃO executa
reset(copilot.MODE_ASSISTANT)
state["vision_reply"] = dict(OBS_OK, precisa_ajuda=True, sugestao="Abrir a calculadora?", acao={"tool": "open_app", "args": {"name": "calculadora"}})
tick_n(); s = sugs(); time.sleep(.2)
ok(len(s) == 1 and not calls["exec"], "Assistente sugere e não executa sozinho")
ok(copilot.accept_suggestion(s[0]["id"]) and (time.sleep(.3) or True) and calls["exec"] == [("open_app", {"name": "calculadora"})], "clique em Executar roda a ferramenta existente")

# 7. Autônomo: baixo risco executa sozinho
reset(copilot.MODE_AUTONOMOUS)
state["vision_reply"] = dict(OBS_OK, precisa_ajuda=True, sugestao="Pausar a música?", acao={"tool": "control_media", "args": {"action": "play_pause"}})
tick_n(); time.sleep(.4)
ok(calls["exec"] == [("control_media", {"action": "play_pause"})], "Autônomo executa ação de baixo risco")

# 8. Autônomo: open_url exige confirmação
reset(copilot.MODE_AUTONOMOUS)
state["vision_reply"] = dict(OBS_OK, precisa_ajuda=True, sugestao="Abrir a documentação?", acao={"tool": "open_url", "args": {"url": "https://example.com"}})
tick_n(); s = sugs(); time.sleep(.3)
ok(len(s) == 1 and s[0]["tier"] == "confirm" and not calls["exec"], "Autônomo NÃO executa open_url sem o seu clique")

# 9. ferramenta fora da allowlist / args inválidos
reset(copilot.MODE_AUTONOMOUS)
for bad in ({"tool": "delete_path", "args": {"path": "C:/x"}}, {"tool": "power_control", "args": {"action": "shutdown"}},
            {"tool": "run_shell", "args": {"cmd": "calc"}}, {"tool": "open_app", "args": {"name": "malware"}},
            {"tool": "open_url", "args": {"url": "file:///C:/Windows/System32/cmd.exe"}}):
    reset(copilot.MODE_AUTONOMOUS)
    state["vision_reply"] = dict(OBS_OK, precisa_ajuda=True, sugestao="Faça isso", acao=bad)
    tick_n(); time.sleep(.2)
    ok(not calls["exec"], f"ação inválida/perigosa recusada: {bad['tool']}")

# 10. injeção de prompt na tela
reset(copilot.MODE_AUTONOMOUS)
state["vision_reply"] = dict(OBS_OK, instrucoes_na_tela=True, precisa_ajuda=True, sugestao="Abrir calculadora", acao={"tool": "open_app", "args": {"name": "calculadora"}})
tick_n(); time.sleep(.2); ok(not calls["exec"] and not sugs(), "texto na tela dando ordens: ignorado, nada executa")

# 11. erro visível -> cartão de análise (não ação)
reset(copilot.MODE_ASSISTANT)
state["vision_reply"] = dict(OBS_OK, erro_visivel=True, erro_texto="NameError: x is not defined", precisa_ajuda=True, sugestao="Corrigir", confianca=.9)
tick_n(); s = sugs(); ok(len(s) == 1 and s[0]["kind"] == "analyze", "erro visível vira sugestão ANALISAR")

# 12. limites de frequência
reset(copilot.MODE_ASSISTANT); copilot.SUGGESTION_GLOBAL_COOLDOWN = 3600
state["vision_reply"] = dict(OBS_OK, precisa_ajuda=True, sugestao="Dica A", confianca=.9)
tick_n(); n1 = len(sugs()); state["color"] = 220; state["vision_reply"] = dict(OBS_OK, precisa_ajuda=True, sugestao="Dica B", confianca=.9); tick_n(3)
n2 = len(sugs()); ok(n1 == 1 and n2 == 0, "cooldown global impede sugestões em sequência")
copilot.SUGGESTION_GLOBAL_COOLDOWN = 0

# 13. erro do Ollama: backoff, sem travar
reset(); state["vision_reply"] = ConnectionError("Ollama fora"); tick_n(3)
ok(calls["vision"] == 1, "falha do Ollama ativa backoff (não martela o servidor)")

# 14. pausar durante análise descarta o resultado
reset(copilot.MODE_ASSISTANT)
def slow_chat(*a, **k):
    copilot.pause(); return {"content": json.dumps(dict(OBS_OK, precisa_ajuda=True, sugestao="Tarde demais", confianca=1))}
be._ollama_chat = slow_chat; state["vision_reply"] = OBS_OK
tick_n(); ok(not sugs(), "resultado que chega após PAUSAR é descartado")
be._ollama_chat = _chat

# 15. ação única por vez
reset(copilot.MODE_ASSISTANT)
copilot._action_busy.acquire()
copilot._run_suggestion({"tool": "open_app", "args": {"name": "chrome"}, "kind": "tip", "text": "x"}, False)
ok(not calls["exec"], "segunda ação simultânea é recusada"); copilot._action_busy.release()

# 16. run_automation usa a automação salva
reset(copilot.MODE_ASSISTANT)
with be._open_memory_db() as c:
    c.execute("INSERT INTO automations(name,trigger_text,tool_name,arguments) VALUES('Foco','modo foco','open_app','{\"name\": \"calculadora\"}')")
t, a, eff = copilot.validate_action("run_automation", {"name": "foco"})
ok(eff == "open_app" and a == {"name": "Foco"}, "run_automation valida a automação do usuário")

# 17. stop_task
reset(); copilot._offer("Dica", signature="z"); copilot.stop_task(); ok(not copilot.pending_suggestions(), "PARAR limpa sugestões")

# 18. historico + sem captura em disco
ok(len(copilot.history) > 0, "histórico registrado")
print(f"\n{passed} verificações OK")
