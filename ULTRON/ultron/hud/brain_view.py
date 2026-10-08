"""BRAIN VIEW — desenha a ``NeuralScene`` (QPainter).

Camadas (de trás para a frente): fundo → auréola → textura do córtex → fissuras e borda →
estruturas internas (reveladas pela profundidade) → atividade das regiões → sinapses →
nós → partículas → pulsos → módulos neurais e filamentos → títulos, telemetria mínima e
transcrição → vinheta.

Desempenho: a textura do córtex é calculada fora da thread da interface e guardada como
``QPixmap``; brilhos são sprites pré-renderizados com composição aditiva; o caminho de
todas as sinapses é reconstruído só quando o grafo muda.
"""
from __future__ import annotations

import math
import threading
import time
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from . import theme
from .brain_model import REGIONS
from .cortex import X0, X1, Y0, Y1, CortexRenderer
from .scene import BOOT_PHASES, NeuralScene

QPointF, QRectF = QtCore.QPointF, QtCore.QRectF
PLUS = QtGui.QPainter.CompositionMode_Plus
OVER = QtGui.QPainter.CompositionMode_SourceOver

STATUS_TONE = {"done": "gold", "running": "white", "unconfirmed": "amber", "failed": "amber", "skipped": "dim",
               "cancelled": "amber", "pending": "dim"}


def _path(points, closed: bool = False) -> QtGui.QPainterPath:
    path = QtGui.QPainterPath()
    pts = list(points)
    if not pts:
        return path
    path.moveTo(float(pts[0][0]), float(pts[0][1]))
    for x, y in pts[1:]:
        path.lineTo(float(x), float(y))
    if closed:
        path.closeSubpath()
    return path


class _TextureSignal(QtCore.QObject):
    ready = QtCore.Signal(float, object)


class BrainView(QtWidgets.QWidget):
    def __init__(self, scene: NeuralScene, *, cache_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self.setMinimumSize(480, 320)
        self.renderer = CortexRenderer(scene.geometry, cache_path=(cache_dir / "hud_cortex.npz") if cache_dir else None)
        self._texture: QtGui.QPixmap | None = None
        self._texture_dev = -1.0
        self._texture_busy = False
        self._texture_signal = _TextureSignal()
        self._texture_signal.ready.connect(self._on_texture)
        g = scene.geometry
        self._outline = _path(g.cerebrum, True)
        self._outline.addPath(_path(g.cerebellum, True))
        self._outline_length = max(1.0, self._outline.length())
        self._fissures = {name: _path(pts) for name, pts in g.fissures.items()}
        self._inner = {name: _path(pts, name == "thalamus") for name, pts in g.inner.items()}
        self._edges_path = QtGui.QPainterPath()
        self._edges_version = -1
        self._background: QtGui.QPixmap | None = None
        self._vignette: QtGui.QPixmap | None = None
        self._base: QtGui.QPixmap | None = None
        self._base_key: tuple | None = None
        self.base_renders = 0
        self._structure: QtGui.QPixmap | None = None        # sinapses, nós em repouso, contorno e fissuras
        self._structure_key: tuple | None = None
        self.structure_renders = 0
        self._images: dict[str, QtGui.QPixmap | None] = {}
        self.fps = 0.0
        self._frame_times: list[float] = []
        self._dpr = 1.0
        self.bottom_reserved = 70                  # pixels ocupados por controles sobrepostos (entrada, decisões)
        self._request_texture()

    # ================================================================ textura do córtex
    def _request_texture(self) -> None:
        dev = round(self.scene.development * 10) / 10
        if self._texture_busy or abs(dev - self._texture_dev) < 0.05:
            return
        self._texture_busy = True

        def work() -> None:
            try:
                rgba = self.renderer.texture(dev)
            except Exception:
                rgba = None
            self._texture_signal.ready.emit(dev, rgba)

        threading.Thread(target=work, name="ultron-cortex", daemon=True).start()

    @QtCore.Slot(float, object)
    def _on_texture(self, dev: float, rgba) -> None:
        self._texture_busy = False
        if rgba is None:
            return
        h, w = rgba.shape[:2]
        image = QtGui.QImage(np.ascontiguousarray(rgba).data, w, h, 4 * w, QtGui.QImage.Format_RGBA8888).copy()
        self._texture = QtGui.QPixmap.fromImage(image)
        self._texture_dev = dev
        self.update()

    # ================================================================ geometria de tela
    def brain_transform(self) -> QtGui.QTransform:
        cam = self.scene.camera
        w, h = self.width(), self.height()
        base = min(w / 2.45, (h - 120) / 1.75)
        t = QtGui.QTransform()
        t.translate(w / 2 + cam.shift * w, h / 2 - 0.02 * h)
        t.scale(base * cam.zoom, base * cam.zoom)
        t.translate(-cam.x, -cam.y)
        return t

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._background = None
        self._vignette = None
        self._base_key = None
        super().resizeEvent(event)

    def _ensure_backgrounds(self) -> None:
        w, h = max(1, self.width()), max(1, self.height())
        if self._background is None:
            pix = QtGui.QPixmap(w, h)
            p = QtGui.QPainter(pix)
            grad = QtGui.QRadialGradient(w * 0.5, h * 0.46, max(w, h) * 0.75)
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
            pix = QtGui.QPixmap(w, h)
            pix.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pix)
            grad = QtGui.QRadialGradient(w * 0.5, h * 0.48, max(w, h) * 0.68)
            grad.setColorAt(0.55, QtGui.QColor(0, 0, 0, 0))
            grad.setColorAt(1.0, QtGui.QColor(0, 0, 0, 255))
            p.fillRect(0, 0, w, h, grad)
            p.end()
            self._vignette = pix

    def _rebuild_edges(self) -> None:
        if self._edges_version == self.scene.graph_version:
            return
        path = QtGui.QPainterPath()
        nodes = self.scene.nodes
        for edge in self.scene.edges.values():
            a, b = nodes.get(edge.a), nodes.get(edge.b)
            if a is None or b is None:
                continue
            path.moveTo(a.x, a.y)
            path.quadTo(edge.cx, edge.cy, b.x, b.y)
        self._edges_path = path
        self._edges_version = self.scene.graph_version

    # ================================================================ pintura
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        started = time.perf_counter()
        scene = self.scene
        if abs(round(scene.development * 10) / 10 - self._texture_dev) >= 0.05:
            self._request_texture()
        self._dpr = self.devicePixelRatioF()
        self._ensure_backgrounds()
        self._rebuild_edges()
        reveal = self._reveal()
        transform = self.brain_transform()
        self._ensure_base(transform, reveal)
        p = QtGui.QPainter(self)
        p.drawPixmap(0, 0, self._base)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        p.setTransform(transform)
        self._draw_dynamic(p, reveal, transform)
        p.resetTransform()
        if scene.suspense > 0.03 or scene.dim > 0.01:
            p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, int(min(200, 70 * scene.suspense + 140 * scene.dim))))
        self._draw_modules(p, transform)
        self._draw_overlay_text(p, reveal)
        p.end()
        self._frame_times.append(time.perf_counter() - started)
        if len(self._frame_times) >= 30:
            self.fps = 1.0 / max(1e-6, sum(self._frame_times) / len(self._frame_times))
            self._frame_times.clear()

    def _halo_level(self, reveal: dict[str, float]) -> float:
        scene = self.scene
        activity = sum(scene.region_activity.values()) / max(1, len(scene.region_activity))
        level = (0.06 + 0.03 * math.sin(2 * math.pi * scene.breath) + 0.25 * activity
                 + 0.35 * scene.release) * reveal["core"]
        return round(level / 0.015) * 0.015                     # quantizado: o cache vale vários quadros

    def _ensure_base(self, transform: QtGui.QTransform, reveal: dict[str, float]) -> None:
        scene = self.scene
        cam = scene.camera
        inner = max(0.0, min(1.0, (scene.depth - 3.5) / 5.0))
        key = (self.width(), self.height(), round(cam.x, 4), round(cam.y, 4), round(cam.zoom, 4),
               round(cam.shift, 4), id(self._texture), self._edges_version, scene.graph_version,
               tuple(round(v, 2) for v in reveal.values()), round(inner, 2), self._halo_level(reveal),
               round(scene.dim, 2))
        if key == self._base_key and self._base is not None:
            return
        dpr = self.devicePixelRatioF()
        pix = QtGui.QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pix.setDevicePixelRatio(dpr)
        p = QtGui.QPainter(pix)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        p.drawPixmap(0, 0, self._background)
        p.setTransform(transform)
        self._draw_base_brain(p, reveal, inner, transform)
        p.resetTransform()
        p.drawPixmap(0, 0, self._vignette)
        p.end()
        self._base, self._base_key = pix, key
        self.base_renders += 1

    def _reveal(self) -> dict[str, float]:
        boot = self.scene.boot
        if not boot.active:
            return dict.fromkeys(("core", "nodes", "outline", "frontal", "edges", "motor", "imagination", "voice",
                                  "texture", "online"), 1.0)
        bp = boot.shown

        def vis(i: int) -> float:
            return max(0.0, min(1.0, bp - (i - 1)))

        return {"core": vis(1), "nodes": vis(3), "outline": vis(4), "frontal": vis(5), "edges": vis(6),
                "motor": vis(7), "imagination": vis(8), "voice": vis(9), "texture": vis(10), "online": vis(11)}

    # ---------------------------------------------------------------- cérebro
    def _sprite(self, p: QtGui.QPainter, kind: str, tone: str, x: float, y: float, r: float, opacity: float,
                transform: QtGui.QTransform | None = None, *, bounds: tuple[int, int] | None = None) -> None:
        """Brilho em espaço de dispositivo: ``x, y, r`` no espaço do cérebro quando há ``transform``."""
        if opacity <= 0.004 or r <= 0:
            return
        if transform is not None:
            x, y = transform.m11() * x + transform.m31(), transform.m22() * y + transform.m32()
            r = r * transform.m11()
        radius = theme.quantize_radius(r)
        w, h = bounds or (self.width(), self.height())
        if x + radius < 0 or y + radius < 0 or x - radius > w or y - radius > h:
            return
        pix = theme.sprite_px(kind, tone, radius, self._dpr)
        p.setOpacity(min(1.0, opacity))
        p.drawPixmap(QPointF(x - radius, y - radius), pix)

    STRUCTURE_SCALE = 720.0                                       # pixels por unidade do cérebro na camada em cache

    def _ensure_structure(self, rv: dict[str, float], inner: float) -> QtGui.QPixmap:
        """Camada em espaço do cérebro (independente da câmera): refeita só quando o grafo, a
        fase de inicialização ou a profundidade mudam — durante movimentos de câmera ela é só
        reescalada."""
        key = (self.scene.graph_version, self._edges_version, round(inner, 2), round(self._dpr, 2),
               tuple(round(rv[k], 2) for k in ("nodes", "edges", "outline", "voice", "motor", "texture")))
        if key == self._structure_key and self._structure is not None:
            return self._structure
        k = self.STRUCTURE_SCALE
        w, h = int((X1 - X0) * k), int((Y1 - Y0) * k)
        pix = QtGui.QPixmap(w, h)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        layer = QtGui.QTransform()
        layer.scale(k, k)
        layer.translate(-X0, -Y0)
        if rv["edges"] > 0 and not self._edges_path.isEmpty():
            pen = QtGui.QPen(theme.with_alpha(theme.GOLD, (0.10 + 0.08 * inner) * rv["edges"]), 1.0)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawPath(layer.map(self._edges_path))
        if rv["outline"] > 0:
            pen = QtGui.QPen(theme.with_alpha(theme.GOLD, 0.34 + 0.30 * (1 - rv["texture"])), 1.4)
            p.setPen(pen)
            p.setBrush(QtCore.Qt.NoBrush)
            if rv["outline"] < 1.0:                              # contorno sendo traçado (inicialização)
                part = QtGui.QPainterPath()
                steps = max(2, int(160 * rv["outline"]))
                part.moveTo(self._outline.pointAtPercent(0.0))
                for i in range(1, steps + 1):
                    part.lineTo(self._outline.pointAtPercent(min(1.0, rv["outline"] * i / steps)))
                p.drawPath(layer.map(part))
            else:
                p.drawPath(layer.map(self._outline))
        for name, path in self._fissures.items():
            vis = rv["voice"] if name == "lateral" else rv["motor"]
            if vis <= 0:
                continue
            mapped = layer.map(path)
            p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, int(170 * vis)), 4.4))
            p.drawPath(mapped)
            p.setPen(QtGui.QPen(theme.with_alpha(theme.GOLD, 0.45 * vis), 1.4))
            p.drawPath(mapped)
        if inner > 0.02:
            p.setPen(QtGui.QPen(theme.with_alpha(theme.WARM_WHITE, 0.35 * inner), 1.6, QtCore.Qt.DashLine))
            for path in self._inner.values():
                p.drawPath(layer.map(path))
        if rv["nodes"] > 0:                                      # nós em repouso
            p.setCompositionMode(PLUS)
            saved_dpr, self._dpr = self._dpr, 1.0
            for node in self.scene.nodes.values():
                radius, opacity = self._node_look(node)
                self._sprite(p, "glow", self._node_tone(node), node.x, node.y, radius * 2.2,
                             rv["nodes"] * opacity, layer, bounds=(w, h))
            self._dpr = saved_dpr
        p.end()
        self._structure, self._structure_key = pix, key
        self.structure_renders += 1
        return pix

    def _draw_base_brain(self, p: QtGui.QPainter, rv: dict[str, float], inner: float,
                         transform: QtGui.QTransform) -> None:
        """Tudo o que só muda com câmera, grafo, profundidade ou fase de inicialização."""
        scene = self.scene
        p.save()
        p.resetTransform()
        p.setCompositionMode(PLUS)
        self._sprite(p, "soft", "gold", 0.05, -0.08, 1.35, self._halo_level(rv), transform)
        p.restore()
        moving = self._camera_moving()
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, not moving)
        target = QRectF(X0, Y0, X1 - X0, Y1 - Y0)
        if self._texture is not None and rv["texture"] > 0:
            p.setOpacity(rv["texture"] * (1.0 - 0.55 * inner) * (1.0 - 0.35 * scene.dim))
            p.drawPixmap(target, self._texture, QRectF(0, 0, self._texture.width(), self._texture.height()))
        structure = self._ensure_structure(rv, inner)
        p.setOpacity(1.0)
        p.setCompositionMode(PLUS)
        p.drawPixmap(target, structure, QRectF(0, 0, structure.width(), structure.height()))
        p.setCompositionMode(OVER)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)

    def _camera_moving(self) -> bool:
        cam = self.scene.camera
        return (abs(cam.zoom - cam.tzoom) > 0.002 or abs(cam.x - cam.tx) > 0.002 or abs(cam.y - cam.ty) > 0.002
                or abs(cam.shift - cam.tshift) > 0.002)

    @staticmethod
    def _node_tone(node) -> str:
        if node.type in ("IDEA", "CONCEPT", "WORLD", "SCENARIO"):
            return "white"
        return "amber" if node.type in ("MEMORY", "DEVICE") else "gold"

    @staticmethod
    def _node_look(node) -> tuple[float, float]:
        radius = 0.008 + 0.010 * node.strength
        opacity = 0.24 + 0.48 * node.strength
        return radius, opacity

    def _draw_dynamic(self, p: QtGui.QPainter, rv: dict[str, float], transform: QtGui.QTransform) -> None:
        """Só o que está ativo agora: regiões, núcleo, sinapses e nós ativados, sinais e pulsos."""
        scene = self.scene
        now = scene.clock()
        heartbeat = 0.5 + 0.5 * math.sin(now * 2 * math.pi * 0.8) if scene.suspense > 0.2 else 0.0
        p.save()
        p.resetTransform()                                       # espaço de dispositivo, sem escala
        if rv["edges"] > 0:
            # sinapses ativadas: agrupadas por intensidade → poucas chamadas de traçado por quadro
            m11, m22, m31, m32 = transform.m11(), transform.m22(), transform.m31(), transform.m32()
            buckets: dict[int, QtGui.QPainterPath] = {}
            for edge in scene.edges.values():
                if edge.activation < 0.03:
                    continue
                a, b = scene.nodes.get(edge.a), scene.nodes.get(edge.b)
                if a is None or b is None:
                    continue
                level = min(5, int(edge.activation * 6))
                path = buckets.setdefault(level, QtGui.QPainterPath())
                path.moveTo(m11 * a.x + m31, m22 * a.y + m32)
                path.quadTo(m11 * edge.cx + m31, m22 * edge.cy + m32, m11 * b.x + m31, m22 * b.y + m32)
            p.setBrush(QtCore.Qt.NoBrush)
            for level, path in buckets.items():
                pen = QtGui.QPen(theme.with_alpha(theme.GOLD, 0.75 * (level + 0.5) / 6), 1.0)
                pen.setCosmetic(True)                          # ≤ 1 px: caminho rápido de linhas do QPainter
                p.setPen(pen)
                p.drawPath(path)
        p.setCompositionMode(PLUS)
        boot_regions = {"frontal": rv["frontal"], "prefrontal": rv["imagination"], "motor": rv["motor"],
                        "auditory": rv["voice"], "broca": rv["voice"], "occipital": rv["texture"]}
        for name, level in scene.region_activity.items():
            x, y, r = REGIONS[name]
            boot_glow = 0.0
            if scene.boot.active and name in boot_regions:
                v = boot_regions[name]
                boot_glow = 1.4 * v * (1 - v)                     # acende ao surgir e assenta
            amount = level + boot_glow
            if amount > 0.01:
                tone = "white" if name in ("auditory", "broca") and level > 0.5 else "gold"
                self._sprite(p, "soft", tone, x, y, r * 1.9, min(1.0, amount * 0.9), transform)
        core = REGIONS["core"]
        booting = 1.0 if scene.boot.active else 0.0
        core_glow = rv["core"] * (0.30 + 0.45 * (1 - rv["online"]) * booting + 0.4 * heartbeat * scene.suspense
                                  + 0.3 * scene.release)
        self._sprite(p, "glow", "white", core[0], core[1], 0.05 + 0.04 * scene.release, core_glow, transform)
        if rv["nodes"] > 0:
            for node in scene.nodes.values():
                birth = now - node.born
                if node.activation < 0.02 and birth > 1.0:
                    continue
                radius, _opacity = self._node_look(node)
                grow = min(1.0, max(0.0, birth / 0.8))
                extra = 0.85 * node.activation + (1.0 - grow) * 0.8
                self._sprite(p, "glow", self._node_tone(node), node.x, node.y,
                             radius * 2.2 * (1 + 0.9 * node.activation), rv["nodes"] * extra, transform)
        for particle in scene.particles:
            if particle.t < 0:
                continue
            x, y = particle.position()
            fade = math.sin(math.pi * min(1.0, particle.t))
            self._sprite(p, "glow", particle.tone, x, y, 0.016 * particle.size, 0.9 * fade, transform)
        p.restore()
        p.setCompositionMode(OVER)
        p.setBrush(QtCore.Qt.NoBrush)
        for pulse in scene.pulses:
            t = (now - pulse.born) / pulse.duration
            if t < 0 or t > 1:
                continue
            ease = 1 - (1 - t) ** 3
            pen = QtGui.QPen(theme.color(pulse.tone, 0.6 * pulse.strength * (1 - t) ** 1.5), 1.0)
            pen.setCosmetic(True)
            p.setPen(pen)
            r = pulse.radius * ease
            p.drawEllipse(QPointF(pulse.x, pulse.y), r * 1.2, r * 0.9)
        p.setOpacity(1.0)

    # ---------------------------------------------------------------- módulos neurais
    def _module_layout(self, transform: QtGui.QTransform) -> list[tuple]:
        modules = self.scene.visible_modules()
        w, h = self.width(), self.height()
        width = min(360, max(250, int(w * 0.26)))
        columns = {"left": 84, "right": 84}
        out = []
        for module in modules:
            side = self.scene.module_side(module)
            lines = module.lines
            height = 34 + sum(self._line_height(line) for line in lines) + 10
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

    def _draw_modules(self, p: QtGui.QPainter, transform: QtGui.QTransform) -> None:
        now = self.scene.clock()
        for module, rect, side in self._module_layout(transform):
            alpha = module.alpha
            if alpha < 0.02:
                continue
            rx, ry, _ = REGIONS.get(module.region, REGIONS["core"])
            anchor = transform.map(QPointF(rx, ry))
            end = QPointF(rect.right() if side == "left" else rect.left(), rect.top() + 18)
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
            self._draw_panel(p, module, rect)
            p.setOpacity(1.0)

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
        if module.key == "authorization":
            self._draw_countdown(p, module, rect)
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
    def _draw_overlay_text(self, p: QtGui.QPainter, rv: dict[str, float]) -> None:
        scene = self.scene
        w, h = self.width(), self.height()
        now = scene.clock()
        # identidade (canto superior esquerdo)
        p.setFont(theme.font(13, weight=600, spacing=6))
        p.setPen(theme.with_alpha(theme.WARM_WHITE, 0.92 * max(rv["core"], 0.15)))
        p.drawText(QPointF(26, 38), "ULTRON")
        p.setFont(theme.font(7, weight=500, spacing=3))
        p.setPen(theme.with_alpha(theme.GOLD, 0.8))
        p.drawText(QPointF(27, 55), "NEURAL HUB")
        state = "BOOT" if scene.boot.active else scene.runtime_state.replace("_", " ")
        p.setPen(theme.with_alpha(theme.TEXT_DIM, 0.9))
        p.drawText(QPointF(27, 72), state)
        # profundidade cognitiva (canto superior direito)
        p.setFont(theme.font(7, weight=500, spacing=3))
        p.setPen(theme.with_alpha(theme.GOLD, 0.8))
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
            if scene.boot.active:
                failed = scene.boot.phase_failed(scene.boot.phase)
                text = f"{scene.boot.phase + 1:02d} · {headline}" + (" · OFFLINE" if failed else "")
            alert = scene.runtime_state == "AWAITING_AUTHORIZATION" and not scene.boot.active
            tone = theme.AMBER if alert or (scene.boot.active and scene.boot.phase_failed(scene.boot.phase)) \
                else theme.GOLD
            pulse = 0.75 + 0.25 * math.sin(now * 2.4)
            p.setPen(theme.with_alpha(tone, pulse))
            p.drawText(QPointF((w - fm.horizontalAdvance(text)) / 2, 44), text)
        if scene.boot.active and rv["online"] > 0:
            p.setFont(theme.font(22, weight=300, spacing=14))
            fm = QtGui.QFontMetricsF(p.font())
            p.setPen(theme.with_alpha(theme.WARM_WHITE, rv["online"] * 0.9))
            p.drawText(QPointF((w - fm.horizontalAdvance("ULTRON ONLINE")) / 2, h * 0.86), "ULTRON ONLINE")
        if scene.boot.active:
            self._draw_boot_track(p, w, h)
        # telemetria mínima (rodapé)
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
