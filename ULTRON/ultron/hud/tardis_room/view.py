"""Desenho da sala de controle da TARDIS em QPainter (CPU), no estilo holográfico do JARVIS.

Inspirada na sala de controle clássica — console hexagonal, rotor de vidro que sobe e desce, paredes com
círculos —, sem reproduzir marcas, textos ou desenhos protegidos: a geometria é própria e as cores são
as da plataforma (âmbar da TARDIS sobre o azul profundo do JARVIS).

Camadas, de trás para a frente: fundo em cache · círculos das paredes · piso (anéis e raios) · colunas
e nervuras do teto · anel de falha · console (painéis atrás do rotor) · rotor · console (painéis à
frente) · telas flutuantes · feixe JARVIS ⇄ TARDIS · rótulos · partículas · linhas de varredura.

Custo: as camadas fixas (fundo, paredes, piso, colunas e pedestal) ficam numa imagem em cache, refeita só
quando a câmera se move (escolher um painel); por quadro, só rotor, painéis, telas, rótulos e partículas.
Linhas são polilinhas de 1 px (caminhos e segmentos soltos custam ~4× mais; canetas largas com
antialiasing, dezenas de vezes mais) e os brilhos são imagens em cache, não gradientes recalculados.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ...tardis.protocol import PANELS
from ..avatar import fastpath
from .scene import AMBER, CYAN, ICE, MODES, PANEL_ANGLES, RED, RoomScene

DEEP = (3, 7, 18)
ABYSS = (7, 20, 38)
NAVY = (11, 31, 58)
ROOM_R = 5.4
CEILING = 3.7
OUT_R, OUT_Y = 1.22, 0.92          # borda externa do console
IN_R, IN_Y = 0.42, 1.14            # borda interna (base do rotor)
PED_R = 0.62                       # pedestal
ROTOR_R, ROTOR_Y0, ROTOR_Y1 = 0.30, IN_Y, 2.95
TARGET = np.array([0.0, 1.50, 0.0])


@dataclass(frozen=True)
class RoomQuality:
    name: str
    ring_samples: int
    motes: int
    glow: bool
    roundel_rows: int
    scanlines: bool


QUALITY = {
    "economy": RoomQuality("economy", 40, 0, False, 2, False),
    "balanced": RoomQuality("balanced", 64, 40, True, 3, True),
    "high": RoomQuality("high", 80, 70, True, 3, True),
    "cinematic": RoomQuality("cinematic", 96, 100, True, 3, True),
}


def quality_for(profile_name: str) -> RoomQuality:
    return QUALITY.get(profile_name, QUALITY["balanced"])


def _color(rgb, alpha: float) -> QtGui.QColor:
    return QtGui.QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(max(0.0, min(1.0, alpha)) * 255))


def _mix(a, b, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _pen(rgb, alpha: float, width: float = 1.0) -> QtGui.QPen:
    pen = QtGui.QPen(_color(rgb, alpha))
    pen.setWidthF(width)
    pen.setCosmetic(True)
    return pen


class Camera:
    """Câmera em órbita olhando para o console. Ângulo ``azimuth`` = direção (cos, sen) no plano do piso."""

    def __init__(self, azimuth: float, width: int, height: int, *, elevation: float = 0.30, distance: float = 4.5):
        self.width, self.height = width, height
        ce = math.cos(elevation)
        self.position = TARGET + distance * np.array([ce * math.cos(azimuth), math.sin(elevation),
                                                      ce * math.sin(azimuth)])
        forward = TARGET - self.position
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, np.array([0.0, 1.0, 0.0]))
        right /= np.linalg.norm(right)
        self.forward, self.right, self.up = forward, right, np.cross(right, forward)
        self.focal = min(width * 0.58, height * 0.98)
        self.cx, self.cy = width * 0.5, height * 0.47

    def project(self, points) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(x, y, z) na tela; pontos atrás da câmera (z ≤ 0,05) viram NaN."""
        pts = np.asarray(points, dtype=np.float64)
        d = pts - self.position
        x = d @ self.right
        y = d @ self.up
        z = d @ self.forward
        with np.errstate(divide="ignore", invalid="ignore"):
            inv = np.where(z > 0.05, 1.0 / z, np.nan)
        return self.cx + self.focal * x * inv, self.cy - self.focal * y * inv, z

    def point(self, p) -> tuple[float, float, float]:
        x, y, z = self.project(np.asarray(p, dtype=np.float64).reshape(1, 3))
        return float(x[0]), float(y[0]), float(z[0])

    def facing(self, point, normal) -> float:
        """Quanto uma superfície está de frente para a câmera (−1..1)."""
        to_camera = self.position - np.asarray(point, dtype=np.float64)
        n = float(np.linalg.norm(to_camera))
        return float(np.dot(np.asarray(normal, dtype=np.float64), to_camera) / n) if n else 0.0


def _circle(center, radius: float, samples: int, *, axis_u=(1.0, 0.0, 0.0), axis_v=(0.0, 0.0, 1.0)) -> np.ndarray:
    t = np.linspace(0.0, math.tau, samples + 1)
    c = np.asarray(center, dtype=np.float64)
    u, v = np.asarray(axis_u, dtype=np.float64), np.asarray(axis_v, dtype=np.float64)
    return c + radius * (np.cos(t)[:, None] * u + np.sin(t)[:, None] * v)


def _wrap(text: str, metrics: QtGui.QFontMetricsF, width: float) -> list[str]:
    """Quebra por palavras na largura da tela flutuante."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and metrics.horizontalAdvance(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _depth_alpha(z: np.ndarray, near: float = 1.5, far: float = 13.0) -> np.ndarray:
    """Neblina: perto = 1, longe = 0,2."""
    return np.clip(1.0 - (z - near) / (far - near), 0.2, 1.0)


def _segment_alpha(sx, sy, z, base: float) -> np.ndarray:
    """Alfa por segmento (linhas × colunas−1); segmentos com ponta inválida = 0."""
    valid = np.isfinite(sx) & np.isfinite(sy)
    ok = valid[:, 1:] & valid[:, :-1]
    zz = np.nan_to_num(0.5 * (z[:, 1:] + z[:, :-1]), nan=99.0)
    return np.where(ok, _depth_alpha(zz) * base, 0.0)


class RoomRenderer:
    def __init__(self):
        self._background: tuple[tuple[int, int], QtGui.QPixmap] | None = None
        self._scan: tuple[tuple[int, int], QtGui.QPixmap] | None = None
        self.panel_polygons: list[tuple[float, str, QtGui.QPolygonF]] = []
        self._fonts: dict[int, QtGui.QFont] = {}
        self._glows: dict[tuple, QtGui.QPixmap] = {}
        self._static: tuple[tuple, QtGui.QPixmap] | None = None
        self._screen_cache: dict[str, tuple[tuple, QtGui.QPixmap]] = {}
        self._console: tuple | None = None
        self.static_renders = 0

    # ------------------------------------------------------------ utilidades
    def font(self, size: int, *, bold: bool = False, spacing: float = 1.5) -> QtGui.QFont:
        key = size * 10 + int(bold)
        font = self._fonts.get(key)
        if font is None:
            font = QtGui.QFont("Bahnschrift")
            if not QtGui.QFontInfo(font).exactMatch():
                font = QtGui.QFont("Segoe UI")
            font.setPixelSize(max(6, size))
            font.setBold(bold)
            font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, spacing)
            self._fonts[key] = font
        return font

    def panel_at(self, x: float, y: float) -> str:
        """Painel do console sob o cursor (o mais próximo da câmera)."""
        point = QtCore.QPointF(x, y)
        for _depth, key, poly in sorted(self.panel_polygons, key=lambda item: item[0]):
            if poly.containsPoint(point, QtCore.Qt.OddEvenFill):
                return key
        return ""

    def _rows(self, painter, rows_xyz: np.ndarray, cam: Camera, rgb, base: float, levels: int = 4) -> None:
        """Linhas (linhas × colunas × 3) com neblina por profundidade: cada linha vira polilinhas contínuas
        de mesmo nível de brilho (uma chamada por trecho; pontos atrás da câmera interrompem o trecho)."""
        rows, cols = rows_xyz.shape[:2]
        sx, sy, z = cam.project(rows_xyz.reshape(-1, 3))
        sx, sy, z = sx.reshape(rows, cols), sy.reshape(rows, cols), z.reshape(rows, cols)
        alpha = _segment_alpha(sx, sy, z, base)
        quant = np.clip((alpha * levels + 0.5).astype(np.int32), 0, levels)
        pens: dict[int, QtGui.QPen] = {}
        for r in range(rows):
            q = quant[r]
            if not q.any():
                continue
            change = np.flatnonzero(np.diff(q)) + 1
            starts = np.concatenate(([0], change))
            ends = np.concatenate((change, [len(q)]))
            for start, end in zip(starts, ends):
                level = int(q[start])
                if level <= 0:
                    continue
                pen = pens.get(level)
                if pen is None:
                    pen = pens[level] = _pen(rgb, level / levels)
                painter.setPen(pen)
                painter.drawPolyline(fastpath.polygon(np.stack([sx[r, start:end + 1], sy[r, start:end + 1]], axis=1)))

    def _ring(self, painter, points: np.ndarray, cam: Camera, rgb, alpha: float, width: float = 1.0) -> None:
        """Um contorno curto (profundidade quase constante): uma polilinha só."""
        sx, sy, _z = cam.project(points)
        valid = np.isfinite(sx) & np.isfinite(sy)
        if valid.sum() < 2:
            return
        painter.setPen(_pen(rgb, alpha, width))
        if valid.all():
            painter.drawPolyline(fastpath.polygon(np.stack([sx, sy], axis=1)))
            return
        idx = np.flatnonzero(valid)
        breaks = np.flatnonzero(np.diff(idx) > 1) + 1
        for chunk in np.split(idx, breaks):
            if len(chunk) >= 2:
                painter.drawPolyline(fastpath.polygon(np.stack([sx[chunk], sy[chunk]], axis=1)))

    def glow(self, radius: float, rgb, alpha: float, *, squash: float = 1.0) -> QtGui.QPixmap:
        """Brilho radial pré-desenhado (raio em degraus de 8 px; cor e alfa em degraus; ``squash`` achata na
        vertical, para o piso) — por quadro, só um blit sem escala."""
        r = max(8, int(round(radius / 8.0)) * 8)
        color = tuple(int(c) // 16 * 16 for c in rgb)
        a = max(0, min(20, int(round(alpha * 20))))
        key = (r, color, a, round(squash, 2))
        pix = self._glows.get(key)
        if pix is None:
            if len(self._glows) > 48:
                self._glows.clear()
            ry = max(4, int(r * squash))
            pix = QtGui.QPixmap(r * 2, ry * 2)
            pix.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pix)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            p.scale(1.0, ry / r)
            grad = QtGui.QRadialGradient(r, r, r)
            grad.setColorAt(0.0, _color(color, a / 20))
            grad.setColorAt(0.45, _color(color, a / 20 * 0.35))
            grad.setColorAt(1.0, _color(color, 0.0))
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(grad)
            p.drawEllipse(0, 0, r * 2, r * 2)
            p.end()
            self._glows[key] = pix
        return pix

    # ------------------------------------------------------------ camadas fixas
    def background(self, w: int, h: int, scan: bool = True) -> QtGui.QPixmap:
        """Fundo (gradientes, halo, vinheta e linhas de varredura): desenhado uma vez por tamanho."""
        if self._background is not None and self._background[0] == (w, h, scan):
            return self._background[1]
        pix = QtGui.QPixmap(w, h)
        p = QtGui.QPainter(pix)
        grad = QtGui.QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, _color(DEEP, 1.0))
        grad.setColorAt(0.55, _color(ABYSS, 1.0))
        grad.setColorAt(1.0, _color((4, 12, 26), 1.0))
        p.fillRect(0, 0, w, h, grad)
        halo = QtGui.QRadialGradient(w * 0.5, h * 0.40, max(w, h) * 0.55)
        halo.setColorAt(0.0, _color(NAVY, 0.85))
        halo.setColorAt(0.6, _color(NAVY, 0.25))
        halo.setColorAt(1.0, _color(NAVY, 0.0))
        p.fillRect(0, 0, w, h, halo)
        vignette = QtGui.QRadialGradient(w * 0.5, h * 0.5, max(w, h) * 0.75)
        vignette.setColorAt(0.65, _color(DEEP, 0.0))
        vignette.setColorAt(1.0, _color(DEEP, 0.85))
        p.fillRect(0, 0, w, h, vignette)
        if scan:
            p.drawPixmap(0, 0, self.scanlines(w, h))
        p.end()
        self._background = ((w, h, scan), pix)
        return pix

    def scanlines(self, w: int, h: int) -> QtGui.QPixmap:
        if self._scan is not None and self._scan[0] == (w, h):
            return self._scan[1]
        pix = QtGui.QPixmap(w, h)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setPen(_pen((0, 0, 0), 0.16))
        for y in range(0, h, 3):
            p.drawLine(0, y, w, y)
        p.end()
        self._scan = ((w, h), pix)
        return pix

    # ------------------------------------------------------------ quadro
    def render(self, painter: QtGui.QPainter, w: int, h: int, scene: RoomScene, *, quality: RoomQuality,
               effects: bool = True) -> None:
        if w < 40 or h < 40:
            painter.drawPixmap(0, 0, self.background(w, h, False))
            return
        cam = Camera(scene.azimuth, w, h)
        panels = self._panel_geometry(cam)
        painter.drawPixmap(0, 0, self.static_layer(cam, w, h, quality, effects and quality.scanlines,
                                                   moving=scene.camera_moving()))
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        style = MODES[scene.mode]
        glow = scene.brightness
        if effects and quality.glow:
            self._floor_glow(painter, cam, scene)
        if scene.fault_glow > 0.02:
            self._fault_ring(painter, cam, scene, quality)
        self._screens(painter, cam, scene)
        origin, console = self.console_layer(cam, panels, scene.selected, scene.hover)
        if console is not None:
            painter.drawPixmap(origin, console)
        rotor_depth = cam.point((0.0, 1.8, 0.0))[2]
        for panel in sorted(panels, key=lambda p: -p["depth"]):
            if panel["depth"] > rotor_depth:
                self._panel_lights(painter, cam, scene, panel)
        self._rotor(painter, cam, scene, quality, effects)
        for panel in sorted(panels, key=lambda p: -p["depth"]):
            if panel["depth"] <= rotor_depth:
                self._panel_lights(painter, cam, scene, panel)
        if scene.beam > 0.02:
            self._beam(painter, cam, scene)
        self._labels(painter, cam, scene, panels)
        if effects and quality.motes and scene.motes:
            self._motes(painter, cam, scene, quality.motes)
        self._hud(painter, w, h, scene, style, glow)

    def static_layer(self, cam: Camera, w: int, h: int, quality: RoomQuality, scan: bool = True, *,
                     moving: bool = False) -> QtGui.QPixmap:
        """Fundo, paredes, piso e colunas — refeitos só quando a câmera ou o tamanho mudam (escolher um painel
        gira a câmera; parada, a sala custa um blit). Durante a volta da câmera, menos detalhe (sem os
        círculos internos das paredes, metade das amostras); ao parar, o quadro final volta completo."""
        key = (w, h, round(float(cam.position[0]), 4), round(float(cam.position[2]), 4), quality.name, scan, moving)
        if self._static is not None and self._static[0] == key:
            return self._static[1]
        pix = QtGui.QPixmap(w, h)
        p = QtGui.QPainter(pix)
        p.drawPixmap(0, 0, self.background(w, h, scan))
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self._walls(p, cam, quality, moving=moving)
        self._floor(p, cam, quality, moving=moving)
        self._structure(p, cam)
        p.end()
        self._static = (key, pix)
        self.static_renders += 1
        return pix

    def console_layer(self, cam: Camera, panels: list[dict], selected: str, hover: str
                      ) -> tuple[QtCore.QPointF, QtGui.QPixmap | None]:
        """Pedestal e placas do console numa imagem transparente recortada (acima do brilho e do anel do piso,
        abaixo das luzes e do rotor) — refeita quando a câmera, o painel escolhido ou o cursor mudam."""
        key = (cam.width, cam.height, round(float(cam.position[0]), 4), round(float(cam.position[2]), 4),
               selected, hover)
        if self._console is not None and self._console[0] == key:
            return self._console[1], self._console[2]
        hexa = [PANEL_ANGLES[k] - math.pi / 6 for k in PANELS]
        bounds = [[r * math.cos(a), y, r * math.sin(a)] for a in hexa
                  for y, r in ((0.0, PED_R + 0.2), (OUT_Y, OUT_R), (IN_Y, IN_R))]
        bx, by, _bz = cam.project(np.array(bounds))
        if not (np.all(np.isfinite(bx)) and np.all(np.isfinite(by))):
            self._console = (key, QtCore.QPointF(0, 0), None)
            return self._console[1], None
        left, top = int(math.floor(bx.min())) - 4, int(math.floor(by.min())) - 4
        width, height = int(math.ceil(bx.max())) + 4 - left, int(math.ceil(by.max())) + 4 - top
        pix = QtGui.QPixmap(max(1, width), max(1, height))
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.translate(-left, -top)
        self._pedestal(p, cam)
        for panel in sorted(panels, key=lambda item: -item["depth"]):
            self._panel_plate(p, panel, selected, hover)
        p.end()
        self._console = (key, QtCore.QPointF(left, top), pix)
        self.static_renders += 1
        return self._console[1], pix

    # ------------------------------------------------------------ sala (camada fixa)
    def _walls(self, painter, cam: Camera, quality: RoomQuality, *, moving: bool = False) -> None:
        """Círculos nas paredes (duplos), em perspectiva verdadeira, com neblina."""
        heights = (0.95, 1.85, 2.75)[:quality.roundel_rows]
        rows = []
        for i in range(16):
            a = i * math.tau / 16 + math.pi / 16
            normal = np.array([-math.cos(a), 0.0, -math.sin(a)])
            tangent = np.array([-math.sin(a), 0.0, math.cos(a)])
            for y in heights:
                center = np.array([ROOM_R * math.cos(a), y, ROOM_R * math.sin(a)])
                if cam.facing(center, normal) < 0.08:
                    continue
                rows.append(_circle(center, 0.36, 18, axis_u=tangent, axis_v=(0.0, 1.0, 0.0)))
                if not moving:
                    rows.append(_circle(center, 0.22, 18, axis_u=tangent, axis_v=(0.0, 1.0, 0.0)))
        if rows:
            self._rows(painter, np.stack(rows), cam, _mix(AMBER, ICE, 0.25), 0.5)
        # anéis do teto e da base das paredes
        samples = quality.ring_samples // (2 if moving else 1)
        ring_rows = [_circle((0.0, 0.0, 0.0), ROOM_R, samples), _circle((0.0, CEILING, 0.0), ROOM_R * 0.92, samples)]
        self._rows(painter, np.stack(ring_rows), cam, (103, 243, 255), 0.35)

    def _floor(self, painter, cam: Camera, quality: RoomQuality, *, moving: bool = False) -> None:
        n = quality.ring_samples // (2 if moving else 1)
        rings = np.stack([_circle((0.0, 0.0, 0.0), r, n) for r in (0.85, 1.6, 2.4, 3.2, 4.1, 5.0)])
        self._rows(painter, rings, cam, (22, 139, 255), 0.55)
        spokes = []
        count = 12 if moving else 24
        for i in range(count):
            a = i * math.tau / count
            t = np.linspace(0.85, 5.0, 9)[:, None]
            spokes.append(np.hstack([t * math.cos(a), np.zeros_like(t), t * math.sin(a)]))
        self._rows(painter, np.stack(spokes), cam, (22, 139, 255), 0.32)

    def _structure(self, painter, cam: Camera) -> None:
        """Seis colunas curvas (entre os painéis) e as nervuras do teto até o conector do rotor."""
        rows = []
        for i in range(6):
            a = PANEL_ANGLES[PANELS[i]] + math.pi / 6
            t = np.linspace(0.0, 1.0, 12)[:, None]
            radius = 3.5 - 1.0 * t ** 2 + 0.25 * np.sin(t * math.pi)
            y = CEILING * t
            rows.append(np.hstack([radius * math.cos(a), y, radius * math.sin(a)]))
            u = np.linspace(0.0, 1.0, 12)[:, None]
            r2 = 2.5 * (1 - u) + 0.42 * u
            y2 = CEILING - 0.05 - 0.55 * u ** 1.5
            rows.append(np.hstack([r2 * math.cos(a), y2, r2 * math.sin(a)]))
        self._rows(painter, np.stack(rows), cam, _mix((103, 243, 255), AMBER, 0.3), 0.55)
        connector = np.stack([_circle((0.0, CEILING - 0.6, 0.0), 0.42, 32),
                              _circle((0.0, ROTOR_Y1 + 0.05, 0.0), ROTOR_R + 0.06, 32)])
        self._rows(painter, connector, cam, AMBER, 0.6)

    def _floor_glow(self, painter, cam: Camera, scene: RoomScene) -> None:
        x, y, z = cam.point((0.0, 0.0, 0.0))
        if not math.isfinite(x):
            return
        radius = cam.focal * 2.2 / max(0.5, z)
        sprite = self.glow(radius, scene.color, 0.4 * scene.brightness, squash=0.32)
        painter.drawPixmap(QtCore.QPointF(x - sprite.width() / 2, y - sprite.height() / 2), sprite)

    def _fault_ring(self, painter, cam: Camera, scene: RoomScene, quality: RoomQuality) -> None:
        pulse = 0.55 + 0.45 * math.sin(scene.time * 7.0)
        alpha = min(1.0, scene.fault_glow * pulse)
        for radius in (1.7, 1.85):
            self._ring(painter, _circle((0.0, 0.01, 0.0), radius, quality.ring_samples), cam, RED, alpha)

    # ------------------------------------------------------------ console
    def _panel_geometry(self, cam: Camera) -> list[dict]:
        out = []
        for key in PANELS:
            phi = PANEL_ANGLES[key]
            left, right = phi - math.pi / 6, phi + math.pi / 6
            corners = np.array([[OUT_R * math.cos(left), OUT_Y, OUT_R * math.sin(left)],
                                [OUT_R * math.cos(right), OUT_Y, OUT_R * math.sin(right)],
                                [IN_R * math.cos(right), IN_Y, IN_R * math.sin(right)],
                                [IN_R * math.cos(left), IN_Y, IN_R * math.sin(left)]])
            center = corners.mean(axis=0)
            normal = np.array([math.cos(phi) * 0.28, 1.0, math.sin(phi) * 0.28])
            normal /= np.linalg.norm(normal)
            sx, sy, z = cam.project(corners)
            visible = bool(np.all(np.isfinite(sx)) and np.all(np.isfinite(sy)))
            poly = fastpath.polygon(np.stack([sx, sy], axis=1)) if visible else None
            out.append({"key": key, "corners": corners, "center": center, "sx": sx, "sy": sy, "poly": poly,
                        "depth": float(cam.point(center)[2]), "facing": cam.facing(center, normal)})
        self.panel_polygons = [(p["depth"], p["key"], p["poly"]) for p in out if p["poly"] is not None]
        return out

    def _pedestal(self, painter, cam: Camera) -> None:
        """Pedestal hexagonal: três contornos fechados e as seis arestas verticais (quatro chamadas)."""
        rgb = _mix(AMBER, (103, 243, 255), 0.45)
        hexa = [PANEL_ANGLES[k] - math.pi / 6 for k in PANELS]
        for y, r in ((0.0, PED_R + 0.2), (0.80, PED_R), (OUT_Y, OUT_R)):
            ring = np.array([[r * math.cos(a), y, r * math.sin(a)] for a in hexa + hexa[:1]])
            self._ring(painter, ring, cam, rgb, 0.6)
        ends = np.array([[[(PED_R + 0.2) * math.cos(a), 0.0, (PED_R + 0.2) * math.sin(a)],
                          [PED_R * math.cos(a), 0.80, PED_R * math.sin(a)]] for a in hexa]).reshape(-1, 3)
        sx, sy, _z = cam.project(ends)
        lines = [QtCore.QLineF(sx[i], sy[i], sx[i + 1], sy[i + 1]) for i in range(0, len(ends), 2)
                 if np.isfinite(sx[i:i + 2]).all() and np.isfinite(sy[i:i + 2]).all()]
        if lines:
            painter.setPen(_pen(rgb, 0.5))
            painter.drawLines(lines)

    def _panel_plate(self, painter, panel: dict, selected: str, hover: str) -> None:
        """Placa do painel (camada fixa): preenchimento e contorno; escolhido/sob o cursor mais claros."""
        poly = panel["poly"]
        if poly is None:
            return
        lit = max(0.0, panel["facing"])
        is_selected, is_hovered = panel["key"] == selected, panel["key"] == hover
        painter.setBrush(_color(_mix(NAVY, AMBER, 0.12), 0.55 + 0.3 * lit))
        edge = ICE if is_selected else AMBER
        painter.setPen(_pen(edge, 0.35 + 0.45 * lit + (0.2 if is_hovered else 0.0) + (0.2 if is_selected else 0.0),
                            1.6 if is_selected else 1.0))
        painter.drawPolygon(poly)

    def _panel_lights(self, painter, cam: Camera, scene: RoomScene, panel: dict) -> None:
        """Luzes do painel (por quadro): brilho da tarefa em execução, pulso ao terminar, vermelho na falha e
        a grade de luzes que pisca enquanto a tarefa roda."""
        poly = panel["poly"]
        if poly is None:
            return
        state = scene.panels[panel["key"]]
        lit = max(0.0, panel["facing"])
        activity = max(state.level, state.flash)
        if activity > 0.02 or state.fault > 0.02:
            tint = RED if state.fault > activity else AMBER
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(_color(tint, 0.45 * max(activity, state.fault)))
            painter.drawPolygon(poly)
        corners = panel["corners"]
        dots = []
        for v in (0.28, 0.5, 0.72):
            for u in (0.22, 0.4, 0.6, 0.78):
                outer = corners[0] * (1 - u) + corners[1] * u
                inner = corners[3] * (1 - u) + corners[2] * u
                dots.append(outer * (1 - v) + inner * v)
        dx, dy, dz = cam.project(np.array(dots))
        valid = np.isfinite(dx) & np.isfinite(dy)
        if not valid.any():
            return
        width = float(max(2.4, min(6.5, cam.focal * 0.044 / max(0.5, float(np.nanmean(dz))))))
        base = 0.22 + 0.2 * lit
        index = np.arange(len(dots))
        blink = 0.5 + 0.5 * np.sin(scene.time * (4.0 + index % 3) + index * 1.7)
        lit_dots = activity * blink > 0.35                   # com tarefa rodando, metade das luzes pisca
        warm = RED if state.fault > 0.3 else AMBER
        groups = ((warm, valid & ~lit_dots, base),
                  (warm, valid & lit_dots & (index % 5 != 0), base + 0.55 * activity),
                  (CYAN, valid & lit_dots & (index % 5 == 0), base + 0.55 * activity))
        for rgb, mask, alpha in groups:
            if mask.any():
                pen = _pen(rgb, alpha, width)
                pen.setCapStyle(QtCore.Qt.RoundCap)
                painter.setPen(pen)
                painter.drawPoints(fastpath.polygon(np.stack([dx[mask], dy[mask]], axis=1)))

    def _rotor(self, painter, cam: Camera, scene: RoomScene, quality: RoomQuality, effects: bool) -> None:
        offset = scene.rotor_offset()
        rgb = scene.color
        top = cam.point((0.0, ROTOR_Y1, 0.0))
        bottom = cam.point((0.0, ROTOR_Y0, 0.0))
        middle = cam.point((0.0, (ROTOR_Y0 + ROTOR_Y1) / 2, 0.0))
        if not all(math.isfinite(v) for v in (*top[:2], *bottom[:2], *middle[:2])):
            return
        half = cam.focal * ROTOR_R / max(0.5, middle[2])
        if effects and quality.glow:
            sprite = self.glow(half * 3.6, rgb, 0.42 * scene.brightness)
            painter.drawPixmap(QtCore.QPointF(middle[0] - sprite.width() / 2, middle[1] - sprite.height() / 2),
                               sprite)
        # vidro
        glass = QtGui.QLinearGradient(middle[0] - half, 0, middle[0] + half, 0)
        glass.setColorAt(0.0, _color(rgb, 0.10 + 0.10 * scene.brightness))
        glass.setColorAt(0.5, _color(rgb, 0.04))
        glass.setColorAt(1.0, _color(rgb, 0.10 + 0.10 * scene.brightness))
        painter.setBrush(glass)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(middle[0] - half, top[1], half * 2, bottom[1] - top[1]))
        # mecanismo interno: duas pilhas de anéis que se aproximam e se afastam
        travel = 0.55 * offset
        ring_rgb = _mix(rgb, ICE, 0.25)
        for k in range(3):
            y_low = ROTOR_Y0 + 0.12 + travel + k * 0.13
            y_high = ROTOR_Y1 - 0.12 - travel - k * 0.13
            for y in (y_low, y_high):
                self._ring(painter, _circle((0.0, y, 0.0), ROTOR_R * (0.78 - 0.1 * k), 28), cam, ring_rgb,
                           0.55 + 0.45 * scene.brightness - 0.1 * k)
        # hastes que giram
        rods = []
        for a in (scene.spin, scene.spin + math.pi * 2 / 3, scene.spin + math.pi * 4 / 3):
            x, z = 0.13 * math.cos(a), 0.13 * math.sin(a)
            rods += [[x, ROTOR_Y0 + 0.1, z], [x, ROTOR_Y0 + 0.1 + travel + 0.3, z],
                     [x, ROTOR_Y1 - 0.1, z], [x, ROTOR_Y1 - 0.1 - travel - 0.3, z]]
        rx, ry, _rz = cam.project(np.array(rods))
        if np.all(np.isfinite(rx)) and np.all(np.isfinite(ry)):
            painter.setPen(_pen(ICE, 0.45 + 0.4 * scene.brightness))
            painter.drawLines([QtCore.QLineF(rx[i], ry[i], rx[i + 1], ry[i + 1]) for i in range(0, len(rods), 2)])
        # núcleo de luz entre as pilhas
        gap_low = cam.point((0.0, ROTOR_Y0 + 0.12 + travel + 0.3, 0.0))
        gap_high = cam.point((0.0, ROTOR_Y1 - 0.12 - travel - 0.3, 0.0))
        if all(math.isfinite(v) for v in (*gap_low[:2], *gap_high[:2])):
            beam = QtGui.QLinearGradient(0, gap_high[1], 0, gap_low[1])
            beam.setColorAt(0.0, _color(rgb, 0.0))
            beam.setColorAt(0.5, _color(_mix(rgb, ICE, 0.5), 0.55 * scene.brightness + 0.15))
            beam.setColorAt(1.0, _color(rgb, 0.0))
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(beam)
            core = max(2.0, half * 0.35)
            painter.drawRect(QtCore.QRectF(middle[0] - core, gap_high[1], core * 2, gap_low[1] - gap_high[1]))
        # contorno do vidro
        for y in (ROTOR_Y0, ROTOR_Y1):
            self._ring(painter, _circle((0.0, y, 0.0), ROTOR_R, 36), cam, _mix(rgb, ICE, 0.4), 0.75)
        painter.setPen(_pen(_mix(rgb, ICE, 0.4), 0.6))
        painter.drawLine(QtCore.QPointF(middle[0] - half, top[1]), QtCore.QPointF(middle[0] - half, bottom[1]))
        painter.drawLine(QtCore.QPointF(middle[0] + half, top[1]), QtCore.QPointF(middle[0] + half, bottom[1]))

    # ------------------------------------------------------------ telas, feixe, rótulos
    def _screens(self, painter, cam: Camera, scene: RoomScene) -> None:
        """Telas flutuantes atrás do console (presas à câmera): fila, rotor e o último resultado REAIS.
        Cada tela é uma imagem em cache (refeita quando o texto ou o tamanho mudam)."""
        if not scene.screens:
            return
        slots = (("left", 0.95), ("center", 0.0), ("right", -0.95))
        for slot, offset in slots:
            content = scene.screens.get(slot)
            if not content:
                continue
            a = scene.azimuth + math.pi + offset
            x, y, z = cam.point((3.1 * math.cos(a), 2.35 if slot != "center" else 3.05, 3.1 * math.sin(a)))
            if not (math.isfinite(x) and math.isfinite(y)) or z <= 0.3:
                continue
            width = int(cam.focal * 2.0 / z)
            height = int(cam.focal * 0.84 / z)
            if width < 30 or height < 16:
                continue
            pix = self._screen_pixmap(slot, content, width, height)
            painter.drawPixmap(QtCore.QPointF(x - width / 2, y - height / 2), pix)

    def _screen_pixmap(self, slot: str, content, width: int, height: int) -> QtGui.QPixmap:
        title, lines, rgb = content
        key = (slot, title, tuple(lines), tuple(int(c) for c in rgb), width, height)
        cached = self._screen_cache.get(slot)
        if cached is not None and cached[0] == key:
            return cached[1]
        pix = QtGui.QPixmap(width, height)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        rect = QtCore.QRectF(0.5, 0.5, width - 1, height - 1)
        p.setPen(_pen(rgb, 0.55))
        p.setBrush(_color(ABYSS, 0.62))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(_pen(rgb, 0.18))
        p.drawLine(QtCore.QPointF(6, height * 0.28), QtCore.QPointF(width - 6, height * 0.28))
        size = int(max(7, min(14, height * 0.15)))
        title_font = self.font(size, bold=True, spacing=2.0)
        p.setFont(title_font)
        p.setPen(_color(rgb, 0.95))
        inner = width - 16
        p.drawText(QtCore.QPointF(8, 4 + size), QtGui.QFontMetricsF(title_font).elidedText(
            title, QtCore.Qt.ElideRight, inner))
        if size >= 8 and lines:
            body_font = self.font(max(7, size - 2), spacing=0.5)
            metrics = QtGui.QFontMetricsF(body_font)
            p.setFont(body_font)
            p.setPen(_color(ICE, 0.85))
            y = height * 0.32 + metrics.ascent()
            wrapped = [part for line in lines for part in _wrap(str(line), metrics, inner)]
            for line in wrapped:
                if y + metrics.descent() > height - 3:
                    break
                p.drawText(QtCore.QPointF(8, y), metrics.elidedText(line, QtCore.Qt.ElideRight, inner))
                y += metrics.height()
        p.end()
        self._screen_cache[slot] = (key, pix)
        return pix

    def _beam(self, painter, cam: Camera, scene: RoomScene) -> None:
        """Feixe JARVIS ⇄ TARDIS: só enquanto uma tarefa pedida pelo JARVIS está em execução."""
        x, y, _z = cam.point((0.0, 1.95, 0.0))
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        start = QtCore.QPointF(18.0, cam.height * 0.58)
        end = QtCore.QPointF(x, y)
        pen = _pen(CYAN, 0.85 * scene.beam, 1.5)
        pen.setDashPattern([6, 5])
        pen.setDashOffset(-scene.time * 18.0)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.setBrush(_color(CYAN, 0.8 * scene.beam))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(start, 5, 5)
        painter.setFont(self.font(11, bold=True, spacing=2.5))
        painter.setPen(_color(CYAN, scene.beam))
        painter.drawText(QtCore.QPointF(start.x() + 10, start.y() - 10), "JARVIS ⇄ TARDIS")

    def _labels(self, painter, cam: Camera, scene: RoomScene, panels: list[dict]) -> None:
        for panel in panels:
            if panel["facing"] < 0.12:
                continue
            key = panel["key"]
            phi = PANEL_ANGLES[key]
            x, y, z = cam.point((OUT_R * 1.08 * math.cos(phi), OUT_Y - 0.08, OUT_R * 1.08 * math.sin(phi)))
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            state = scene.panels[key]
            selected, hovered = key == scene.selected, key == scene.hover
            size = int(max(8, min(13, cam.focal * 0.045 / max(0.6, z))))
            painter.setFont(self.font(size, bold=selected, spacing=2.0))
            rgb = RED if state.fault > 0.3 else (ICE if selected or hovered else AMBER)
            alpha = 0.45 + 0.4 * min(1.0, panel["facing"] * 1.5) + (0.15 if selected or hovered else 0.0)
            text = state.label + (" ●" if state.running else "")
            metrics = QtGui.QFontMetricsF(painter.font())
            width = metrics.horizontalAdvance(text)
            painter.setPen(_color(rgb, alpha))
            painter.drawText(QtCore.QPointF(x - width / 2, y + size + 6), text)

    def _motes(self, painter, cam: Camera, scene: RoomScene, limit: int) -> None:
        motes = scene.motes[:limit]
        pts = np.array([[m.x, m.y, m.z] for m in motes])
        sx, sy, z = cam.project(pts)
        valid = np.isfinite(sx) & np.isfinite(sy) & (z < 9.0)
        if not valid.any():
            return
        pen = _pen(_mix(scene.color, ICE, 0.5), 0.35 + 0.25 * scene.brightness, 2.0)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPoints(fastpath.polygon(np.stack([sx[valid], sy[valid]], axis=1)))

    def _hud(self, painter, w: int, h: int, scene: RoomScene, style, glow: float) -> None:
        painter.setFont(self.font(10, spacing=3.0))
        painter.setPen(_color(AMBER, 0.75))
        painter.drawText(QtCore.QPointF(18, 26), "TARDIS · SALA DE CONTROLE")
        painter.setFont(self.font(13, bold=True, spacing=3.0))
        painter.setPen(_color(scene.color, 0.95))
        painter.drawText(QtCore.QPointF(18, 48), f"ROTOR · {style.label}")
        painter.setFont(self.font(10, spacing=1.0))
        y = 66
        if scene.running:
            painter.setPen(_color(ICE, 0.85))
            painter.drawText(QtCore.QPointF(18, y), f"executando: {scene.running.get('kind_label', '')}")
            y += 16
        if scene.queued:
            painter.setPen(_color(ICE, 0.7))
            painter.drawText(QtCore.QPointF(18, y), f"{scene.queued} na fila")
            y += 16
        for operation in scene.operations[:2]:
            painter.setPen(_color((77, 232, 194), 0.85))
            painter.drawText(QtCore.QPointF(18, y), f"operação: {operation[:60]}")
            y += 16
        if scene.fault and scene.fault_text:
            painter.setPen(_color(RED, 0.95))
            painter.drawText(QtCore.QPointF(18, y), QtGui.QFontMetricsF(painter.font()).elidedText(
                f"falha: {scene.fault_text}", QtCore.Qt.ElideRight, w * 0.34))
        painter.setFont(self.font(9, spacing=1.0))
        painter.setPen(_color((127, 155, 183), 0.85))
        note = "um só modelo de linguagem: o mesmo do JARVIS" + (f" ({scene.model_label})" if scene.model_label
                                                                else "")
        painter.drawText(QtCore.QPointF(18, h - 14), note)
        hint = "clique num painel do console · Esc fecha o painel"
        width = QtGui.QFontMetricsF(painter.font()).horizontalAdvance(hint)
        painter.drawText(QtCore.QPointF(w - width - 18, h - 14), hint)


class RoomView(QtWidgets.QWidget):
    """A sala desenhada na CPU. O relógio (passo da cena + redesenho) é da página."""

    panel_clicked = QtCore.Signal(str)

    def __init__(self, scene: RoomScene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.renderer = RoomRenderer()
        self.quality = quality_for("balanced")
        self.effects = True
        self.frame_times: deque = deque(maxlen=120)
        self.paint_count = 0
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)

    def set_profile(self, profile_name: str, *, effects: bool) -> None:
        self.quality = quality_for(profile_name)
        self.effects = bool(effects)
        count = self.quality.motes if effects else 0
        if len(self.scene.motes) != count:
            self.scene.set_motes(count)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        started = time.perf_counter()
        painter = QtGui.QPainter(self)
        try:
            self.renderer.render(painter, self.width(), self.height(), self.scene, quality=self.quality,
                                 effects=self.effects)
        finally:
            painter.end()
        self.frame_times.append(time.perf_counter() - started)
        self.paint_count += 1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt)
        pos = event.position()
        key = self.renderer.panel_at(pos.x(), pos.y())
        if key != self.scene.hover:
            self.scene.hover = key
            self.setCursor(QtCore.Qt.PointingHandCursor if key else QtCore.Qt.ArrowCursor)
            self.setToolTip(f"Painel {self.scene.panels[key].label}" if key else "")
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self.scene.hover:
            self.scene.hover = ""
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() != QtCore.Qt.LeftButton:
            return
        pos = event.position()
        key = self.renderer.panel_at(pos.x(), pos.y())
        if key:
            self.panel_clicked.emit(key)
