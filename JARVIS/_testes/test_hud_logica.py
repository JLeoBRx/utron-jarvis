"""Testa a LÓGICA da HUD (minimizar/restaurar/sem timer de 7 s/botão flutuante) sem Qt real.
PySide6 é substituído por stubs; os métodos reais do MainWindow/FloatingButton são executados."""
import os, sys, types, time, importlib.util
from types import SimpleNamespace
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------- stubs genéricos do PySide6
class _Flag:
    def __init__(self, n=""): self.n = n
    def __or__(self, o): return self
    __ror__ = __or__
    def __and__(self, o): return self
    def __bool__(self): return False
    def __eq__(self, o): return isinstance(o, _Flag) and o.n == self.n
    __hash__ = lambda self: hash(self.n)
class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"): raise AttributeError(n)
        return _Flag(n)
class _Base(metaclass=_Meta):
    def __init__(self, *a, **k): pass
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        return _Any()
class _Any:
    def __init__(self, *a, **k): pass
    def __getattr__(self, n):
        if n.startswith("__"): raise AttributeError(n)
        return _Any()
    def __call__(self, *a, **k): return _Any()
    def __or__(self, o): return self
    def __iter__(self): return iter(())
class Signal:
    def __init__(self, *a): pass
    def __set_name__(self, owner, name): self.name = "_sig_" + name
    def __get__(self, obj, owner):
        if obj is None: return self
        if not hasattr(obj, self.name):
            sig = SimpleNamespace(slots=[])
            sig.connect = sig.slots.append
            sig.emit = lambda *a, s=sig: [f(*a) for f in s.slots]
            setattr(obj, self.name, sig)
        return getattr(obj, self.name)
class QPoint:
    def __init__(self, x=0, y=0): self._x, self._y = x, y
    def x(self): return self._x
    def y(self): return self._y
    def __sub__(self, o): return QPoint(self._x - o._x, self._y - o._y)
    def __add__(self, o): return QPoint(self._x + o._x, self._y + o._y)
    def manhattanLength(self): return abs(self._x) + abs(self._y)
    def toPoint(self): return self
class QRect:
    def __init__(self, x=0, y=0, w=0, h=0): self.X, self.Y, self.W, self.H = x, y, w, h
    def left(self): return self.X
    def top(self): return self.Y
    def right(self): return self.X + self.W - 1
    def bottom(self): return self.Y + self.H - 1
    def width(self): return self.W
    def height(self): return self.H
    def center(self): return QPoint(self.X + self.W // 2, self.Y + self.H // 2)
    def topLeft(self): return QPoint(self.X, self.Y)
class QColor:
    def __init__(self, v="#000000", *a):
        v = str(v) if not isinstance(v, QColor) else v.hexs
        self.hexs = v
        v = v.lstrip("#"); self.r, self.g, self.b = (int(v[i:i+2], 16) for i in (0, 2, 4)) if len(v) >= 6 else (0, 0, 0)
    def red(self): return self.r
    def green(self): return self.g
    def blue(self): return self.b
    def name(self): return self.hexs
    def setAlpha(self, a): pass
    def alpha(self): return 255
def _mod(name, extra=None):
    m = types.ModuleType(name)
    extra = extra or {}
    def ga(n):
        if n.startswith("__"): raise AttributeError(n)
        if n in extra: return extra[n]
        c = type(n, (_Base,), {}); setattr(m, n, c); return c
    m.__getattr__ = ga
    for k, v in extra.items(): setattr(m, k, v)
    return m
pyside = types.ModuleType("PySide6"); pyside.__path__ = []
sys.modules["PySide6"] = pyside
sys.modules["PySide6.QtCore"] = _mod("PySide6.QtCore", {"Signal": Signal, "QPoint": QPoint, "QRect": QRect, "QPointF": _Base, "QRectF": _Base})
sys.modules["PySide6.QtGui"] = _mod("PySide6.QtGui", {"QColor": QColor})
sys.modules["PySide6.QtWidgets"] = _mod("PySide6.QtWidgets")

# ---------------- backend/commands falsos
calls = []
be = types.ModuleType("backend")
be.STATES = {"IDLE", "WAKE", "LISTENING", "THINKING", "TOOL_EXECUTION", "SPEAKING", "ERROR", "RETURNING_IDLE"}
be.status = {"mic": True, "tts": True, "ollama": True, "vision": None}
be.event_queue = __import__("queue").Queue()
be.logs = []
be.OLLAMA_MODEL = "x"; be.MIC_INDEX = 1
S = {"active": True, "idle_ok": True}
be.is_assistant_active = lambda: S["active"]
def return_to_idle():
    calls.append("return_to_idle")
    if S["idle_ok"] and S["active"]:
        S["active"] = False; return True
    return False
be.return_to_idle = return_to_idle
def activate():
    calls.append("activate")
    if S["active"]: return False
    S["active"] = True; return True
be.activate = activate
be.finish_return_to_idle = lambda: calls.append("finish_idle")
be.add_log = lambda t: None
be.abort_agent = lambda: calls.append("abort") or True
be.is_busy = lambda: False
be.run_exclusive = lambda f: (True, f())
be._memory_db_path = lambda: os.path.join("/tmp", "jarvis_test", "assistant.sqlite3")
be.enqueue = lambda *a: None
be.speak = lambda t: None
be._open_memory_db = lambda: (_ for _ in ()).throw(RuntimeError("sem db"))
sys.modules["backend"] = be
cm = types.ModuleType("commands"); cm.norm = lambda s: s.lower(); cm.is_confirmation_pending = lambda: False
cm.cancel_pending = lambda: False; cm.foreground_info = lambda: {}
sys.modules["commands"] = cm

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

passed = 0
def ok(c, m):
    global passed
    print(("PASS" if c else "FAIL"), "-", m)
    if not c: sys.exit(1)
    passed += 1

def make_win(mod, with_new=True):
    class W(mod.MainWindow):
        def __init__(self): pass
        # métodos Qt simulados
        def isVisible(self): return self.vis
        def show(self): self.vis = True; self.log.append("show")
        def hide(self): self.vis = False; self.log.append("hide")
        def raise_(self): pass
        def activateWindow(self): pass
        def geometry(self): return self.geom
        def setGeometry(self, g): self.geom = g; self.log.append("setGeometry")
        def isFullScreen(self): return self.fs
        def showFullScreen(self): self.log.append("showFullScreen")
        def showNormal(self): self.log.append("showNormal")
        def close(self): self.log.append("close")
    w = W()
    w.vis, w.geom, w.fs, w.log = True, QRect(0, 0, 1920, 1040), False, []
    w.display_mode = "full"; w._hide_to_tray_pending = False; w._transition_direction = None
    w.last_interaction = time.monotonic() - 1000          # "parado há muito tempo"
    w.last = time.perf_counter(); w._next_tel = 1e18; w._next_audio = 1e18
    w._bucket_t = time.monotonic(); w.frame = 1; w.animated = []
    w.core = object(); w.inter = SimpleNamespace(chip=object())
    w._allow_exit = False
    w._begin_expansion = lambda: w.log.append("expand")
    w._begin_contraction = lambda: w.log.append("contract")
    return w

class FakeFab:
    def __init__(self): self.vis = False; self.calls = []
    def keep_on_top(self): self.calls.append("top")
    def set_status(self, *a): self.status = a
    def show(self): self.vis = True
    def isVisible(self): return self.vis
    def close(self): self.calls.append("close")
    def geometry(self): return QRect(1840, 960, 60, 60)
class FakeToast:
    def __init__(self): self.vis = False; self.calls = []
    def hide(self): self.vis = False
    def isVisible(self): return self.vis
    def keep_on_top(self): pass
    def close(self): pass
    def drop(self, sid): pass

# =========================================================================================
# A) PROVA DE SENSIBILIDADE: no HUD ORIGINAL, parado >7 s em LISTENING recolhe sozinho
orig = load(os.path.join(ROOT, "_backup_antes_do_copilot", "jarvis_hud.py"), "hud_orig")
w0 = make_win(orig)
orig.anim.state = "LISTENING"; S.update(active=True, idle_ok=True); calls.clear()
w0.tick()
ok("return_to_idle" in calls, "[controle] HUD ORIGINAL recolhia sozinha após 7 s (o teste enxerga o problema)")

# B) HUD NOVA
hud = load(os.path.join(ROOT, "jarvis_hud.py"), "hud_new")
ok(not hasattr(hud, "IDLE_TIMEOUT"), "constante IDLE_TIMEOUT removida")
w = make_win(hud)
w.hud_minimized = False; w._covering = False; w._saved_geometry = None; w._saved_fullscreen = False
w.fab, w.toast = FakeFab(), FakeToast()
w.cpanel = SimpleNamespace(refresh=lambda: None, add_history=lambda e: None)
w.cbar = SimpleNamespace(sync=lambda: None)
import copilot
# 1) sem timer: parado muito tempo, ouvindo, HUD aberta -> NÃO recolhe
for state in ("LISTENING", "ERROR", "SPEAKING", "THINKING", "TOOL_EXECUTION", "IDLE"):
    hud.anim.state = state; S.update(active=True, idle_ok=True); calls.clear()
    for _ in range(3): w.tick()
    ok("return_to_idle" not in calls, f"HUD aberta parada em {state}: não recolhe sozinha")
ok(w.vis and not w.hud_minimized, "janela continua visível e não-minimizada")

# 2) Esc não minimiza
hud.anim.state = "LISTENING"; calls.clear(); w.on_escape()
ok("return_to_idle" not in calls, "Esc não recolhe a HUD")
hud.anim.state = "THINKING"; calls.clear(); w.on_escape()
ok("abort" in calls, "Esc continua abortando tarefa em andamento")

# 3) minimizar (assistente ativo, ocioso) -> contrai e esconde no fim da animação
hud.anim.state = "LISTENING"; S.update(active=True, idle_ok=True); calls.clear(); w.log.clear()
w.minimize_hud()
ok(w.hud_minimized and "return_to_idle" in calls and w._hide_to_tray_pending and w.vis,
   "minimizar pede retorno ao ocioso e espera a animação de contração")
w.display_mode = "contracting"; w._transition_direction = "contract"
w.compact = SimpleNamespace(show=lambda: None, set_progress=lambda v: None, hide=lambda: None)
w._set_full_widgets_visible = lambda v: None; w.background = SimpleNamespace(update=lambda: None, resizeEvent=lambda e: None)
w._finish_transition()
ok(not w.vis and w.display_mode == "compact", "ao fim da contração a HUD some (botão flutuante permanece)")

# 4) restaurar: orbe -> ativa -> expande
calls.clear(); w.log.clear(); S["active"] = False
w.setGeometry = lambda g: w.log.append("setGeometry")
w._compact_geometry = lambda: QRect(1800, 920, 196, 196)
w.restore_hud()
ok(w.vis and not w.hud_minimized and "activate" in calls, "restaurar mostra a janela e ativa o assistente (expansão)")

# 5) toggle
S["active"] = True; w.display_mode = "full"; w.hud_minimized = False; w.vis = True; calls.clear()
w.toggle_hud(); ok(w.hud_minimized, "toggle com HUD aberta minimiza")
w.toggle_hud(); ok(not w.hud_minimized and w.vis, "toggle com HUD recolhida restaura")

# 6) minimizar no meio de uma tarefa (ocupado): esconde já, tarefa segue, e depois volta ao modo "Jarvis"
S.update(active=True, idle_ok=False); hud.anim.state = "THINKING"; w.display_mode = "full"; w.hud_minimized = False
w.vis = True; w.geom = QRect(0, 0, 1920, 1040); calls.clear(); w.log.clear()
w.minimize_hud()
ok(not w.vis and w.hud_minimized and "return_to_idle" in calls and S["active"], "ocupado: esconde na hora e não interrompe a tarefa")
S["idle_ok"] = True; calls.clear(); hud.anim.state = "THINKING"; w.tick()
ok("return_to_idle" not in calls, "minimizada e ainda pensando: não mexe no assistente")
hud.anim.state = "LISTENING"; w.tick()
ok("return_to_idle" in calls, "tarefa terminou com a HUD minimizada: volta a exigir a palavra 'Jarvis'")
# restaurar nesse caso volta ao tamanho e posição anteriores
S["active"] = True; w.display_mode = "full"; w.log.clear(); w.restore_hud()
ok("setGeometry" in w.log and w.geom.W == 1920, "restaurar devolve tamanho/posição de antes de minimizar")

# 7) fechar a janela = minimizar (botão flutuante permanece), não encerra
w.hud_minimized = False; w.vis = True; w.display_mode = "full"; S.update(active=True, idle_ok=True); calls.clear()
class Ev:
    ignored = False
    def ignore(self): self.ignored = True
    def accept(self): pass
ev = Ev(); w.closeEvent(ev)
ok(ev.ignored and w.hud_minimized, "fechar (X/Alt+F4) só minimiza")

# 8) WAKE com a HUD recolhida (palavra 'Jarvis'): mostra e expande
w.hud_minimized = True; w.vis = False; w.log.clear(); hud.anim.state = "IDLE"
be.STATES.add("WAKE"); w.set_state("WAKE")
ok(w.vis and "expand" in w.log, "palavra de ativação com a HUD recolhida: mostra e expande")

# 9) cache de cobertura para o copilot
w.vis = True; w.display_mode = "full"; w._update_covering(); ok(w._hud_covering() is True, "HUD aberta => copilot sabe que cobre a tela")
w.vis = False; w._update_covering(); ok(w._hud_covering() is False, "HUD recolhida => copilot pode observar")
w.vis = True; w.display_mode = "compact"; w._update_covering(); ok(w._hud_covering() is False, "orbe compacto não cobre a tela")

# =========================================================================================
# C) Botão flutuante: cantos, arrastar, clique
fb = hud.FloatingButton.__new__(hud.FloatingButton)
fb.SIZE = 60
fb._geom = QRect(0, 0, 60, 60)
fb.geometry = lambda: fb._geom
fb.isVisible = lambda: True
fb.move = lambda *a: setattr(fb, "_geom", QRect(a[0].x() if len(a) == 1 else a[0], a[0].y() if len(a) == 1 else a[1], 60, 60))
fb._screen_rect = lambda point=None: QRect(0, 0, 1920, 1040)
for corner, (ex, ey) in {"top-left": (20, 20), "top-right": (1840, 20), "bottom-left": (20, 960), "bottom-right": (1840, 960)}.items():
    fb.place(corner); ok((fb._geom.X, fb._geom.Y) == (ex, ey), f"botão encaixa no canto {corner} {ex},{ey}")
    ok(fb.corner_now() == corner, f"canto detectado = {corner}")
fb._geom = QRect(1000, 100, 60, 60); ok(fb.corner_now() == "top-right", "posição solta perto do topo/direita encaixa em top-right")
fb._geom = QRect(300, 900, 60, 60); ok(fb.corner_now() == "bottom-left", "posição solta embaixo/esquerda encaixa em bottom-left")
# clique x arraste
sig = SimpleNamespace(toggled=0, corner=None)
fb.clicked_toggle.connect(lambda: setattr(sig, "toggled", sig.toggled + 1))
fb.cornerChanged.connect(lambda c: setattr(sig, "corner", c))
fb._press_global = None; fb._dragging = False; fb._press_offset = QPoint()
class Me:
    def __init__(self, x, y, left=True): self.x, self.y, self.left = x, y, left
    def button(self): return hud.Qt.LeftButton
    def buttons(self): return hud.Qt.LeftButton
    def globalPosition(self): return QPoint(self.x, self.y)
fb.frameGeometry = lambda: fb._geom
hud.Qt.LeftButton = "L"
class QtL:  # compara botão
    pass
# sem mover: clique
fb._geom = QRect(1840, 960, 60, 60)
fb.mousePressEvent(SimpleNamespace(button=lambda: "L", globalPosition=lambda: QPoint(1860, 980)))
fb.mouseReleaseEvent(SimpleNamespace(button=lambda: "L", globalPosition=lambda: QPoint(1860, 980)))
ok(sig.toggled == 1 and sig.corner is None, "clique simples (sem arrastar) alterna a HUD")
# arrastando 600 px: muda de canto e NÃO alterna a HUD
fb.mousePressEvent(SimpleNamespace(button=lambda: "L", globalPosition=lambda: QPoint(1860, 980)))
class _Held:
    def __and__(self, o): return True
fb.mouseMoveEvent(SimpleNamespace(buttons=lambda: _Held(), globalPosition=lambda: QPoint(1260, 100)))
fb._geom = QRect(1200, 80, 60, 60)
fb.mouseReleaseEvent(SimpleNamespace(button=lambda: "L", globalPosition=lambda: QPoint(1260, 100)))
ok(sig.toggled == 1 and sig.corner == "top-right", "arrastar muda para o canto mais próximo sem restaurar/minimizar a HUD")

print(f"\n{passed} verificações OK")
