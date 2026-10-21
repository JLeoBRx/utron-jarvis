"""Renderização do avatar holográfico — QPainter sobre NumPy (CPU por padrão; o mesmo código desenha
num QOpenGLWidget quando a renderização por GPU está ligada).

Camadas, de trás para a frente:

1. **fundo em cache** (por tamanho): espaço profundo, halo, grade 3D do piso, plataforma de projeção e
   feixe — o DNA do avatar original;
2. **ambiente**: anéis de dados girando (velocidade pelo estado), partículas subindo pelo feixe,
   halo de escuta pelo nível REAL do microfone, anéis de fala pelo nível REAL da saída;
3. **pescoço, colar com o reator e orelhas**;
4. **malha da cabeça**: contornos e meridianos por níveis de brilho (iluminação direcional + borda),
   linha de varredura, costuras e linhas de relevo;
5. **rosto**: olhos com íris e pálpebras, sobrancelhas, boca com mandíbula, lábios e grade de voz;
6. **brilho**: os traços luminosos redesenhados numa imagem pequena, desfocada em NumPy e somada;
7. **efeitos de estado**: montagem do boot (plano de varredura), viseira de privacidade, "falha" de
   projeção no erro, tinta âmbar de alerta.

Custo: proporcional ao número de chamadas de desenho (segmentos agrupados por nível), não aos pixels.
Densidade da malha, partículas e brilho seguem o perfil de qualidade; sem "efeitos pesados", nada de
brilho, partículas nem anéis animados.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PySide6 import QtCore, QtGui

from . import fastpath
from .geometry import (DENSITY, EYE_THETA, LIGHT, Y_BROW, Y_CHIN, Y_EYE, Y_MOUTH, FaceGeometry, RadiusTable,
                       jaw_transform, rotation)
from .rig import Rig, mix

WHITE = (220.0, 238.0, 255.0)
DEEP = (3, 7, 18)
ELECTRIC = (22.0, 139.0, 255.0)
CORAL = (255.0, 93.0, 115.0)
CAMERA = 5.5


@dataclass(frozen=True)
class AvatarQuality:
    name: str
    density: str
    bloom: bool
    particles: int
    rings: int
    accents: bool


QUALITY = {
    "economy": AvatarQuality("economy", "economy", False, 0, 1, False),
    "balanced": AvatarQuality("balanced", "balanced", True, 36, 2, True),
    "high": AvatarQuality("high", "high", True, 60, 3, True),
    "cinematic": AvatarQuality("cinematic", "cinematic", True, 90, 3, True),
}


def quality_for(profile_name: str) -> AvatarQuality:
    return QUALITY.get(str(profile_name or ""), QUALITY["balanced"])


def qcolor(rgb, alpha: float) -> QtGui.QColor:
    color = QtGui.QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
    color.setAlphaF(float(max(0.0, min(1.0, alpha))))
    return color


def box_blur(img: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return img
    k = 2 * r + 1
    padded = np.pad(img, ((r + 1, r), (0, 0)), mode="constant")
    c = np.cumsum(padded, axis=0, dtype=np.float32)
    img = (c[k:] - c[:-k]) / k
    padded = np.pad(img, ((0, 0), (r + 1, r)), mode="constant")
    c = np.cumsum(padded, axis=1, dtype=np.float32)
    return (c[:, k:] - c[:, :-k]) / k


class _Pens:
    def __init__(self):
        self._cache: dict = {}

    def __call__(self, rgb, alpha: float, width: float = 1.0) -> QtGui.QPen:
        key = (int(rgb[0]), int(rgb[1]), int(rgb[2]), round(alpha, 3), width)
        pen = self._cache.get(key)
        if pen is None:
            if len(self._cache) > 4000:
                self._cache.clear()
            pen = QtGui.QPen(qcolor(rgb, alpha), width)
            pen.setCosmetic(True)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)
            self._cache[key] = pen
        return pen


class AvatarRenderer:
    def __init__(self):
        self.table = RadiusTable()
        self._geometry: dict[str, FaceGeometry] = {}
        self.pen = _Pens()
        self._background: QtGui.QImage | None = None
        self._background_key = None
        self._scanlines: QtGui.QImage | None = None
        rng = np.random.default_rng(11)
        self._particles = rng.random((120, 4))                  # x, fase, velocidade, tamanho
        self.last_stats: dict = {}

    def geometry(self, density: str) -> FaceGeometry:
        geo = self._geometry.get(density)
        if geo is None:
            geo = self._geometry[density] = FaceGeometry(DENSITY.get(density, DENSITY["balanced"]))
        return geo

    # ------------------------------------------------------------ enquadramento
    @staticmethod
    def frame(width: int, height: int) -> tuple[float, float, float]:
        """(cx, cy, escala): a cabeça cabe na largura e na altura."""
        scale = min(height * 0.255, width * 0.30)
        return width * 0.5, height * 0.43, scale

    # ------------------------------------------------------------ fundo (cache por tamanho)
    def background(self, width: int, height: int, effects: bool) -> QtGui.QImage:
        key = (width, height, effects)
        if self._background_key == key and self._background is not None:
            return self._background
        cx, cy, scale = self.frame(width, height)
        image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor(*DEEP))
        p = QtGui.QPainter(image)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        halo = QtGui.QRadialGradient(cx, cy, scale * 1.7)
        halo.setColorAt(0, qcolor((0, 217, 255), 0.09))
        halo.setColorAt(0.5, qcolor(ELECTRIC, 0.035))
        halo.setColorAt(1, qcolor(ELECTRIC, 0.0))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QtCore.QPointF(cx, cy), scale * 1.7, scale * 1.7)
        base = QtCore.QPointF(cx, min(height - 12.0, cy + scale * 2.05))
        if effects:
            # grade 3D do piso (perspectiva fixa), sumindo nas bordas
            for i in range(-10, 11):
                x0 = cx + i * scale * 0.42
                x1 = cx + i * scale * 0.12
                alpha = 0.10 * (1 - abs(i) / 11)
                p.setPen(self.pen((0, 160, 220), alpha))
                p.drawLine(QtCore.QPointF(x0, height), QtCore.QPointF(x1, base.y() - scale * 0.05))
            for j in range(1, 9):
                y = base.y() - scale * 0.05 + (height - base.y()) * (j / 8) ** 1.6
                p.setPen(self.pen((0, 160, 220), 0.08 * (1 - j / 10)))
                p.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(width, y))
        p.setBrush(QtCore.Qt.NoBrush)
        for radius, alpha in ((1.05, 0.30), (0.78, 0.22), (0.45, 0.35)):
            p.setPen(self.pen((0, 217, 255), alpha))
            p.drawEllipse(base, scale * radius, scale * radius * 0.12)
        beam = QtGui.QLinearGradient(0, base.y(), 0, cy - scale * 0.2)
        beam.setColorAt(0, qcolor((0, 217, 255), 0.06))
        beam.setColorAt(1, qcolor((0, 217, 255), 0.0))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(beam)
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(cx - scale * 0.45, base.y()),
                                       QtCore.QPointF(cx + scale * 0.45, base.y()),
                                       QtCore.QPointF(cx + scale * 1.0, cy - scale * 0.2),
                                       QtCore.QPointF(cx - scale * 1.0, cy - scale * 0.2)]))
        p.end()
        self._background, self._background_key = image, key
        self._scanlines = None
        return image

    def scanlines(self, width: int, height: int) -> QtGui.QImage:
        if self._scanlines is None or self._scanlines.size() != QtCore.QSize(width, height):
            image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(image)
            p.setPen(QtGui.QPen(qcolor((0, 0, 0), 0.22), 1))
            for y in range(0, height, 3):
                p.drawLine(0, y, width, y)
            p.end()
            self._scanlines = image
        return self._scanlines

    # ------------------------------------------------------------ quadro
    def render(self, p: QtGui.QPainter, width: int, height: int, rig: Rig, t: float, quality: AvatarQuality,
               *, effects: bool = True) -> dict:
        geo = self.geometry(quality.density)
        cx, cy, scale = self.frame(width, height)
        cx += rig.offset_x * scale
        p.drawImage(0, 0, self.background(width, height, effects))
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        R = rotation(rig.yaw, rig.pitch, rig.roll)
        light = max(0.0, 1.0 - 0.6 * rig.dim) * (1.0 + 0.4 * rig.pulse)
        glow = max(0.05, rig.glow) * light
        color = rig.rgb
        bright = mix(color, WHITE, 0.45)
        bloom_items: list = []
        calls = 0

        def project(points):
            q = points @ R.T
            f = CAMERA / (CAMERA - q[..., 2])
            return np.stack([cx + q[..., 0] * f * scale, cy - q[..., 1] * f * scale], -1), q

        plane_y = 1.05 - rig.assemble * 2.95                    # montagem do boot (de cima para baixo)

        def assembled(y):
            return np.where(y >= plane_y, 1.0, 0.0) if rig.assemble < 0.999 else 1.0

        # --- ambiente
        if effects:
            calls += self._rings(p, cx, cy, scale, rig, t, quality)
            calls += self._particles_layer(p, cx, cy, scale, rig, t, quality, height)
        if rig.mic_level > 0.01:                                 # halo de escuta: nível REAL do microfone
            level = min(1.0, rig.mic_level * 4.0)
            p.setBrush(QtCore.Qt.NoBrush)
            for k in range(3):
                radius = scale * (1.18 + 0.10 * k + 0.22 * level)
                p.setPen(self.pen(color, min(1.0, (0.45 - 0.12 * k) * level)))       # 1 px: caminho rápido
                p.drawEllipse(QtCore.QPointF(cx, cy), radius, radius * 1.08)
                calls += 1
        # --- pescoço, colar e orelhas
        lxy, lq = project(geo.lower)
        la = np.clip(0.10 + 0.32 * (lq[..., 2] + 0.35), 0.0, 0.6) * glow * assembled(geo.lower[..., 1])
        for level, path in fastpath.level_paths(lxy, np.minimum(la[:, :-1], la[:, 1:])):
            p.setPen(self.pen(mix(color, ELECTRIC, 0.5), level))
            p.drawPath(path)
            calls += 1
        exy, eq = project(geo.ears)
        ea = np.clip((eq[..., 2] + 0.55) * 0.9, 0, 0.9) * glow * assembled(geo.ears[..., 1])
        for level, path in fastpath.level_paths(exy, np.minimum(ea[:, :-1], ea[:, 1:])):
            p.setPen(self.pen(color, level))
            p.drawPath(path)
            calls += 1
        if rig.assemble > 0.9:
            calls += self._reactor(p, project, scale, rig, t, color)
        if rig.out_level > 0.01:                                 # anéis de fala: nível REAL da saída
            level = min(1.0, rig.out_level * 5.0)
            mouth_xy, _ = project(self.table.surface(np.array([0.0]), np.array([Y_MOUTH])))
            center = QtCore.QPointF(*mouth_xy[0].tolist())
            p.setBrush(QtCore.Qt.NoBrush)
            for k in range(3):
                phase = (t * 1.6 + k / 3.0) % 1.0
                radius = scale * (0.25 + 0.55 * phase)
                p.setPen(self.pen(color, 0.38 * level * (1 - phase)))
                p.drawEllipse(center, radius, radius * 0.45)
                calls += 1
        # --- malha da cabeça
        grid, normal = geo.posed_grid(rig.jaw)
        xy, q = project(grid)
        nv = normal @ R.T
        facing = nv[..., 2]
        diffuse = np.clip(nv @ LIGHT, 0, 1)
        rim = np.clip(1 - np.abs(facing), 0, 1) ** 5
        alpha = np.where(facing > 0.0, 0.04 + 0.62 * diffuse ** 1.5 + 0.40 * rim, 0.0)
        scan_y = 1.05 - ((t * 0.28 * rig.scan_speed) % 1.0) * 2.3
        alpha = alpha * (1 + 1.2 * np.exp(-((geo.levels[:, None] - scan_y) / 0.045) ** 2))
        mouth_hole = ((np.abs(grid[..., 1] - (Y_MOUTH - 0.035 * rig.jaw)) < 0.012 + 0.065 * rig.jaw)
                      & (np.abs(grid[..., 0]) < 0.16) & (grid[..., 2] > 0))
        alpha = np.where(mouth_hole, 0.0, alpha) * glow * assembled(grid[..., 1])
        for level, path in fastpath.level_paths(xy, np.minimum(alpha[:, :-1], alpha[:, 1:]) * 0.9):
            p.setPen(self.pen(color, level))
            p.drawPath(path)
            calls += 1
        cols = np.array(geo.meridians)
        vxy = np.transpose(xy[:, cols], (1, 0, 2))
        va = np.transpose(alpha[:, cols], (1, 0))
        for level, path in fastpath.level_paths(vxy, np.minimum(va[:, :-1], va[:, 1:]) * 0.40):
            p.setPen(self.pen(mix(color, ELECTRIC, 0.6), level))
            p.drawPath(path)
            calls += 1
        # silhueta: o primeiro e o último ponto visível de cada linha
        visible = (facing > 0.0) & (np.asarray(assembled(grid[..., 1])) > 0)
        rows = np.where(visible.any(axis=1))[0]
        if len(rows) > 3:
            left = np.argmin(np.where(visible, xy[..., 0], np.inf), axis=1)
            right = np.argmax(np.where(visible, xy[..., 0], -np.inf), axis=1)
            for index in (left, right):
                outline = xy[rows, index[rows]]
                p.setPen(self.pen(bright, min(1.0, 0.8 * glow)))
                p.drawPolyline(fastpath.polygon(outline))
                bloom_items.append((outline, 2.0, 0.35 * glow, False))
                calls += 1
        # costuras e relevo
        lines = geo.lines if quality.accents else geo.lines[:5]
        sxy, sq = project(jaw_transform(lines, rig.jaw))
        sa = np.clip((sq[..., 2] - 0.05) * 1.6, 0, 1) * glow * assembled(lines[..., 1])
        for level, path in fastpath.level_paths(sxy, np.minimum(sa[:, :-1], sa[:, 1:]) * 0.85):
            p.setPen(self.pen(bright, level))
            p.drawPath(path)
            calls += 1
        # --- rosto (só com o rosto montado)
        if rig.assemble > 0.75:
            face_alpha = min(1.0, (rig.assemble - 0.75) / 0.2) * light
            calls += self._eyes(p, project, scale, rig, t, bright, face_alpha, bloom_items)
            calls += self._mouth(p, project, rig, bright, color, face_alpha, bloom_items)
        if rig.assemble < 0.999:                                 # plano de varredura do boot
            calls += self._assembly_plane(p, project, plane_y, color)
        # --- brilho
        if effects and quality.bloom and bloom_items:
            self._bloom(p, bloom_items, width, height, bright)
            calls += 1
        # --- efeitos de estado
        if rig.glitch > 0.05:
            calls += self._glitch(p, width, cy, scale, rig, t)
        if effects:
            p.save()
            p.setOpacity(0.35)
            p.drawImage(0, 0, self.scanlines(width, height))
            p.restore()
            calls += 1
        self.last_stats = {"draw_calls": calls, "rows": len(geo.levels), "bloom": bool(effects and quality.bloom)}
        return self.last_stats

    # ------------------------------------------------------------ partes
    def _reactor(self, p, project, scale, rig, t, color) -> int:
        point, _ = project(np.array([[0.0, -1.50, 0.40]]))
        center = QtCore.QPointF(*point[0].tolist())
        radius = scale * 0.065
        gradient = QtGui.QRadialGradient(center, radius * 2.2)
        gradient.setColorAt(0, qcolor(WHITE, 0.95 * rig.glow))
        gradient.setColorAt(0.28, qcolor(mix(color, WHITE, 0.4), 0.75 * rig.glow))
        gradient.setColorAt(1, qcolor(color, 0.0))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(gradient)
        p.drawEllipse(center, radius * 2.2, radius * 1.6)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(self.pen(mix(color, WHITE, 0.4), 0.85 * rig.glow))
        p.drawArc(QtCore.QRectF(center.x() - radius * 1.5, center.y() - radius * 1.05, radius * 3.0, radius * 2.1),
                  int(t * 80 * 16) % (360 * 16), 250 * 16)
        return 2

    def _rings(self, p, cx, cy, scale, rig, t, quality) -> int:
        """Anéis de dados em perspectiva ao redor da cabeça: arcos e marcas girando pela velocidade do estado."""
        calls = 0
        p.setBrush(QtCore.Qt.NoBrush)
        for k in range(quality.rings):
            radius = scale * (1.45 + 0.22 * k) * (1 + 0.08 * rig.pulse)
            tilt = 0.16 + 0.05 * k
            rect = QtCore.QRectF(cx - radius, cy + scale * 1.25 - radius * tilt, radius * 2, radius * 2 * tilt)
            angle = (t * (18 + 9 * k) * rig.ring_speed * (1 if k % 2 == 0 else -1)) % 360
            p.setPen(self.pen(rig.rgb, 0.10 + 0.05 * rig.pulse))
            p.drawEllipse(rect)
            p.setPen(self.pen(mix(rig.rgb, WHITE, 0.25), 0.55 * rig.glow))
            for arc in range(3):
                p.drawArc(rect, int((angle + arc * 120) * 16), int((24 + 8 * k) * 16))
            calls += 4
        return calls

    def _particles_layer(self, p, cx, cy, scale, rig, t, quality, height) -> int:
        count = int(quality.particles * rig.particles)
        if count <= 0:
            return 0
        part = self._particles[:count]
        life = (part[:, 1] + t * (0.05 + 0.08 * part[:, 2])) % 1.0
        spread = 0.3 + 0.7 * life
        x = cx + (part[:, 0] - 0.5) * scale * 1.6 * spread
        base = min(height - 12.0, cy + scale * 2.05)
        y = base - life * (base - (cy - scale * 1.2))
        points = np.stack([x, y], -1)
        fade = np.sin(life * math.pi)
        p.setPen(self.pen(mix(rig.rgb, WHITE, 0.3), 0.65 * float(np.mean(fade))))
        p.drawPoints(fastpath.polygon(points))
        return 1

    def _eyes(self, p, project, scale, rig, t, bright, face_alpha, bloom_items) -> int:
        calls = 0
        opening = 0.042 * max(0.0, rig.eye_open) * (1.0 - rig.blink)
        visor = rig.visor
        for side in (-1, 1):
            th0 = side * EYE_THETA
            angles = np.linspace(0, 2 * math.pi, 36)
            ex = th0 + 0.155 * np.cos(angles)
            ey = Y_EYE + np.where(np.sin(angles) > 0, opening * 1.15, opening * 0.6) * np.sin(angles) \
                - 0.014 * np.cos(angles) * side
            eye = self.table.surface(ex, ey)
            eye[..., 2] += 0.015
            exy, eq = project(eye)
            seen = float(np.clip(eq[:, 2].mean() * 2.5, 0, 1)) * face_alpha
            lit = seen * (1.0 - 0.85 * visor)
            p.setBrush(qcolor((0, 30, 50), 0.55 * seen))
            p.setPen(self.pen(bright, round(0.95 * lit, 2), 1.4))
            p.drawPolygon(fastpath.polygon(exy))
            bloom_items.append((exy, 3.0, 0.9 * lit, True))
            calls += 1
            if opening > 0.004:                                  # íris (segue o olhar)
                center_xy, _ = project(self.table.surface(np.array([th0 + 0.05 * rig.gaze_x]),
                                                          np.array([Y_EYE + 0.018 * rig.gaze_y]))
                                       + np.array([0, 0, 0.012]))
                center = QtCore.QPointF(*center_xy[0].tolist())
                iris = scale * 0.048
                gradient = QtGui.QRadialGradient(center, iris)
                gradient.setColorAt(0, qcolor(WHITE, 0.98 * lit))
                gradient.setColorAt(0.32, qcolor(rig.iris, 0.85 * lit))
                gradient.setColorAt(1, qcolor(rig.iris, 0.0))
                p.setPen(QtCore.Qt.NoPen)
                p.setBrush(gradient)
                p.drawEllipse(center, iris, iris * max(0.12, min(1.0, opening / 0.042)))
                calls += 1
            # sobrancelha: + erguida, − franzida (a ponta de dentro desce)
            bx = np.linspace(th0 - 0.17 * side, th0 + 0.18 * side, 12)
            inner = np.clip((side * (th0 - bx)) / 0.17, 0, 1)            # 1 perto do nariz
            by = Y_BROW - 0.035 + 0.014 * np.sin((bx - th0) * 9 * side) + 0.03 * rig.brow \
                + 0.025 * min(0.0, rig.brow) * inner
            brow = self.table.surface(bx, by)
            brow[..., 2] += 0.022
            bxy, _ = project(brow)
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(self.pen(bright, round(0.9 * seen, 2), 2.0))
            p.drawPolyline(fastpath.polygon(bxy))
            bloom_items.append((bxy, 3.0, 0.6 * seen, False))
            calls += 1
            if visor > 0.02:                                     # viseira: linhas sobre os olhos
                for k in range(5):
                    yy = Y_EYE - 0.05 + k * 0.025
                    vx = np.linspace(th0 - 0.2, th0 + 0.2, 10)
                    band = self.table.surface(vx, np.full_like(vx, yy))
                    band[..., 2] += 0.03
                    vxy, _ = project(band)
                    p.setPen(self.pen(bright, 0.65 * visor * seen))
                    p.drawPolyline(fastpath.polygon(vxy))
                    calls += 1
        return calls

    def _mouth(self, p, project, rig, bright, color, face_alpha, bloom_items) -> int:
        calls = 0
        jaw = max(0.0, rig.jaw)
        u = np.linspace(-1, 1, 25)
        half = (0.155 + 0.04 * rig.wide - 0.05 * rig.round) / 0.8
        press = max(0.0, min(1.0, rig.press))
        gap = (0.004 + 0.055 * jaw) * (1 - 0.8 * press)
        curve_up = 0.020 * (1 + rig.round) * (1 - 0.5 * press)
        upper = Y_MOUTH + curve_up * (1 - u ** 2) + gap * 0.3
        lower = Y_MOUTH - gap - (0.018 + 0.02 * rig.round) * (1 - 0.5 * press) * (1 - u ** 2)
        top = self.table.surface(u * half, upper)
        bottom = jaw_transform(self.table.surface(u * half, lower), jaw)
        top[..., 2] += 0.014
        bottom[..., 2] += 0.014
        txy, _ = project(top)
        bxy, _ = project(bottom)
        if jaw > 0.05:
            inner = np.concatenate([txy, bxy[::-1]])
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(qcolor((1, 4, 10), 0.92 * face_alpha))
            p.drawPolygon(fastpath.polygon(inner))
            calls += 1
            if rig.teeth > 0.3:                                  # linha dos dentes superiores
                teeth = top * 0.8 + bottom * 0.2
                teeth_xy, _ = project(teeth[3:-3])
                p.setPen(self.pen(WHITE, 0.35 * rig.teeth * face_alpha))
                p.drawPolyline(fastpath.polygon(teeth_xy))
                calls += 1
            index = ((np.linspace(-0.7, 0.7, 9) + 1) / 2 * (len(u) - 1)).astype(int)
            a0, b0 = txy[index], bxy[index]
            bars = np.empty((len(index) * 2, 2))
            bars[0::2] = a0 * 0.75 + b0 * 0.25
            bars[1::2] = a0 * 0.25 + b0 * 0.75
            p.setPen(self.pen(color, round((0.25 + 0.6 * min(1.0, rig.energy)) * face_alpha, 2)))
            p.drawLines(fastpath.polygon(bars))                  # grade de voz: energia REAL da fala
            calls += 1
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(self.pen(bright, 0.95 * face_alpha, 1.5 + 0.6 * press))
        for lip in (txy, bxy):
            p.drawPolyline(fastpath.polygon(lip))
            bloom_items.append((lip, 3.0, 0.8 * face_alpha, False))
            calls += 1
        return calls

    def _assembly_plane(self, p, project, plane_y, color) -> int:
        """Plano de varredura que desce enquanto o boot avança (progresso real dos componentes)."""
        if plane_y < Y_CHIN - 0.9:
            return 0
        a = np.linspace(-math.pi, math.pi, 64)
        ring = np.stack([0.95 * np.sin(a), np.full_like(a, plane_y), 0.95 * np.cos(a)], -1)
        xy, _ = project(ring)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(self.pen(mix(color, WHITE, 0.5), 1.0))
        p.drawPolyline(fastpath.polygon(xy))
        return 1

    def _glitch(self, p, width, cy, scale, rig, t) -> int:
        """Falha de projeção discreta: algumas faixas horizontais corais deslocadas (sem piscar)."""
        calls = 0
        for k in range(3):
            phase = math.sin(t * (13 + 7 * k)) * math.sin(t * (3 + k))
            if abs(phase) < 0.6:
                continue
            y = cy + scale * (-0.9 + 0.8 * k + 0.2 * phase)
            p.setPen(self.pen(CORAL, 0.35 * rig.glitch))
            p.drawLine(QtCore.QPointF(width * 0.5 - scale * (0.9 - 0.1 * phase), y),
                       QtCore.QPointF(width * 0.5 + scale * (0.9 + 0.1 * phase), y))
            calls += 1
        return calls

    def _bloom(self, p, items, width, height, rgb, factor: int = 4) -> None:
        points = np.concatenate([item[0] for item in items])
        x0, y0 = np.maximum(points.min(axis=0) - 40, 0)
        x1, y1 = np.minimum(points.max(axis=0) + 40, [width, height])
        w, h = int((x1 - x0) / factor) + 1, int((y1 - y0) / factor) + 1
        if w < 4 or h < 4:
            return
        small = QtGui.QImage(w, h, QtGui.QImage.Format_Grayscale8)
        small.fill(0)
        sp = QtGui.QPainter(small)
        sp.setRenderHint(QtGui.QPainter.Antialiasing)
        sp.setBrush(QtCore.Qt.NoBrush)
        offset = np.array([x0, y0])
        for xy, pen_width, alpha, closed in items:
            level = int(255 * max(0.0, min(1.0, alpha)))
            sp.setPen(QtGui.QPen(QtGui.QColor(level, level, level), pen_width))
            poly = fastpath.polygon((xy - offset) / factor)
            sp.drawPolygon(poly) if closed else sp.drawPolyline(poly)
        sp.end()
        stride = small.bytesPerLine()
        gray = np.frombuffer(small.constBits(), dtype=np.uint8).reshape(h, stride)[:, :w].astype(np.float32)
        gray = np.clip(box_blur(box_blur(gray, 2), 2) * (1.6 / 255.0), 0, 1)
        rgba = np.empty((h, w, 4), dtype=np.uint8)              # BGRA pré-multiplicado (ARGB32 little-endian)
        rgba[..., 0] = (rgb[2] * gray).astype(np.uint8)
        rgba[..., 1] = (rgb[1] * gray).astype(np.uint8)
        rgba[..., 2] = (rgb[0] * gray).astype(np.uint8)
        rgba[..., 3] = (255 * gray).astype(np.uint8)
        image = QtGui.QImage(rgba.data, w, h, w * 4, QtGui.QImage.Format_ARGB32_Premultiplied)
        p.save()
        p.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        p.drawImage(QtCore.QRectF(x0, y0, w * factor, h * factor), image)
        p.restore()
