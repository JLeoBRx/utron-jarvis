"""J.A.R.V.I.S. NEURAL CORE — o cérebro holográfico que GERA e CONTROLA o HUD.

* IDLE: tela escura; um núcleo de energia gera partículas que se ligam e formam o cérebro (gênese),
  depois ele só pulsa. Abaixo, apenas "J.A.R.V.I.S. / NEURAL CORE".
* Comando: o cérebro reage, interpreta a intenção (plan) e faz crescer só os nós necessários;
  cada painel materializa a partir de partículas quando o nó correspondente chega.
* Fim da tarefa: painéis viram partículas que voltam ao cérebro; as conexões somem.
Só desenha: lê anim / live / backend (dados reais). Nada de telemetria inventada.
"""
import math
import random
import re
import time

from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QRadialGradient, QPainterPath, QBrush
from PySide6.QtWidgets import QWidget, QToolTip

CYAN, BLUE, DEEP, ICE = (0, 240, 255), (30, 140, 255), (10, 60, 160), (225, 250, 255)

# nome, ângulo (graus, horário, 0 = direita), órbita: "o" externa · "i" interna (estações do plano)
NODES = [("VISÃO", -165, "o"), ("MEMÓRIA", -135, "o"), ("OLLAMA", -105, "o"), ("GPT", -75, "o"),
         ("WEB", -45, "o"), ("CÓDIGO", -15, "o"), ("AUTOMAÇÃO", 15, "o"), ("WINDOWS", 45, "o"),
         ("ARQUIVOS", 75, "o"), ("TELEMETRIA", 105, "o"), ("OBSERVADOR", 135, "o"), ("VOZ", 165, "o"),
         ("INTENÇÃO", -90, "i"), ("VERIFICAÇÃO", 52, "i")]
# ordem do plano (CÉREBRO → INTENÇÃO → … → VERIFICAÇÃO)
CHAIN = ["INTENÇÃO", "MEMÓRIA", "VISÃO", "OBSERVADOR", "OLLAMA", "GPT", "WEB", "ARQUIVOS",
         "WINDOWS", "CÓDIGO", "AUTOMAÇÃO", "TELEMETRIA", "VERIFICAÇÃO"]

# intenção -> módulos (o que o comando realmente exige)
RULES = [
    (r"\b(abr[aei]r?|inici[ae]r?|execut[ae]r?|lan[cç][ae]r?|fech[ae]r?)\b", ["WINDOWS"]),
    (r"vs ?code|visual studio|editor|c[oó]digo|programa[rç]|script|python|terminal|compil", ["CÓDIGO"]),
    (r"\btela\b|screenshot|captur|\bveja\b|\bolhe\b", ["VISÃO", "OBSERVADOR"]),
    (r"pesquis|busc[ao]|google|internet|\bweb\b|\bsite\b|not[ií]cia|youtube|navegador", ["WEB"]),
    (r"arquivo|pasta|documento|download|salv|copiar|mover|apag", ["ARQUIVOS"]),
    (r"lembr|mem[oó]ri|anot|guarde", ["MEMÓRIA"]),
    (r"\bclic|digit|mouse|teclado|macro|preench", ["AUTOMAÇÃO"]),
    (r"\bcpu\b|\bram\b|\bgpu\b|bateria|desempenho|status|telemetr", ["TELEMETRIA"]),
    (r"observ|copilot|sugest|monitor", ["OBSERVADOR"]),
]
COMPLEX = r"resolv|problema|corrij|consert|\berro\b|\bbug\b|desenvolv|implement|crie um|criar um|programe|refator|otimiz"
GPT_RX = r"gpt|openai|chatgpt"
NOTE = {"VISÃO": r"captur|screenshot|vis[aã]o", "WEB": r"\bweb\b|pesquis|navegador", "ARQUIVOS": r"arquivo|pasta",
        "CÓDIGO": r"c[oó]digo|script", "WINDOWS": r"janela|abrindo|aplicativo", "AUTOMAÇÃO": r"clic|digit|automa"}
# painel -> módulos que o justificam (um painel só nasce quando um deles chegou)
PANEL_MODS = {"status_p": {"TELEMETRIA"}, "diag_p": {"TELEMETRIA", "GPT"}, "mods_p": set(),
              "net_p": {"WEB", "GPT"}, "act_p": {"MEMÓRIA", "AUTOMAÇÃO", "ARQUIVOS"},
              "console": {"CÓDIGO", "WINDOWS", "AUTOMAÇÃO", "ARQUIVOS", "WEB"}, "cpanel": {"VISÃO", "OBSERVADOR"}}
STAGES = {"INTENÇÃO", "VERIFICAÇÃO"}


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def rgba(c, a):
    return QColor(int(c[0]), int(c[1]), int(c[2]), int(clamp(a, 0, 255)))


def mixc(a, b, k):
    return tuple(a[i] + (b[i] - a[i]) * k for i in range(3))


class BrainSim:
    """Estado e desenho do cérebro. Uma única instância (SIM) é compartilhada pelo orbe e pela tela cheia."""

    def __init__(self):
        rnd = random.Random(11)
        pts = []
        for _ in range(230):                              # casca com giros e fissura central
            th, ph = rnd.uniform(0, math.tau), math.acos(rnd.uniform(-.75, 1))
            g = 1 + .11 * math.sin(5 * th + 3 * ph) * math.sin(4 * ph)
            x, y, z = math.sin(ph) * math.cos(th), -math.cos(ph) * .78, math.sin(ph) * math.sin(th) * .8
            if abs(z) < .06:
                z += .09 if z >= 0 else -.09
            pts.append((x * g, y * g, z * g))
        for _ in range(34):                               # cerebelo / tronco
            th, ph = rnd.uniform(0, math.tau), rnd.uniform(0, math.pi)
            pts.append((-.48 + .28 * math.sin(ph) * math.cos(th), .62 + .16 * math.cos(ph), .26 * math.sin(ph) * math.sin(th)))
        self.P, n = pts, len(pts)
        self.rad = [math.sqrt(x * x + y * y + z * z) for x, y, z in pts]
        order = sorted(range(n), key=lambda i: -pts[i][1] + rnd.uniform(-.35, .35))   # nasce do tronco para a coroa
        self.birth = [0.0] * n
        for rank, i in enumerate(order):
            self.birth[i] = 1.2 + 8.0 * rank / n
        E = set()
        for i, a in enumerate(pts):
            d = sorted((sum((a[k] - b[k]) ** 2 for k in range(3)), j) for j, b in enumerate(pts) if j != i)
            for dd, j in d[:3]:
                if dd < .09:
                    E.add((min(i, j), max(i, j)))
        self.E = sorted(E)
        self.ebirth = [max(self.birth[i], self.birth[j]) + 1.3 for i, j in self.E]
        self.gt, self.ang, self._last = 0.0, 0.0, time.perf_counter()     # gt = relógio da gênese
        self.a = self.live = self.backend = None
        self._st, self._st_t, self._hold = "IDLE", 0.0, 0.0
        self.build = 0.0                                  # 0 = adormecido · 1 = interface aberta
        self.pulse = self.boost = 0.0
        self.wave = 9.0
        self.m = self.m_goal = 0.0                        # 0 = Ollama local · 1 = GPT
        self.plan_ = None
        self.grow = {nm: 0.0 for nm, _a, _o in NODES}
        self.vis = dict(self.grow)
        self.start, self.want, self.seq_t, self.chain = {}, set(), 0.0, []
        self.po = {k: 0.0 for k in PANEL_MODS}            # opacidade (materialização) de cada painel
        self.pdelta = dict(self.po)
        self.pulses, self.sparks, self.xedges, self.rings = [], [], [], []
        self.nodes_screen = []

    # ------------------------------------------------------------ comandos vindos do HUD
    def keep_open(self, sec):
        self._hold = max(self._hold, time.monotonic() + sec)

    def react(self):
        """Chamado do JARVIS: pulso, núcleo intenso, partículas aceleram, novas conexões."""
        self.keep_open(8.0)
        self.pulse, self.boost, self.wave = 1.0, 1.0, 0.0
        for _ in range(26):
            self.sparks.append([random.uniform(0, math.tau), .1, random.uniform(.6, 1.6), 1.0, random.uniform(1, 2.4)])
        for _ in range(14):
            i, j = random.randrange(len(self.P)), random.randrange(len(self.P))
            if i != j:
                self.xedges.append([i, j, 0.0])

    def route_to(self, name):
        self.m_goal = 1.0 if str(name).lower() == "gpt" else 0.0

    def plan(self, text):
        """Interpreta a intenção do comando e define quais módulos o plano exige."""
        low = str(text).lower().strip()
        mono = time.monotonic()
        if not low or (self.plan_ and self.plan_["text"] == low and mono - self.plan_["t"] < 3):
            return
        mods = set()
        for rx, ms in RULES:
            if re.search(rx, low):
                mods.update(ms)
        cx_ = bool(re.search(COMPLEX, low))
        if cx_:
            mods |= {"VISÃO", "CÓDIGO", "AUTOMAÇÃO"}
        self.plan_ = {"text": low, "t": mono, "mods": mods, "ia": cx_ or not mods, "verify": cx_}
        if re.search(GPT_RX, low):
            self.m_goal = 1.0
        self.react()

    def note(self, text):
        """Linhas de log podem acrescentar módulos ao plano em andamento (ex.: 'capturando tela')."""
        if not self.plan_:
            return
        low = str(text).lower()
        for nm, rx in NOTE.items():
            if re.search(rx, low) and nm not in self.plan_["mods"]:
                self.plan_["mods"].add(nm)
                self.keep_open(4.0)
        if re.search(GPT_RX, low):
            self.m_goal, self.plan_["ia"] = 1.0, True

    # ------------------------------------------------------------ lógica por quadro
    def vstate(self):
        s, age = self.a.state, self.a.t - self._st_t
        if self.build < .05 or s in ("IDLE", "RETURNING_IDLE"):
            return "IDLE"
        if s in ("WAKE", "ERROR"):
            return "WAITING"
        if s == "LISTENING":
            return "LISTENING"
        if s == "THINKING":
            return "THINKING" if age < 1.5 else "PLANNING"
        return "EXECUTING" if s == "TOOL_EXECUTION" else "VERIFYING"

    def route_label(self):
        if self.build < .05:
            return "LOCAL"
        if self.m > .97:
            return "GPT ACTIVE"
        if self.m > .02 or self.m_goal > self.m:
            return "MIGRANDO"
        return "OLLAMA ACTIVE" if self.vstate() in ("THINKING", "PLANNING", "EXECUTING", "VERIFYING") else "LOCAL"

    def _wanted(self, alive):
        s, w = self.a.state, set()
        if not alive:
            return w
        if s == "SPEAKING" or (s in ("WAKE", "LISTENING") and self.plan_ is None):
            w.add("VOZ")                                  # voz só aparece ao chamar e ao responder
        pl = self.plan_
        if pl:
            w |= pl["mods"] | {"INTENÇÃO"}
            if pl["ia"]:
                if self.m < .97:
                    w.add("OLLAMA")
                if self.m_goal > 0 or self.m > .02:
                    w.add("GPT")
            if pl["verify"] and s == "SPEAKING":
                w.add("VERIFICAÇÃO")
        return w

    def step(self, a, live, backend):
        now = time.perf_counter()
        dt = now - self._last
        if dt < .004:
            return
        dt, self._last = min(dt, .05), now
        self.a, self.live, self.backend = a, live, backend
        self.gt += dt
        mono, s = time.monotonic(), a.state
        if s != self._st:
            self._st, self._st_t = s, a.t
            if s == "WAKE":
                self.react()
            elif s == "LISTENING":
                self.keep_open(8.0)
            elif s in ("THINKING", "TOOL_EXECUTION"):
                self.pulse = max(self.pulse, .8)
        if s in ("THINKING", "TOOL_EXECUTION", "SPEAKING"):
            self.keep_open(3.5)
            if self.plan_ is None:                        # comando sem hook: raciocínio genérico
                self.plan_ = {"text": "", "t": mono, "mods": set(), "ia": True, "verify": False}
        alive = mono < self._hold
        if not alive:
            self.plan_ = None
        self.build += clamp((1.0 if alive else 0.0) - self.build, -dt * .6, dt * .9)
        if not alive and self.build < .02:
            self.m_goal = 0.0                             # tarefa terminou: volta ao Ollama local
        self.pulse, self.boost = max(0.0, self.pulse - dt * 1.4), max(0.0, self.boost - dt / 3.0)
        self.wave += dt * 1.1
        self.ang += dt * (.2 + .8 * self.boost + .4 * a.energy)
        self.m += clamp(self.m_goal - self.m, -dt * .55, dt * .55)          # migração ~1,8 s
        wanted = self._wanted(alive)
        if not wanted:
            self.seq_t = 0.0
        for nm in CHAIN:                                  # ativação em cadeia: cada nó espera o anterior
            if nm in wanted and nm not in self.want:
                self.start[nm] = max(now, self.seq_t + .45)
                self.seq_t = self.start[nm]
        if "VOZ" in wanted and "VOZ" not in self.want:
            self.start["VOZ"] = now
        self.want = wanted
        self.chain = [nm for nm in CHAIN if nm in wanted]
        for nm in self.grow:
            tgt = 1.0 if (nm in wanted and now >= self.start.get(nm, 0)) else 0.0
            g = self.grow[nm]
            ng = g + clamp(tgt - g, -dt * 1.3, dt * 1.7)
            if g < .97 <= ng:
                self.rings.append([nm, 0.0])
            self.grow[nm] = ng
            k = clamp((ng - .75) / .25)
            self.vis[nm] = k * k * (3 - 2 * k)
        arrived = {nm for nm in wanted if self.grow[nm] > .97}
        real = arrived - STAGES - {"VOZ"}
        for pn, mods in PANEL_MODS.items():               # painéis só nascem quando o módulo chegou
            goal = bool(mods & arrived) or (pn == "mods_p" and len(real) >= 3)
            o = self.po[pn]
            self.po[pn] = o + clamp((1.0 if goal else 0.0) - o, -dt * 1.7, dt * 1.2)
            self.pdelta[pn] = self.po[pn] - o
        for r in self.rings:
            r[1] += dt * 1.1
        self.rings = [r for r in self.rings if r[1] < 1]
        en = clamp(a.energy + .5 * self.boost)
        rate = (16 if self.gt < 12 else 2.5) + 70 * self.boost + 10 * en     # emissão de partículas do núcleo
        if len(self.sparks) < 90 and random.random() < dt * rate:
            self.sparks.append([random.uniform(0, math.tau), .08, random.uniform(.25, .7) * (1 + 2 * self.boost), 1.0, random.uniform(.8, 2)])
        for sp in self.sparks:
            sp[1] += dt * sp[2]
            sp[3] -= dt * (.55 + .5 * self.boost)
        self.sparks = [sp for sp in self.sparks if sp[3] > 0]
        for xe in self.xedges:
            xe[2] += dt / 1.8
        self.xedges = [xe for xe in self.xedges if xe[2] < 1]
        if self.gt > 12.5 and len(self.pulses) < 90 and random.random() < dt * (2 + 50 * en * (1 + self.pulse)):
            self.pulses.append([random.randrange(len(self.E)), 0.0, random.uniform(.8, 1.8) * (.6 + en + self.boost)])
        for q in self.pulses:
            q[1] += dt * q[2]
        self.pulses = [q for q in self.pulses if q[1] < 1]

    def node_text(self, name):
        s, st = self.live["s"], self.backend.status
        if name == "OLLAMA":
            ok = s.get("ollama_ok")
            return "LOCAL ONLINE" if ok else ("OFFLINE" if ok is False else "N/D")
        if name == "VOZ":
            return f"MIC {'ON' if st['mic'] is True else 'OFF'} · TTS {'ON' if st['tts'] is True else 'OFF'}"
        if name == "VISÃO":
            return "ONLINE" if st.get("vision") else "N/D"
        if name == "TELEMETRIA":
            return f"CPU {int((s.get('cpu') or 0) * 100)}% · RAM {int((s.get('ram') or 0) * 100)}%"
        return "ATIVO" if self.vis[name] > .5 else "EM ESPERA"

    # ------------------------------------------------------------ desenho
    def draw(self, p, cx, cy, R, w, h, nodes=True, rx=0.0, ry=0.0):
        a, t, gt = self.a, self.a.t, self.gt
        en = clamp(a.energy + .5 * self.boost)
        awake = self.build
        breath = .5 + .5 * math.sin(t * 1.25)
        form = clamp(gt / 12.0)
        # --- núcleo de energia
        core_r = R * (.07 + .09 * form) * (1 + .2 * breath + .6 * self.pulse)
        gr = R * (.55 + 1.0 * form + .5 * self.pulse)
        gl = QRadialGradient(cx, cy, gr)
        gl.setColorAt(0, rgba(BLUE, 70 + 70 * form + 90 * self.pulse + 50 * awake))
        gl.setColorAt(1, rgba(DEEP, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gl))
        p.drawEllipse(QPointF(cx, cy), gr, gr)
        cg = QRadialGradient(cx, cy, core_r * 2.6)
        cg.setColorAt(0, rgba(ICE, 255))
        cg.setColorAt(.35, rgba(CYAN, 200))
        cg.setColorAt(1, rgba(BLUE, 0))
        p.setBrush(QBrush(cg))
        p.drawEllipse(QPointF(cx, cy), core_r * 2.6, core_r * 2.6)
        # --- partículas emitidas pelo núcleo
        for ang, r_, _sp, life, sz in self.sparks:
            p.setBrush(rgba(mixc(CYAN, ICE, .4), 200 * life))
            p.drawEllipse(QPointF(cx + math.cos(ang) * r_ * R * 1.6, cy + math.sin(ang) * r_ * R * 1.3), sz, sz)
        # --- projeção 3D das partículas que já nasceram
        ca, sa, cb, sb = math.cos(self.ang), math.sin(self.ang), math.cos(-.12), math.sin(-.12)
        sc = R * (1 + .02 * math.sin(t * 1.7) + .05 * self.pulse + .035 * awake)
        pr = []
        for n_, (x, y, z) in enumerate(self.P):
            age = gt - self.birth[n_]
            if age <= 0:
                pr.append(None)
                continue
            u = clamp(age / 1.6)
            e = 1 - (1 - u) ** 3                           # voa do núcleo até a posição final
            j_ = .025 * (en + self.pulse) * math.sin(t * 2.3 + n_ * 1.7)
            x, y, z = (x + j_) * e, (y + j_ * .7) * e, (z - j_) * e
            X, Z = x * ca + z * sa, -x * sa + z * ca
            Y, Z2 = y * cb - Z * sb, y * sb + Z * cb
            f = 1 / (1 - Z2 * .22)
            pr.append((cx + X * sc * 1.28 * f, cy + Y * sc * f, Z2, f, age))
        base = .12 + .30 * en + .06 * breath
        col = mixc(BLUE, CYAN, clamp(en + self.pulse))
        wv = self.wave * 1.3
        for k, (i, j) in enumerate(self.E):
            pa, pb = pr[i], pr[j]
            eg = clamp((gt - self.ebirth[k]) / 1.1)       # a linha neural se desenha de i para j
            if pa is None or pb is None or eg <= 0:
                continue
            z = (pa[2] + pb[2]) / 2
            r = (self.rad[i] + self.rad[j]) / 2
            front = max(0.0, 1 - abs(r - wv) * 4) if wv < 1.8 else 0.0
            flick = self.boost * (1.0 if math.sin(t * 9 + k * 1.3) > .6 else 0.0)
            al = 255 * (base * (.3 + .7 * (z + 1) / 2) + .5 * front + .35 * flick)
            p.setPen(QPen(rgba(mixc(col, ICE, front * .6 + flick * .4), al), 1))
            ex, ey = pa[0] + (pb[0] - pa[0]) * eg, pa[1] + (pb[1] - pa[1]) * eg
            p.drawLine(QPointF(pa[0], pa[1]), QPointF(ex, ey))
            if eg < 1:
                p.setPen(Qt.NoPen)
                p.setBrush(rgba(ICE, 230))
                p.drawEllipse(QPointF(ex, ey), 1.8, 1.8)
        p.setPen(Qt.NoPen)
        for k, q in enumerate(pr):
            if q is None:
                continue
            front = max(0.0, 1 - abs(self.rad[k] - wv) * 4) if wv < 1.8 else 0.0
            d = (q[2] + 1) / 2
            flash = max(0.0, 1 - (q[4] - 1.6) / .5) if q[4] > 1.6 else 1.0   # brilho ao encaixar
            p.setBrush(rgba(mixc(col, ICE, .3 + front * .6 + .5 * flash), (80 + 170 * d * (.4 + .6 * en)) * clamp(q[4] / .4) + 90 * front))
            r_ = (1.0 + 1.5 * d) * q[3] * (1 + front + .6 * flash)
            p.drawEllipse(QPointF(q[0], q[1]), r_, r_)
        for e_i, u, _s in self.pulses:                    # sinais correndo pelas sinapses
            i, j = self.E[e_i]
            pa, pb = pr[i], pr[j]
            if pa and pb:
                p.setBrush(rgba(ICE, 230))
                p.drawEllipse(QPointF(pa[0] + (pb[0] - pa[0]) * u, pa[1] + (pb[1] - pa[1]) * u), 2.2, 2.2)
        for i, j, age in self.xedges:                     # novas conexões criadas pelo chamado
            pa, pb = pr[i], pr[j]
            if pa and pb:
                k = clamp(age * 2.2)
                p.setPen(QPen(rgba(CYAN, 190 * (1 - age)), 1.1))
                p.drawLine(QPointF(pa[0], pa[1]), QPointF(pa[0] + (pb[0] - pa[0]) * k, pa[1] + (pb[1] - pa[1]) * k))

        # --- nós do plano (somente na tela cheia)
        self.nodes_screen = []
        if nodes:
            self._draw_nodes(p, cx, cy, R, w, h, rx, ry)

        # --- identidade: aparece quando o cérebro termina de se formar; intensifica ao despertar
        sc2 = clamp(R / 110, .55, 1.0)
        shown = clamp((gt - 8.5) / 3.0)
        title = QFont("Consolas", int(max(8, 15 * sc2)), QFont.Bold)
        title.setLetterSpacing(QFont.AbsoluteSpacing, 7 * sc2)
        ty = cy + R * 1.22
        p.setFont(title)
        p.setPen(rgba(mixc(BLUE, ICE, .35 + .5 * awake), (95 + 160 * awake) * shown))
        p.drawText(QRectF(0, ty, w, 24 * sc2 + 4), Qt.AlignCenter, "J.A.R.V.I.S.")
        sub = QFont("Consolas", int(max(7, 9 * sc2)))
        sub.setLetterSpacing(QFont.AbsoluteSpacing, 5 * sc2)
        p.setFont(sub)
        p.setPen(rgba(CYAN, (80 + 120 * awake) * shown))
        p.drawText(QRectF(0, ty + 24 * sc2 + 2, w, 16), Qt.AlignCenter, "NEURAL CORE")
        if nodes and awake > .15:
            p.setPen(rgba(CYAN if self.route_label() != "LOCAL" else (110, 150, 200), 230 * clamp(awake)))
            p.drawText(QRectF(0, ty + 24 * sc2 + 22, w, 16), Qt.AlignCenter, f"{self.vstate()}  ·  {self.route_label()}")

    def _draw_nodes(self, p, cx, cy, R, w, h, rx, ry):
        t = self.a.t
        label_f = QFont("Consolas", 8)
        label_f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        pos = {}
        for name, ang, orb in NODES:
            rad = math.radians(ang)
            if orb == "o":
                nx, ny = cx + math.cos(rad) * rx, cy + math.sin(rad) * ry
                ax, ay = cx + math.cos(rad) * R * 1.2, cy + math.sin(rad) * R * .95
            else:
                nx, ny = cx + math.cos(rad) * R * 2.0, cy + math.sin(rad) * R * 1.65
                ax, ay = cx + math.cos(rad) * R * 1.1, cy + math.sin(rad) * R * .9
            pos[name] = (nx, ny)
            gn, v = self.grow[name], self.vis[name]
            g = gn
            if name == "OLLAMA":
                g = gn * (1 - .85 * self.m)               # a conexão local diminui
            if name == "GPT":
                g = gn = max(gn, self.m * clamp(self.build * 3))   # nova conexão intensa até o GPT
            ctrl = QPointF((ax + nx) / 2 - math.sin(rad) * 26, (ay + ny) / 2 + math.cos(rad) * 26)
            path = QPainterPath(QPointF(ax, ay))
            path.quadTo(ctrl, QPointF(nx, ny))
            c = CYAN if name == "GPT" else BLUE
            if g > .01:
                seg = max(2, int(28 * g))
                pts_ = [path.pointAtPercent(g * k / seg) for k in range(seg + 1)]
                poly = QPainterPath(pts_[0])
                for q in pts_[1:]:
                    poly.lineTo(q)
                inten = g * (1 if name != "GPT" else .4 + .6 * self.m)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(rgba(c, 35 + 110 * inten), 3.5 * inten + .6))
                p.drawPath(poly)
                p.setPen(QPen(rgba(mixc(c, ICE, .5), 90 + 150 * inten), 1.3))
                p.drawPath(poly)
                p.setPen(Qt.NoPen)
                if g < .97:                                # ponta brilhante enquanto a sinapse cresce
                    p.setBrush(rgba(ICE, 240))
                    p.drawEllipse(pts_[-1], 3.2, 3.2)
                if g > .3:
                    for k in range(3 if (name == "GPT" and self.m > .02) else 2):
                        u = ((t * (.6 + .6 * inten) + k / 3 + ang / 360) % 1) * g
                        p.setBrush(rgba(ICE, 220 * inten))
                        p.drawEllipse(path.pointAtPercent(u), 2.5, 2.5)
            an = clamp((gn - .85) / .15)                   # o nó só existe depois que a conexão chega
            if an <= .02:
                continue
            fade = an * (1 - .55 * self.m if name == "OLLAMA" else 1)
            for rg in self.rings:
                if rg[0] == name:
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(rgba(CYAN, 210 * (1 - rg[1])), 1.6))
                    p.drawEllipse(QPointF(nx, ny), 8 + 38 * rg[1], 8 + 38 * rg[1])
            r_n = (3 if orb == "i" else 4) + 6 * v
            ng = QRadialGradient(nx, ny, r_n * 3.2)
            ng.setColorAt(0, rgba(c, (70 + 150 * v) * fade))
            ng.setColorAt(1, rgba(c, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(ng))
            p.drawEllipse(QPointF(nx, ny), r_n * 3.2, r_n * 3.2)
            p.setBrush(rgba(mixc((90, 130, 190), ICE, v * .8), (120 + 135 * v) * fade))
            p.drawEllipse(QPointF(nx, ny), r_n * .55, r_n * .55)
            p.setPen(QPen(rgba(c, (80 + 175 * v) * fade), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(nx, ny), r_n, r_n)
            if name == "GPT" and self.m > .97:              # GPT em destaque: ACTIVE
                pr_ = (t * .9) % 1
                p.setPen(QPen(rgba(CYAN, 200 * (1 - pr_)), 1.5))
                p.drawEllipse(QPointF(nx, ny), r_n + 4 + 22 * pr_, r_n + 4 + 22 * pr_)
            if an > .5:
                p.setFont(label_f)
                p.setPen(rgba(mixc((70, 110, 160), CYAN, v), (110 + 145 * v) * fade))
                above = ny < cy
                p.drawText(QRectF(nx - 70, ny + (-r_n - 16 if above else r_n + 3), 140, 13), Qt.AlignCenter, name)
                tag = "ACTIVE" if (name == "GPT" and self.m > .97) else ("LOCAL" if name == "OLLAMA" and self.m < .02 and v > .5 else "")
                if tag:
                    p.setPen(rgba(CYAN, 235))
                    p.drawText(QRectF(nx - 70, ny + (-r_n - 28 if above else r_n + 15), 140, 13), Qt.AlignCenter, tag)
                self.nodes_screen.append((nx, ny, name, self.node_text(name), c))
        arrived = [nm for nm in self.chain if self.grow[nm] > .97 and nm in pos]
        p.setBrush(Qt.NoBrush)
        for nm1, nm2 in zip(arrived, arrived[1:]):          # a cadeia do plano: nó → nó
            p.setPen(QPen(rgba(BLUE, 70), 1, Qt.DotLine))
            p.drawLine(QPointF(*pos[nm1]), QPointF(*pos[nm2]))


SIM = BrainSim()


class NeuralCore(QWidget):
    """Widget central da tela cheia: só desenha o SIM e trata o mouse (mic e nós)."""
    clicked = Signal()
    nodeClicked = Signal(str)

    def __init__(self, anim, live, backend):
        super().__init__()
        self.a, self.live, self.backend = anim, live, backend
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self._hover = None
        self._geo = (0.0, 0.0, 1.0)

    def _hit(self, pos):
        for i, (x, y, *_r) in enumerate(SIM.nodes_screen):
            if math.hypot(pos.x() - x, pos.y() - y) <= 14:
                return ("node", i)
        cx, cy, R = self._geo
        return ("core", 0) if math.hypot(pos.x() - cx, pos.y() - cy) <= R * 1.1 else None

    def mouseMoveEvent(self, e):
        hit = self._hit(e.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor)
        if hit and hit[0] == "node":
            _x, _y, name, txt, _c = SIM.nodes_screen[hit[1]]
            QToolTip.showText(e.globalPosition().toPoint(), f"{name}: {txt}", self)
        elif hit:
            on = self.backend.status["mic"] is True
            QToolTip.showText(e.globalPosition().toPoint(), "Clique para pausar a escuta" if on else "Clique para ativar a escuta", self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._hover:
            if self._hover[0] == "core":
                self.clicked.emit()
            elif self._hover[1] < len(SIM.nodes_screen):
                self.nodeClicked.emit(SIM.nodes_screen[self._hover[1]][2])

    def leaveEvent(self, e):
        self._hover = None
        QToolTip.hideText()

    def paintEvent(self, ev):
        SIM.step(self.a, self.live, self.backend)
        w, h = self.width(), self.height()
        cx, cy, R = w / 2, h * .45, min(w * .19, h * .25)
        self._geo = (cx, cy, R)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        SIM.draw(p, cx, cy, R, w, h, True, w * .41, h * .36)
        p.end()


class FlowLayer(QWidget):
    """Painéis nascem de partículas do cérebro e, ao fim da tarefa, se desfazem e voltam a ele."""

    def __init__(self, parent, core, panels):
        super().__init__(parent)
        self.core, self.panels, self.parts = core, panels, []
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def tick(self, dt):
        par = self.parentWidget()
        if not self.core.isVisible():
            self.parts.clear()
            return
        cx, cy, _R = self.core._geo
        c = self.core.mapTo(par, QPoint(int(cx), int(cy)))
        for name, wd in self.panels.items():
            d = SIM.pdelta.get(name, 0.0)
            if abs(d) < 1e-4 or not wd.isVisible() or len(self.parts) > 220:
                continue
            tl = wd.mapTo(par, QPoint(0, 0))
            for _ in range(int(min(4, abs(d) * 90 + random.random()))):
                rp = QPointF(tl.x() + random.random() * wd.width(), tl.y() + random.random() * wd.height())
                cp = QPointF(c.x(), c.y())
                a_, b_ = (cp, rp) if d > 0 else (rp, cp)    # d > 0 materializa · d < 0 dissolve
                self.parts.append([a_, b_, random.uniform(-70, 70), 0.0, random.uniform(.9, 1.7), d < 0])
        alive = []
        for q in self.parts:
            q[3] += dt * q[4]
            if q[3] < 1:
                alive.append(q)
            elif q[5]:
                SIM.pulse = min(1.0, SIM.pulse + .03)        # partículas voltando alimentam o cérebro
        self.parts = alive
        self.update()

    def paintEvent(self, ev):
        if not self.parts:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for a_, b_, off, u, _s, back in self.parts:
            e = u * u * (3 - 2 * u)
            mx, my = (a_.x() + b_.x()) / 2 + off, (a_.y() + b_.y()) / 2 + off * .6
            x = (1 - e) ** 2 * a_.x() + 2 * (1 - e) * e * mx + e * e * b_.x()
            y = (1 - e) ** 2 * a_.y() + 2 * (1 - e) * e * my + e * e * b_.y()
            p.setBrush(rgba(CYAN if back else ICE, 230 * math.sin(math.pi * clamp(u))))
            p.drawEllipse(QPointF(x, y), 2.0, 2.0)
        p.end()

# ============================================================
# EXECUTIVE CORE BRIDGE
# The MARK VII visual brain remains the UI surface. The autonomous
# executive core lives in autonomous_core.py so both layers can coexist.

def observe(data, foreground, conversation, *, speak=None, emit=None):
    from autonomous_core import observe as _observe
    return _observe(data, foreground, conversation, speak=speak, emit=emit)


def subscribe(fn):
    from autonomous_core import subscribe as _subscribe
    return _subscribe(fn)


def brain_status():
    from autonomous_core import brain_status as _brain_status
    return _brain_status()


def abort():
    from autonomous_core import abort as _abort
    return _abort()
