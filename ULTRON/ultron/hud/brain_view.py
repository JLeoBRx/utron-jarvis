"""BRAIN VIEW — desenha a ``NeuralScene`` (QPainter).

O cérebro é uma malha 3D de nós e sinapses que gira em perspectiva (pontos à frente são
maiores e mais claros), cercada pelo anel de subsistemas, com o título embaixo:

fundo → órbitas → auréola → sinapses da malha → sinapses do grafo → nós → regiões ativas
→ núcleo → sinais e pulsos → anel de subsistemas → título → vinheta → módulos neurais →
textos.

Desempenho: a projeção é feita em numpy a cada quadro; sinapses são agrupadas por
profundidade (poucas chamadas, canetas de 1 px no caminho rápido do QPainter); nós e brilhos
são sprites pré-renderizados (nós com centro em quartos de pixel: movimento suave sem custo
de antisserrilhamento); fundo, órbitas e auréola formam uma camada em cache, refeita só
quando a câmera ou a intensidade da auréola mudam.
"""
from __future__ import annotations

import math
import time
from collections import deque

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from . import theme
from .brain_model import LEFT_ONLY, REGIONS
from .scene import BOOT_PHASES, NeuralScene

QPointF, QRectF, QLineF = QtCore.QPointF, QtCore.QRectF, QtCore.QLineF
PLUS = QtGui.QPainter.CompositionMode_Plus
OVER = QtGui.QPainter.CompositionMode_SourceOver

STATUS_TONE = {"done": "gold", "running": "white", "unconfirmed": "amber", "failed": "amber", "skipped": "dim",
               "cancelled": "amber", "pending": "dim"}

RING_RX = 2.5                      # raio horizontal do anel (× escala do cérebro)
RING_RY = 1.375                    # raio vertical: o anel é visto em perspectiva
RING_BOTTOM = math.sin(math.radians(62))       # altura relativa dos nós mais baixos do anel
EDGE_ALPHA = (0.06, 0.10, 0.16, 0.25, 0.36)    # sinapses da malha, do fundo para a frente
POINT_RADIUS = (0.75, 1.0, 1.25, 1.55, 1.9)
NODE_RADIUS = (1.0, 1.3, 1.65)                 # nós do grafo, do fundo para a frente
MAX_STRONG_NODES = 48              # nós do grafo com brilho permanente (os mais fortes)
LEVELS = 10                        # níveis de intensidade das sinapses ativadas (desvanecimento suave)
ANGLE_STEP = 0.0005                # rad: resolução angular da camada da malha em cache
NODE_TONES = ("gold", "amber", "white")
GOLD_RGB, AMBER_RGB, WHITE_RGB = (theme.GOLD.getRgb()[:3], theme.AMBER.getRgb()[:3], theme.WARM_WHITE.getRgb()[:3])
# fase da inicialização → região que acende quando a fase é alcançada
BOOT_REGIONS = {3: "hippocampus", 4: "broca", 5: "frontal", 6: "parietal", 7: "motor", 8: "prefrontal",
                9: "auditory", 10: "occipital"}
BOOT_INDEX = {name: i for i, (_label, name) in enumerate(BOOT_PHASES) if name}
BOOT_INDEX.update({"skills": BOOT_INDEX["agent"], "voice_output": BOOT_INDEX["voice"], "health": len(BOOT_PHASES) - 1})
# status do subsistema → (tom do nó, opacidade do nó, cor do rótulo, opacidade do rótulo, palavra de status)
RING_LOOK = {
    "ok": ("gold", 0.95, theme.TEXT_DIM, 0.85, ""),
    "warn": ("amber", 0.95, theme.AMBER, 0.9, ""),
    "fail": ("amber", 0.85, theme.AMBER, 0.9, "FALHA"),
    "off": ("dim", 0.45, theme.TEXT_DIM, 0.45, "OFF"),
    "unknown": ("dim", 0.35, theme.TEXT_DIM, 0.4, ""),
}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def _mix(a: QtGui.QColor, b: QtGui.QColor, t: float) -> QtGui.QColor:
    return QtGui.QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                        int(a.blue() + (b.blue() - a.blue()) * t))


def _pen(c: QtGui.QColor, alpha: float, width: float = 1.0, *, round_cap: bool = False) -> QtGui.QPen:
    pen = QtGui.QPen(theme.with_alpha(c, alpha), width)
    if round_cap:
        pen.setCapStyle(QtCore.Qt.RoundCap)
    else:
        pen.setCosmetic(True)                        # 1 px: caminho rápido de linhas do QPainter
    return pen


def _polygon(xs: np.ndarray, ys: np.ndarray) -> QtGui.QPolygonF:
    return QtGui.QPolygonF(list(map(QPointF, xs.tolist(), ys.tolist())))


def _lines(x0: np.ndarray, y0: np.ndarray, x1: np.ndarray, y1: np.ndarray) -> list:
    return list(map(QLineF, x0.tolist(), y0.tolist(), x1.tolist(), y1.tolist()))


def _node_tone(node_type: str) -> int:
    if node_type in ("IDEA", "CONCEPT", "WORLD", "SCENARIO"):
        return 2
    return 1 if node_type in ("MEMORY", "DEVICE") else 0


class Frame:
    """Geometria de tela de um quadro: cérebro (centro e escala) e anel de subsistemas."""

    __slots__ = ("w", "h", "base", "R", "cx", "cy", "rcx", "rcy", "rrx", "rry", "ring_alpha")

    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)

    def ring_point(self, angle_deg: float) -> tuple[float, float]:
        a = math.radians(angle_deg)
        return self.rcx + self.rrx * math.cos(a), self.rcy + self.rry * math.sin(a)


class BrainView(QtWidgets.QWidget):
    def __init__(self, scene: NeuralScene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self.setMinimumSize(480, 320)
        self._background: QtGui.QPixmap | None = None
        self._vignette: QtGui.QPixmap | None = None
        self._base: QtGui.QPixmap | None = None          # fundo + órbitas + auréola
        self._base_key: tuple | None = None
        self.base_renders = 0
        self._texts: dict[tuple, QtGui.QStaticText] = {}
        self._panels: dict[str, tuple] = {}
        self._images: dict[str, QtGui.QPixmap | None] = {}
        self._graph: dict = {}
        self._graph_version = -1
        self._mesh_layer: QtGui.QPixmap | None = None    # malha + nós em repouso (recortada ao cérebro)
        self._mesh_origin = QPointF(0, 0)
        self._hard_key: tuple | None = None
        self._soft_key: tuple | None = None
        self._geometry_at = -1e9
        self._render_angle = 0.0                          # ângulo da camada atual (tudo preso a ela o usa)
        self.mesh_renders = 0
        self.frame_times: deque = deque(maxlen=600)       # duração de cada pintura (métricas)
        self.paint_count = 0
        self._point_colors = [_mix(theme.GOLD_DIM, _mix(theme.GOLD, theme.WARM_WHITE, 0.35), k / 4).getRgb()[:3]
                              for k in range(5)]
        self.stats: dict[str, int] = {}             # o que o último quadro desenhou (diagnóstico e testes)
        self.fps = 0.0
        self._frame_times: list[float] = []
        self._dpr = 1.0
        self.bottom_reserved = 70                   # pixels ocupados por controles sobrepostos (entrada, decisões)

    # ================================================================ geometria de tela
    def frame(self) -> Frame:
        w, h = max(1, self.width()), max(1, self.height())
        cam = self.scene.camera
        top, bottom = 84.0, h - 70.0 - 110.0        # topo: textos; base: transcrição e entrada
        base = max(30.0, min(w * 0.124, ((bottom - top) / 2 - 4) / (0.94 * RING_RY)))
        rcx, rcy = w / 2 + cam.shift * w, (top + bottom) / 2
        ring = base * min(1.0, cam.zoom)            # o anel encolhe para abrir espaço, mas não cresce
        R = base * cam.zoom
        return Frame(w=w, h=h, base=base, R=R, cx=rcx - cam.x * R, cy=rcy - cam.y * R, rcx=rcx, rcy=rcy,
                     rrx=ring * RING_RX, rry=ring * RING_RY, ring_alpha=_clamp(1.0 - (cam.zoom - 1.25) / 0.25))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._background = None
        self._vignette = None
        self._base_key = None
        super().resizeEvent(event)

    def _canvas(self, w: int, h: int) -> QtGui.QPixmap:
        pix = QtGui.QPixmap(max(1, int(w * self._dpr)), max(1, int(h * self._dpr)))
        pix.setDevicePixelRatio(self._dpr)
        return pix

    def _ensure_backgrounds(self) -> None:
        w, h = max(1, self.width()), max(1, self.height())
        if self._background is not None and abs(self._background.devicePixelRatio() - self._dpr) > 1e-3:
            self._background = self._vignette = None
        if self._background is None:
            pix = self._canvas(w, h)
            p = QtGui.QPainter(pix)
            grad = QtGui.QRadialGradient(w * 0.5, h * 0.44, max(w, h) * 0.75)
            grad.setColorAt(0.0, QtGui.QColor(20, 18, 16))
            grad.setColorAt(0.55, QtGui.QColor(9, 9, 9))
            grad.setColorAt(1.0, theme.BLACK)
            p.fillRect(0, 0, w, h, grad)
            rng = np.random.default_rng(5)                      # grão fino estático (sem animação)
            p.setPen(QtGui.QColor(255, 255, 255, 6))
            for x, y in rng.integers(0, [w, h], size=(int(w * h / 900), 2)):
                p.drawPoint(int(x), int(y))
            p.end()
            self._background = pix
        if self._vignette is None:
            pix = self._canvas(w, h)
            pix.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pix)
            grad = QtGui.QRadialGradient(w * 0.5, h * 0.46, max(w, h) * 0.68)
            grad.setColorAt(0.55, QtGui.QColor(0, 0, 0, 0))
            grad.setColorAt(1.0, QtGui.QColor(0, 0, 0, 255))
            p.fillRect(0, 0, w, h, grad)
            p.end()
            self._vignette = pix

    # ================================================================ pintura
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        started = time.perf_counter()
        scene = self.scene
        self._dpr = self.devicePixelRatioF()
        self._ensure_backgrounds()
        fr = self.frame()
        self.stats = {}
        self._ensure_base(fr)
        p = QtGui.QPainter(self)
        p.drawPixmap(0, 0, self._base)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self._draw_brain(p, fr)
        self._draw_ring(p, fr)
        self._draw_title(p, fr)
        p.drawPixmap(0, 0, self._vignette)
        if scene.suspense > 0.03 or scene.dim > 0.01:
            p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, int(min(200, 70 * scene.suspense + 140 * scene.dim))))
        self._draw_modules(p, fr)
        self._draw_overlay_text(p, fr)
        p.end()
        elapsed = time.perf_counter() - started
        self.frame_times.append(elapsed)
        self.paint_count += 1
        self._frame_times.append(elapsed)
        if len(self._frame_times) >= 30:
            self.fps = 1.0 / max(1e-6, sum(self._frame_times) / len(self._frame_times))
            self._frame_times.clear()

    def _sprite(self, p: QtGui.QPainter, kind: str, tone: str, x: float, y: float, r: float,
                opacity: float, *, clip: bool = True) -> None:
        """Brilho pré-renderizado, desenhado sem escala em espaço de dispositivo."""
        if opacity <= 0.004 or r <= 0.5:
            return
        radius = theme.quantize_radius(r)
        if clip and (x + radius < 0 or y + radius < 0 or x - radius > self.width() or y - radius > self.height()):
            return
        p.setOpacity(min(1.0, opacity))
        p.drawPixmap(QPointF(x - radius, y - radius), theme.sprite_px(kind, tone, radius, self._dpr))

    def _dots(self, p: QtGui.QPainter, xs: np.ndarray, ys: np.ndarray, rgb: tuple, radius: float,
              opacity: float) -> None:
        """Nós como sprites com centro em quartos de pixel (suave e mais rápido que pontos
        antisserrilhados)."""
        if not len(xs) or opacity <= 0.004:
            return
        ix, iy = np.floor(xs), np.floor(ys)
        qx = ((xs - ix) * 4).astype(np.int32)
        qy = ((ys - iy) * 4).astype(np.int32)
        half = theme.dot_size(radius) // 2
        sprites = [[theme.dot_px(rgb, radius, a, b, self._dpr) for b in range(4)] for a in range(4)]
        p.setOpacity(min(1.0, opacity))
        draw = p.drawPixmap
        for x, y, a, b in zip((ix - half).astype(np.int32).tolist(), (iy - half).astype(np.int32).tolist(),
                              qx.tolist(), qy.tolist()):
            draw(x, y, sprites[a][b])
        p.setOpacity(1.0)

    def _glows(self, p: QtGui.QPainter, xs, ys, tones, radii, opacities) -> None:
        """Brilhos em lote: agrupados por (tom, raio, opacidade em 8 níveis) — uma troca de estado por
        grupo e desenho em coordenadas inteiras (sinais em movimento dispensam subpixel)."""
        if not len(xs):
            return
        groups: dict[tuple, list] = {}
        w, h = self.width(), self.height()
        for x, y, tone, r, o in zip(xs, ys, tones, radii, opacities):
            if o <= 0.01 or r <= 0.5:
                continue
            radius = theme.quantize_radius(r)
            if x + radius < 0 or y + radius < 0 or x - radius > w or y - radius > h:
                continue
            groups.setdefault((tone, radius, min(7, int(o * 8))), []).append((int(x) - radius, int(y) - radius))
        draw = p.drawPixmap
        for (tone, radius, level), points in groups.items():
            pix = theme.sprite_px("glow", tone, radius, self._dpr)
            p.setOpacity((level + 0.5) / 8)
            for x, y in points:
                draw(x, y, pix)
        p.setOpacity(1.0)

    def _core_reveal(self) -> float:
        boot = self.scene.boot
        return 1.0 if not boot.active else _clamp(boot.shown - 0.4)

    def _ring_reveal(self, sub) -> float:
        boot = self.scene.boot
        if not boot.active:
            return 1.0
        phase = min((BOOT_INDEX.get(c, len(BOOT_PHASES) - 1) for c in sub.components), default=0)
        return _clamp(boot.shown - phase + 1.0)

    # ---------------------------------------------------------------- camada base (cache)
    def _halo_level(self) -> float:
        scene = self.scene
        activity = sum(scene.region_activity.values()) / max(1, len(scene.region_activity))
        level = (0.05 + 0.025 * math.sin(2 * math.pi * scene.breath) + 0.22 * activity
                 + 0.3 * scene.release) * self._core_reveal()
        return round(level / 0.012) * 0.012                    # quantizado: o cache vale vários quadros

    def _ensure_base(self, fr: Frame) -> None:
        orbit = round(fr.ring_alpha * self._core_reveal(), 2)
        halo = self._halo_level()
        key = (fr.w, fr.h, round(self._dpr, 2), round(fr.cx, 1), round(fr.cy, 1), round(fr.R, 1),
               round(fr.rcx, 1), round(fr.rcy, 1), round(fr.rrx, 1), round(fr.rry, 1), orbit, halo)
        if key == self._base_key and self._base is not None:
            return
        pix = self._canvas(fr.w, fr.h)
        p = QtGui.QPainter(pix)
        p.drawPixmap(0, 0, self._background)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self._draw_orbits(p, fr, orbit)
        p.setCompositionMode(PLUS)
        self._sprite(p, "soft", "gold", fr.cx, fr.cy, fr.R * 1.55, halo)
        p.end()
        self._base, self._base_key = pix, key
        self.base_renders += 1

    def _draw_orbits(self, p: QtGui.QPainter, fr: Frame, alpha: float) -> None:
        if alpha <= 0.01:
            return
        p.setBrush(QtCore.Qt.NoBrush)
        center = QPointF(fr.rcx, fr.rcy)
        p.setPen(_pen(theme.GOLD, 0.10 * alpha))
        p.drawEllipse(center, fr.rrx, fr.rry)
        p.setPen(_pen(theme.GOLD, 0.05 * alpha))
        p.drawEllipse(center, fr.rrx * 0.80, fr.rry * 0.80)
        p.drawEllipse(center, fr.rrx * 1.12, fr.rry * 1.12)

    # ---------------------------------------------------------------- cérebro
    def _ensure_graph(self) -> dict:
        scene = self.scene
        if self._graph_version == scene.graph_version and self._graph:
            return self._graph
        nodes = list(scene.nodes.values())
        index = {node.id: i for i, node in enumerate(nodes)}
        pos = np.array([(n.x, n.y, n.z) for n in nodes], dtype=np.float64).reshape(-1, 3)
        strength = np.array([n.strength for n in nodes], dtype=np.float64)
        tone = np.array([_node_tone(n.type) for n in nodes], dtype=np.int32)
        strong = np.argsort(-strength)[:MAX_STRONG_NODES] if len(nodes) else np.zeros(0, dtype=np.int64)
        strong = strong[strength[strong] >= 0.5] if len(strong) else strong
        self._graph = {"nodes": nodes, "index": index, "pos": pos, "strength": strength, "tone": tone,
                       "strong": strong}
        self._graph_version = scene.graph_version
        return self._graph

    def _boot_flash(self) -> dict[str, float]:
        boot = self.scene.boot
        if not boot.active:
            return {}
        flash = {}
        for phase, region in BOOT_REGIONS.items():
            v = _clamp(boot.shown - (phase - 1))
            if 0.0 < v < 1.0:
                flash[region] = flash.get(region, 0.0) + 1.4 * v * (1 - v)     # acende ao surgir e assenta
        return flash

    def _draw_brain(self, p: QtGui.QPainter, fr: Frame) -> None:
        scene, mesh, cam = self.scene, self.scene.mesh, self.scene.camera
        profile = scene.profile
        now = scene.clock()
        core_reveal = self._core_reveal()
        genesis = scene.genesis()
        inner = _clamp((scene.depth - 3.0) / 5.0)       # profundidade cognitiva revela estruturas internas
        shell = (1.0 - 0.35 * inner) * (1.0 - 0.3 * scene.dim)
        indices = mesh.visible_indices(scene.development, profile.mesh_points)
        # Cadência da geometria: girando livre, a malha é redesenhada no máximo ``geometry_fps``
        # vezes por segundo; tudo que se prende a ela (nós, sinais, regiões, âncoras) usa o mesmo
        # ângulo da camada — alinhado — enquanto sinais e painéis seguem no ritmo pleno.
        # Mudança estrutural (enquadramento, zoom, tamanho, perfil) → redesenho imediato; mudança suave
        # (giro, nós novos no grafo, profundidade, nascimento) → no máximo ``geometry_fps`` por segundo.
        hard_key = (fr.w, fr.h, round(self._dpr, 2), round(fr.cx, 1), round(fr.cy, 1), round(fr.R, 1), profile.name)
        soft_key = (len(indices), round(genesis, 3), round(inner, 2), round(shell, 2), scene.graph_version)
        quantized = round(cam.angle / ANGLE_STEP) * ANGLE_STEP
        clock = scene.clock()
        reuse = (self._mesh_layer is not None and hard_key == self._hard_key
                 and ((soft_key == self._soft_key and quantized == self._render_angle)
                      or clock - self._geometry_at < 1.0 / max(1, profile.geometry_fps)))
        angle = self._render_angle if reuse else quantized
        self._render_angle = angle
        sx, sy, Z, _f = mesh.project(mesh.points, angle, fr.cx, fr.cy, fr.R)
        depth = np.clip((Z + 1.05) / 2.1, 0.0, 1.0)
        visible = np.zeros(len(mesh.points), dtype=bool)
        visible[indices] = True
        if genesis < 1.0:
            visible &= mesh.genesis_rank <= genesis
        if inner < 0.02:
            visible &= ~mesh.inner_mask
        edges = mesh.edges(indices)
        a, b = edges[:, 0], edges[:, 1]
        keep = visible[a] & visible[b]
        a, b = a[keep], b[keep]
        graph = self._ensure_graph()
        reveal = _clamp((genesis - 0.4) / 0.6)
        gsx = gsy = gdepth = gf = None
        if graph["nodes"] and reveal > 0:
            gsx, gsy, gZ, gf = mesh.project(graph["pos"], angle, fr.cx, fr.cy, fr.R)
            gdepth = np.clip((gZ + 1.05) / 2.1, 0.0, 1.0)
        # camada estável (malha + nós em repouso), refeita só quando a geometria vista muda
        if not reuse:
            mesh_args = (sx, sy, depth, visible, a, b, genesis, inner, shell, graph, gsx, gsy, gdepth, gf, reveal)
            self._render_mesh_layer(fr, mesh_args)
            self._hard_key, self._soft_key, self._geometry_at = hard_key, soft_key, clock
            self.mesh_renders += 1
        p.drawPixmap(self._mesh_origin, self._mesh_layer)
        self.stats.update(points=int(visible.sum()), edges=int(len(a)),
                          graph_nodes=len(graph["nodes"]) if reveal > 0 else 0)
        self._draw_graph_activity(p, fr, graph, gsx, gsy, gf, reveal, now)
        self._draw_regions(p, fr, sx, sy, depth, visible, a, b)
        self._draw_core(p, fr, core_reveal, now)
        self._draw_signals(p, fr, now)

    def _render_mesh_layer(self, fr: Frame, mesh_args: tuple) -> None:
        """Desenha a malha e os nós em repouso numa camada recortada ao tamanho do cérebro."""
        sx, sy, visible, gsx, gsy = mesh_args[0], mesh_args[1], mesh_args[3], mesh_args[10], mesh_args[11]
        xs, ys = sx[visible], sy[visible]
        if gsx is not None:
            xs, ys = np.concatenate([xs, gsx]), np.concatenate([ys, gsy])
        if len(xs):
            x0 = int(max(0.0, float(xs.min()) - 10)); y0 = int(max(0.0, float(ys.min()) - 10))
            x1 = int(min(fr.w, float(xs.max()) + 11)); y1 = int(min(fr.h, float(ys.max()) + 11))
        else:
            x0 = y0 = 0
            x1 = y1 = 1
        width, height = max(1, x1 - x0), max(1, y1 - y0)
        pix = self._mesh_layer
        if pix is None or pix.width() < width * self._dpr or pix.height() < height * self._dpr \
                or abs(pix.devicePixelRatio() - self._dpr) > 1e-3 \
                or pix.width() > 1.6 * width * self._dpr + 64 or pix.height() > 1.6 * height * self._dpr + 64:
            pix = QtGui.QPixmap(max(1, int((width + 32) * self._dpr)), max(1, int((height + 32) * self._dpr)))
            pix.setDevicePixelRatio(self._dpr)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.translate(-x0, -y0)
        self._paint_mesh(p, *mesh_args)
        p.end()
        self._mesh_layer, self._mesh_origin = pix, QPointF(x0, y0)

    def _paint_mesh(self, p: QtGui.QPainter, sx, sy, depth, visible, a, b, genesis: float, inner: float,
                    shell: float, graph: dict, gsx, gsy, gdepth, gf, reveal: float) -> None:
        mesh, profile = self.scene.mesh, self.scene.profile
        level = np.minimum(4, (depth * 5).astype(np.int32))
        deep = mesh.inner_mask[a] | mesh.inner_mask[b]
        edge_level = np.minimum(level[a], level[b])
        first = 5 - max(1, min(5, profile.depth_levels))      # camadas do fundo omitidas pelo perfil
        for k in range(first, 5):
            sel = (edge_level == k) & ~deep
            if sel.any():
                p.setPen(_pen(theme.GOLD, EDGE_ALPHA[k] * shell))
                p.drawLines(_lines(sx[a[sel]], sy[a[sel]], sx[b[sel]], sy[b[sel]]))
        if deep.any():
            p.setPen(_pen(theme.WARM_WHITE, 0.30 * inner))
            p.drawLines(_lines(sx[a[deep]], sy[a[deep]], sx[b[deep]], sy[b[deep]]))
        shell_points = visible & ~mesh.inner_mask                # nós da malha: maiores e mais claros à frente
        for k in range(max(0, first - 1), 5):
            sel = shell_points & (level == k)
            self._dots(p, sx[sel], sy[sel], self._point_colors[k], POINT_RADIUS[k],
                       (0.30 + 0.70 * (k / 4) ** 1.2) * shell)
        deep_points = visible & mesh.inner_mask
        self._dots(p, sx[deep_points], sy[deep_points], WHITE_RGB, 1.3, 0.75 * inner)
        p.setCompositionMode(PLUS)
        if profile.front_glow:                                   # cintilação dos nós mais próximos
            for i in np.nonzero(shell_points & (depth > 0.90))[0]:
                self._sprite(p, "glow", "gold", sx[i], sy[i], 4.0, 0.16 * shell, clip=False)
        if genesis < 1.0:                                        # nós nascendo (inicialização)
            for i in np.nonzero(visible & (mesh.genesis_rank > genesis - 0.05))[0]:
                self._sprite(p, "glow", "white", sx[i], sy[i], 5.0, 0.85, clip=False)
        p.setOpacity(1.0)
        p.setCompositionMode(OVER)
        if gsx is not None:                                      # nós reais do Neural Graph
            tone = graph["tone"]
            glevel = np.minimum(2, (gdepth * 3).astype(np.int32))
            for t, rgb in enumerate((GOLD_RGB, AMBER_RGB, WHITE_RGB)):
                for k, alpha in enumerate((0.35, 0.6, 0.9)):
                    sel = (tone == t) & (glevel == k)
                    self._dots(p, gsx[sel], gsy[sel], rgb, NODE_RADIUS[k], alpha * reveal)
            if profile.strong_glow:
                p.setCompositionMode(PLUS)
                strength = graph["strength"]
                for i in graph["strong"][: profile.strong_glow]:   # conhecimento consolidado brilha
                    if gdepth[i] > 0.45:
                        self._sprite(p, "glow", NODE_TONES[tone[i]], gsx[i], gsy[i], (3.5 + 3 * strength[i]) * gf[i],
                                     (0.10 + 0.25 * strength[i]) * gdepth[i] * reveal, clip=False)
                p.setOpacity(1.0)
                p.setCompositionMode(OVER)

    def _draw_graph_activity(self, p: QtGui.QPainter, fr: Frame, graph: dict, sx, sy, f, reveal: float,
                             now: float) -> None:
        """Sinapses do grafo percorridas por um sinal real e nós ativados ou recém-nascidos."""
        scene, mesh, profile = self.scene, self.scene.mesh, self.scene.profile
        self.stats["graph_edges"] = 0
        if sx is None or reveal <= 0:
            return
        index = graph["index"]
        hot = [(index[e.a], index[e.b], min(LEVELS - 1, int(e.activation * LEVELS)))
               for e in scene.hot_edges(profile.active_edges) if e.a in index and e.b in index]
        self.stats["graph_edges"] = len(hot)
        if hot:                                                  # na mesma curva das partículas da cena
            ij = np.array(hot, dtype=np.int64)
            p0, p1 = graph["pos"][ij[:, 0]], graph["pos"][ij[:, 1]]
            ctrl = (p0 + p1) * 0.4
            t = np.linspace(0.0, 1.0, max(1, profile.curve_steps) + 1)[None, :, None]
            curve = (1 - t) ** 2 * p0[:, None] + 2 * (1 - t) * t * ctrl[:, None] + t ** 2 * p1[:, None]
            cx, cy, _cz, _cf = mesh.project(curve.reshape(-1, 3), self._render_angle, fr.cx, fr.cy, fr.R)
            cx, cy = cx.reshape(len(hot), -1), cy.reshape(len(hot), -1)
            for lvl in np.unique(ij[:, 2]):
                rows = ij[:, 2] == lvl
                faint = lvl < 3                          # opacidade < 20%: serrilhado imperceptível, 3× mais barato
                if faint:
                    p.setRenderHint(QtGui.QPainter.Antialiasing, False)
                p.setPen(_pen(theme.GOLD, 0.55 * (lvl + 0.5) / LEVELS * reveal))
                p.drawLines(_lines(cx[rows, :-1].ravel(), cy[rows, :-1].ravel(),
                                   cx[rows, 1:].ravel(), cy[rows, 1:].ravel()))
                if faint:
                    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        glowing = scene.glowing_nodes(profile.max_particles)
        if glowing:
            tone = graph["tone"]
            xs, ys, tones, radii, alphas = [], [], [], [], []
            for node, age in glowing:
                i = index.get(node.id)
                if i is None:
                    continue
                xs.append(sx[i]); ys.append(sy[i]); tones.append(NODE_TONES[tone[i]])
                radii.append((5.0 + 7.0 * node.activation) * f[i])
                alphas.append((0.85 * node.activation + (1.0 - _clamp(age / 0.8)) * 0.9) * reveal)
            p.setCompositionMode(PLUS)
            self._glows(p, xs, ys, tones, radii, alphas)
            p.setCompositionMode(OVER)

    def _region_screen(self, fr: Frame, name: str, near: tuple[float, float] | None = None
                       ) -> tuple[float, float, float]:
        """Centro projetado da região (x, y, profundidade 0..1). Regiões laterais existem nos
        dois hemisférios: vale o do lado voltado para o observador ou, com ``near``, o mais
        próximo desse ponto da tela (a sinapse não atravessa o cérebro sem necessidade)."""
        mesh = self.scene.mesh
        lateral = REGIONS.get(name, REGIONS["core"])[2] != 0 and name not in LEFT_ONLY
        sides = (1.0, -1.0) if lateral else (1.0,)
        points = np.array([mesh.region_center(name, side) for side in sides])
        sx, sy, Z, _f = mesh.project(points, self._render_angle, fr.cx, fr.cy, fr.R)
        if len(sides) == 1:
            k = 0
        elif near is None:
            k = int(np.argmax(Z))
        else:
            k = int(np.argmin((sx - near[0]) ** 2 + (sy - near[1]) ** 2))
        return float(sx[k]), float(sy[k]), float(np.clip((Z[k] + 1.05) / 2.1, 0.0, 1.0))

    def _draw_regions(self, p: QtGui.QPainter, fr: Frame, sx, sy, depth, visible, a, b) -> None:
        """Regiões funcionais em atividade real: halo, nós e sinapses da região acendem."""
        scene, mesh = self.scene, self.scene.mesh
        flash = self._boot_flash()
        p.setCompositionMode(PLUS)
        lit = 0
        for name, level in scene.region_activity.items():
            amount = level + flash.get(name, 0.0)
            if amount < 0.02:
                continue
            lit += 1
            x, y, d = self._region_screen(fr, name)
            tone = "white" if name in ("auditory", "broca") and level > 0.5 else "gold"
            self._sprite(p, "soft", tone, x, y, REGIONS[name][3] * fr.R * 1.9, min(1.0, amount * 0.75))
            p.setOpacity(1.0)
            members = mesh.membership[name]
            members = members[visible[members]]
            if not len(members):
                continue
            inside = np.zeros(len(visible), dtype=bool)
            inside[members] = True
            sel = inside[a] & inside[b]
            if scene.profile.region_lines and sel.any():
                p.setPen(_pen(theme.GOLD, min(1.0, 0.12 + 0.5 * amount)))
                p.drawLines(_lines(sx[a[sel]], sy[a[sel]], sx[b[sel]], sy[b[sel]]))
            front = members[depth[members] > 0.5]
            back = members[depth[members] <= 0.5]
            for group, alpha, radius in ((front, 0.85, 1.6), (back, 0.35, 1.2)):
                self._dots(p, sx[group], sy[group], WHITE_RGB, radius, min(1.0, amount) * alpha)
        p.setCompositionMode(OVER)
        self.stats["regions"] = lit

    def _draw_core(self, p: QtGui.QPainter, fr: Frame, reveal: float, now: float) -> None:
        scene = self.scene
        heartbeat = 0.5 + 0.5 * math.sin(now * 2 * math.pi * 0.8) if scene.suspense > 0.2 else 0.0
        booting = 1.0 if scene.boot.active else 0.0
        online = _clamp(scene.boot.shown - 10.0) if scene.boot.active else 1.0
        glow = reveal * (0.30 + 0.45 * (1 - online) * booting + 0.4 * heartbeat * scene.suspense + 0.3 * scene.release)
        p.setCompositionMode(PLUS)
        self._sprite(p, "glow", "white", fr.cx, fr.cy, (0.07 + 0.05 * scene.release) * fr.R, glow)
        p.setOpacity(1.0)
        p.setCompositionMode(OVER)

    def _draw_signals(self, p: QtGui.QPainter, fr: Frame, now: float) -> None:
        """Partículas (sinais reais entre nós e regiões) e pulsos de estímulo."""
        scene, mesh = self.scene, self.scene.mesh
        active = [pt for pt in scene.particles if pt.t >= 0]
        if active:
            sx, sy, _Z, f = mesh.project(np.array([pt.position() for pt in active]), self._render_angle,
                                         fr.cx, fr.cy, fr.R)
            p.setCompositionMode(PLUS)
            self._glows(p, sx.tolist(), sy.tolist(), [pt.tone for pt in active],
                        [3.2 * pt.size * fi for pt, fi in zip(active, f.tolist())],
                        [0.9 * math.sin(math.pi * min(1.0, pt.t)) for pt in active])
            p.setCompositionMode(OVER)
        pulses = [pulse for pulse in scene.pulses if 0 <= now - pulse.born <= pulse.duration]
        if pulses:
            sx, sy, _Z, f = mesh.project(np.array([(q.x, q.y, q.z) for q in pulses]), self._render_angle,
                                         fr.cx, fr.cy, fr.R)
            p.setBrush(QtCore.Qt.NoBrush)
            for i, pulse in enumerate(pulses):
                t = (now - pulse.born) / pulse.duration
                ease = 1 - (1 - t) ** 3
                p.setPen(_pen(theme.TONES.get(pulse.tone, theme.GOLD), 0.6 * pulse.strength * (1 - t) ** 1.5))
                r = pulse.radius * fr.R * f[i] * ease
                p.drawEllipse(QPointF(sx[i], sy[i]), r * 1.2, r * 0.9)
        self.stats["signals"] = len(active) + len(pulses)

    # ---------------------------------------------------------------- anel de subsistemas
    def _draw_ring(self, p: QtGui.QPainter, fr: Frame) -> None:
        scene = self.scene
        alpha = fr.ring_alpha * self._core_reveal()
        shown = synapses = 0
        if alpha > 0.01:
            now = scene.clock()
            arrivals = dict(scene.ring_pulses)
            for sub in scene.subsystems.values():
                reveal = self._ring_reveal(sub) * alpha
                if reveal <= 0.01:
                    continue
                shown += 1
                nx, ny = fr.ring_point(sub.angle)
                tone, dot_alpha, label_color, label_alpha, word = RING_LOOK.get(sub.status, RING_LOOK["unknown"])
                if sub.grow > 0.01:                           # sinapse até o cérebro: só cresce durante o uso
                    synapses += 1
                    self._draw_ring_synapse(p, fr, sub, nx, ny, reveal, now)
                p.setCompositionMode(PLUS)
                self._sprite(p, "glow", tone if tone != "dim" else "gold", nx, ny, 9 + 5 * sub.activity,
                             (0.18 + 0.6 * sub.activity) * dot_alpha * reveal)
                if sub.name in arrivals:                       # o sinal chegou ao subsistema
                    age = _clamp(now - arrivals[sub.name])
                    p.setOpacity(1.0)
                    p.setCompositionMode(OVER)
                    p.setBrush(QtCore.Qt.NoBrush)
                    p.setPen(_pen(theme.WARM_WHITE, 0.7 * (1 - age) * reveal))
                    p.drawEllipse(QPointF(nx, ny), 4 + 16 * age, 4 + 16 * age)
                p.setOpacity(1.0)
                p.setCompositionMode(OVER)
                c = theme.TONES.get(tone, theme.GOLD)
                if sub.status == "fail":
                    p.setBrush(QtCore.Qt.NoBrush)
                    p.setPen(QtGui.QPen(theme.with_alpha(c, dot_alpha * reveal), 1.2))
                    p.drawEllipse(QPointF(nx, ny), 3.2, 3.2)
                else:
                    p.setPen(QtCore.Qt.NoPen)
                    p.setBrush(theme.with_alpha(c, dot_alpha * reveal))
                    p.drawEllipse(QPointF(nx, ny), 2.8, 2.8)
                label = _mix(label_color, theme.WARM_WHITE, sub.activity) if sub.status == "ok" else label_color
                self._centered(p, sub.name, theme.font(7, weight=600, spacing=1.8),
                               theme.with_alpha(label, min(1.0, label_alpha + 0.2 * sub.activity) * reveal),
                               nx, ny - 19)
                if word:
                    self._centered(p, word, theme.font(6, weight=600, spacing=1.5),
                                   theme.with_alpha(label_color, 0.8 * reveal), nx, ny + 6)
        self.stats.update(ring=shown, synapses=synapses)

    def _draw_ring_synapse(self, p: QtGui.QPainter, fr: Frame, sub, nx: float, ny: float, reveal: float,
                           now: float) -> None:
        ax, ay, _d = self._region_screen(fr, sub.region, near=(nx, ny))
        mx, my = (ax + nx) / 2, (ay + ny) / 2
        kx, ky = mx + (mx - fr.rcx) * 0.18, my + (my - fr.rcy) * 0.18      # curva para fora do anel
        t = np.linspace(0.0, sub.grow, 18)
        u = 1 - t
        xs = u * u * ax + 2 * u * t * kx + t * t * nx
        ys = u * u * ay + 2 * u * t * ky + t * t * ny
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(_pen(theme.GOLD, (0.16 + 0.45 * sub.activity) * reveal))
        p.drawPolyline(_polygon(xs, ys))
        if sub.activity > 0.12:                           # sinal percorrendo a sinapse
            s = ((now * 0.9 + sub.angle / 360.0) % 1.0) * sub.grow
            v = 1 - s
            x = v * v * ax + 2 * v * s * kx + s * s * nx
            y = v * v * ay + 2 * v * s * ky + s * s * ny
            p.setCompositionMode(PLUS)
            self._sprite(p, "glow", "gold", x, y, 4.0, 0.85 * sub.activity * reveal)
            p.setOpacity(1.0)
            p.setCompositionMode(OVER)

    # ---------------------------------------------------------------- textos em cache
    def _static(self, text: str, font: QtGui.QFont) -> QtGui.QStaticText:
        key = (text, font.key())
        st = self._texts.get(key)
        if st is None:
            if len(self._texts) > 400:
                self._texts.clear()
            st = QtGui.QStaticText(text)
            st.setTextFormat(QtCore.Qt.PlainText)
            st.prepare(QtGui.QTransform(), font)
            self._texts[key] = st
        return st

    def _centered(self, p: QtGui.QPainter, text: str, font: QtGui.QFont, color: QtGui.QColor, x: float,
                  top: float, *, shadow: bool = False) -> None:
        st = self._static(text, font)
        pos = QPointF(x - st.size().width() / 2, top)
        p.setFont(font)
        if shadow:
            p.setPen(QtGui.QColor(0, 0, 0, int(200 * color.alphaF())))
            p.drawStaticText(pos + QPointF(0, 1), st)
        p.setPen(color)
        p.drawStaticText(pos, st)

    # ---------------------------------------------------------------- título
    def _draw_title(self, p: QtGui.QPainter, fr: Frame) -> None:
        scene = self.scene
        alpha = fr.ring_alpha * self._core_reveal()
        if alpha <= 0.01:
            return
        top = min(fr.cy + 0.93 * fr.R + 12, fr.rcy + RING_BOTTOM * fr.rry - 26)
        state = "BOOT" if scene.boot.active else scene.runtime_state.replace("_", " ")
        privacy = scene.state.get("privacy") or {}
        mode = "LOCAL" if privacy.get("local_mode") else str(privacy.get("mode") or "").upper()
        alert = not scene.boot.active and scene.runtime_state in ("AWAITING_AUTHORIZATION", "ERROR")
        self._centered(p, "ULTRON", theme.font(14, weight=600, spacing=9),
                       theme.with_alpha(theme.WARM_WHITE, 0.92 * alpha), fr.rcx, top, shadow=True)
        self._centered(p, "NEURAL CORE", theme.font(7.5, weight=600, spacing=5),
                       theme.with_alpha(theme.GOLD, 0.9 * alpha), fr.rcx, top + 25, shadow=True)
        self._centered(p, f"{state} · {mode}" if mode else state, theme.font(7, weight=500, spacing=3.5),
                       theme.with_alpha(theme.AMBER if alert else theme.TEXT_DIM, 0.9 * alpha), fr.rcx, top + 41,
                       shadow=True)

    # ---------------------------------------------------------------- módulos neurais
    def _module_layout(self) -> list[tuple]:
        modules = self.scene.visible_modules()
        w, h = self.width(), self.height()
        width = min(360, max(250, int(w * 0.26)))
        columns = {"left": 84, "right": 84}
        out = []
        for module in modules:
            side = self.scene.module_side(module)
            height = 34 + sum(self._line_height(line) for line in module.lines) + 10
            x = 22 if side == "left" else w - width - 22
            y = columns[side]
            if y + height > h - 150:
                continue
            columns[side] += height + 14
            out.append((module, QRectF(x, y, width, height), side))
        return out

    @staticmethod
    def _line_height(line) -> int:
        if isinstance(line, tuple):
            if line[0] == "option":
                return 40
            if line[0] == "image":
                return 96
            if line[0] == "chain":
                return 22
        return 19

    def _draw_modules(self, p: QtGui.QPainter, fr: Frame) -> None:
        now = self.scene.clock()
        for module, rect, side in self._module_layout():
            alpha = module.alpha
            if alpha < 0.02:
                continue
            end = QPointF(rect.right() if side == "left" else rect.left(), rect.top() + 18)
            ax, ay, _d = self._region_screen(fr, module.region, near=(end.x(), end.y()))
            anchor = QPointF(ax, ay)
            growth = min(1.0, (now - module.born) / 0.5)
            path = QtGui.QPainterPath(anchor)
            bend = (end.x() - anchor.x()) * 0.5
            path.cubicTo(anchor + QPointF(bend, 0), end - QPointF(bend, 0), end)
            pen = QtGui.QPen(theme.with_alpha(theme.GOLD, 0.45 * alpha), 1.0)
            if growth < 1:
                pen.setDashPattern([growth * path.length() / 1.1, 1e6])
            p.setPen(pen)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawPath(path)
            p.setCompositionMode(PLUS)
            spark = path.pointAtPercent(((now * 0.6) % 1.0) * growth)
            self._sprite(p, "glow", "gold", spark.x(), spark.y(), 5, 0.8 * alpha)
            self._sprite(p, "glow", "gold", anchor.x(), anchor.y(), 9, 0.7 * alpha)
            p.setCompositionMode(OVER)
            p.setOpacity(alpha * min(1.0, growth * 1.5))
            p.drawPixmap(rect.topLeft(), self._panel_pixmap(module, rect))
            if module.key == "authorization":
                self._draw_countdown(p, module, rect)
            p.setOpacity(1.0)

    def _panel_pixmap(self, module, rect: QRectF) -> QtGui.QPixmap:
        """Painel pré-renderizado: refeito só quando o conteúdo muda (texto não é refeito por quadro)."""
        key = (module.title, repr(module.lines), int(rect.width()), int(rect.height()), round(self._dpr, 2))
        cached = self._panels.get(module.key)
        if cached is not None and cached[0] == key:
            return cached[1]
        pix = QtGui.QPixmap(max(1, int(rect.width() * self._dpr)) + 1, max(1, int(rect.height() * self._dpr)) + 1)
        pix.setDevicePixelRatio(self._dpr)
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self._draw_panel(painter, module, QRectF(0, 0, rect.width(), rect.height()))
        painter.end()
        if len(self._panels) > 12:
            self._panels.clear()
        self._panels[module.key] = (key, pix)
        return pix

    def _draw_panel(self, p: QtGui.QPainter, module, rect: QRectF) -> None:
        p.fillRect(rect, QtGui.QColor(10, 9, 8, 205))
        pen = QtGui.QPen(theme.with_alpha(theme.GOLD, 0.75), 1.2)
        p.setPen(pen)
        c = 10
        for (x, y, dx, dy) in ((rect.left(), rect.top(), 1, 1), (rect.right(), rect.top(), -1, 1),
                               (rect.left(), rect.bottom(), 1, -1), (rect.right(), rect.bottom(), -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + c * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + c * dy))
        p.setFont(theme.font(8.5, weight=600, spacing=2.2))
        p.setPen(theme.GOLD)
        p.drawText(QRectF(rect.left() + 12, rect.top() + 8, rect.width() - 24, 18), QtCore.Qt.AlignLeft,
                   module.title)
        y = rect.top() + 32
        for line in module.lines:
            y = self._draw_line(p, line, rect, y)

    def _draw_countdown(self, p: QtGui.QPainter, module, rect: QRectF) -> None:
        expires, created = float(module.data.get("expires", 0)), float(module.data.get("created", 0))
        if expires <= created:
            return
        left = max(0.0, min(1.0, (expires - time.time()) / (expires - created)))
        bar = QRectF(rect.left() + 12, rect.top() + 26, (rect.width() - 24) * left, 2)
        p.fillRect(bar, theme.with_alpha(theme.AMBER, 0.8))

    def _draw_line(self, p: QtGui.QPainter, line, rect: QRectF, y: float) -> float:
        x, width = rect.left() + 12, rect.width() - 24
        if isinstance(line, tuple) and line[0] == "chain":
            stages, current = line[1], line[2]
            index = stages.index(current) if current in stages else -1
            p.setFont(theme.font(7, weight=600, spacing=1.0))
            cursor = x
            for i, stage in enumerate(stages):
                tone = theme.WARM_WHITE if i == index else theme.GOLD if i < index else theme.TEXT_DIM
                p.setPen(theme.with_alpha(tone, 1.0 if i <= index else 0.55))
                label = stage.replace("WORLD MODEL", "WORLD").replace("VISUALIZATION", "VISUAL")
                p.drawText(QPointF(cursor, y + 12), label)
                cursor += QtGui.QFontMetricsF(p.font()).horizontalAdvance(label) + 9
                if cursor > x + width - 20:
                    break
            return y + 22
        if isinstance(line, tuple) and line[0] == "option":
            option, recommended = line[1], line[2]
            p.setFont(theme.font(9, weight=700 if recommended else 500))
            p.setPen(theme.WARM_WHITE if recommended else theme.TEXT)
            title = f"{option.get('id', '?')}  {str(option.get('title', ''))[:34]}" + ("  ◆" if recommended else "")
            p.drawText(QPointF(x, y + 12), title)
            bx = x
            p.setFont(theme.font(6.5, spacing=0.5))
            for key, label in (("cost", "CUSTO"), ("time", "TEMPO"), ("quality", "QUALID."), ("complexity", "COMPL."),
                               ("risk", "RISCO")):
                value = max(0, min(5, int(option.get(key, 0) or 0)))
                p.setPen(theme.TEXT_DIM)
                p.drawText(QPointF(bx, y + 31), label)
                for k in range(5):
                    tone = theme.GOLD if k < value else theme.GRAPHITE_LIGHT
                    p.fillRect(QRectF(bx + k * 6.5, y + 34, 5, 3), tone)
                bx += width / 5
            return y + 40
        if isinstance(line, tuple) and line[0] == "image":
            pix = self._image(line[1])
            if pix is not None:
                target = QRectF(x, y, min(width, 150), 88)
                p.drawPixmap(target, pix, QRectF(pix.rect()))
            return y + 96
        if isinstance(line, tuple) and len(line) == 3:
            glyph, text, status = line
            p.setFont(theme.font(9.5))
            p.setPen(theme.color(STATUS_TONE.get(status, "dim"), 1.0))
            p.drawText(QPointF(x, y + 12), glyph)
            p.setPen(theme.TEXT if status != "pending" else theme.TEXT_DIM)
            p.drawText(QPointF(x + 16, y + 12), QtGui.QFontMetricsF(p.font()).elidedText(
                str(text), QtCore.Qt.ElideRight, width - 16))
            return y + 19
        p.setFont(theme.font(9.5))
        p.setPen(theme.TEXT)
        p.drawText(QPointF(x, y + 12), QtGui.QFontMetricsF(p.font()).elidedText(str(line), QtCore.Qt.ElideRight,
                                                                                width))
        return y + 19

    def _image(self, path: str) -> QtGui.QPixmap | None:
        if path not in self._images:
            pix = QtGui.QPixmap(path)
            self._images[path] = None if pix.isNull() else pix.scaled(300, 176, QtCore.Qt.KeepAspectRatio,
                                                                      QtCore.Qt.SmoothTransformation)
        return self._images[path]

    # ---------------------------------------------------------------- textos
    def _draw_overlay_text(self, p: QtGui.QPainter, fr: Frame) -> None:
        scene = self.scene
        w, h = self.width(), self.height()
        now = scene.clock()
        # identidade (canto superior esquerdo)
        p.setFont(theme.font(13, weight=600, spacing=6))
        p.setPen(theme.with_alpha(theme.WARM_WHITE, 0.92 * max(self._core_reveal(), 0.15)))
        p.drawText(QPointF(26, 38), "ULTRON")
        p.setFont(theme.font(7, weight=500, spacing=3))
        p.setPen(theme.with_alpha(theme.GOLD, 0.8))
        p.drawText(QPointF(27, 55), "NEURAL HUB")
        # profundidade cognitiva (canto superior direito)
        label = f"DEPTH {scene.depth_level}"
        fm = QtGui.QFontMetricsF(p.font())
        p.drawText(QPointF(w - 26 - fm.horizontalAdvance(label), 38), label)
        bar_w = 70
        for i in range(10):
            on = i <= scene.depth_level and scene.depth_level > 0
            p.fillRect(QRectF(w - 26 - bar_w + i * 7.2, 46, 5, 2),
                       theme.with_alpha(theme.GOLD if on else theme.GRAPHITE_LIGHT, 0.9 if on else 1))
        # título central (fase cognitiva / fase da inicialização / sonho)
        headline = scene.headline()
        if headline:
            p.setFont(theme.font(10, weight=600, spacing=7))
            fm = QtGui.QFontMetricsF(p.font())
            text = headline
            failed = scene.boot.active and scene.boot.phase_failed(scene.boot.phase)
            if scene.boot.active:
                text = f"{scene.boot.phase + 1:02d} · {headline}" + (" · OFFLINE" if failed else "")
            alert = scene.runtime_state == "AWAITING_AUTHORIZATION" and not scene.boot.active
            pulse = 0.75 + 0.25 * math.sin(now * 2.4)
            p.setPen(theme.with_alpha(theme.AMBER if alert or failed else theme.GOLD, pulse))
            p.drawText(QPointF((w - fm.horizontalAdvance(text)) / 2, 44), text)
        if scene.boot.active:
            online = _clamp(scene.boot.shown - 10.0)
            if online > 0:
                y = min(h - self.bottom_reserved - 24, fr.rcy + RING_BOTTOM * fr.rry + 64)
                self._centered(p, "ULTRON ONLINE", theme.font(20, weight=300, spacing=14),
                               theme.with_alpha(theme.WARM_WHITE, online * 0.9), w / 2, y)
            self._draw_boot_track(p, w, h)
        self._draw_telemetry(p, w, h)
        self._draw_transcript(p, w, h, now)

    def _draw_boot_track(self, p: QtGui.QPainter, w: int, h: int) -> None:
        boot = self.scene.boot
        total = len(BOOT_PHASES)
        span = min(520, w * 0.5)
        x0 = (w - span) / 2
        y = h - 96
        for i in range(total):
            x = x0 + span * i / (total - 1)
            done = boot.shown >= i
            tone = theme.AMBER if boot.phase_failed(i) else theme.GOLD
            p.setBrush(theme.with_alpha(tone, 0.9 if done else 0.15))
            p.setPen(QtCore.Qt.NoPen)
            p.drawEllipse(QPointF(x, y), 2.4 if done else 1.6, 2.4 if done else 1.6)

    def _draw_telemetry(self, p: QtGui.QPainter, w: int, h: int) -> None:
        scene = self.scene
        checks = (scene.state.get("health") or {}).get("checks") or {}
        parts = []
        for key in ("CPU", "RAM", "GPU"):
            check = checks.get(key) or {}
            value = check.get("value")
            parts.append(f"{key} {value:.0f}%" if isinstance(value, (int, float)) else f"{key} —")
        model = scene.state.get("active_model") or "SEM MODELO"
        parts.append(str(model).upper())
        mic = scene.telemetry.get("mic_state") or ""
        if mic:
            parts.append(mic)
        p.setFont(theme.font(7, weight=500, spacing=1.6))
        p.setPen(theme.with_alpha(theme.TEXT_DIM, 0.85))
        p.drawText(QPointF(26, h - 18), "   ".join(parts))
        overall = (scene.state.get("health") or {}).get("overall", "")
        tone = {"OK": theme.GOLD, "WARN": theme.AMBER, "FAIL": theme.AMBER}.get(overall, theme.GRAPHITE_LIGHT)
        p.setBrush(tone)
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(QPointF(18, h - 21), 2.5, 2.5)
        graph = f"{scene.total_nodes} NÓS · {scene.total_edges} SINAPSES"
        fm = QtGui.QFontMetricsF(p.font())
        p.setPen(theme.with_alpha(theme.TEXT_DIM, 0.85))
        p.drawText(QPointF(w - 26 - fm.horizontalAdvance(graph), h - 18), graph)

    def _draw_transcript(self, p: QtGui.QPainter, w: int, h: int, now: float) -> None:
        lines = list(self.scene.transcript)[-2:]
        if not lines:
            return
        max_w = min(w * 0.68, 900)
        y = h - self.bottom_reserved - 14
        for entry in reversed(lines):
            age = now - entry["at"]
            fade = max(0.0, min(1.0, 1.0 - (age - 40) / 6.0))
            if fade <= 0:
                continue
            user = entry["role"] == "user"
            p.setFont(theme.font(10 if user else 12, weight=400 if user else 500))
            fm = QtGui.QFontMetricsF(p.font())
            text = ("›  " if user else "") + entry["text"]
            if not user:
                text = text[: int(max(0.0, age) * 70) + 1]          # revelação no ritmo da leitura
            rect = fm.boundingRect(QRectF(0, 0, max_w, 400), QtCore.Qt.TextWordWrap, text)
            height = min(rect.height(), fm.lineSpacing() * (2 if user else 4))
            y -= height + 6
            box = QRectF((w - max_w) / 2, y, max_w, height + 2)
            p.setPen(theme.with_alpha(theme.TEXT_DIM if user else theme.WARM_WHITE, fade * (0.8 if user else 0.95)))
            p.drawText(box, QtCore.Qt.AlignHCenter | QtCore.Qt.TextWordWrap, text)


def mini_brain(p: QtGui.QPainter, scene: NeuralScene, cx: float, cy: float, scale: float, alpha: float = 1.0) -> None:
    """Cérebro em miniatura (orbe compacto): a mesma malha, no mesmo giro da câmera."""
    mesh = scene.mesh
    indices = mesh.visible_indices(0.0)
    sx, sy, Z, _f = mesh.project(mesh.points, scene.camera.angle, cx, cy, scale)
    depth = np.clip((Z + 1.05) / 2.1, 0.0, 1.0)
    edges = mesh.edges(indices)
    a, b = edges[:, 0], edges[:, 1]
    front = (depth[a] + depth[b]) > 1.0
    for sel, a_level in ((~front, 0.10), (front, 0.26)):
        if sel.any():
            p.setPen(_pen(theme.GOLD, a_level * alpha))
            p.drawLines(_lines(sx[a[sel]], sy[a[sel]], sx[b[sel]], sy[b[sel]]))
    near = depth[indices] > 0.5
    for sel, width, a_level in ((~near, 1.2, 0.4), (near, 1.8, 0.95)):
        chosen = indices[sel]
        if len(chosen):
            p.setPen(_pen(_mix(theme.GOLD, theme.WARM_WHITE, 0.3), a_level * alpha, width, round_cap=True))
            p.drawPoints(_polygon(sx[chosen], sy[chosen]))


__all__ = ["BrainView", "Frame", "mini_brain"]
