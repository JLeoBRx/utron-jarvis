"""TARDIS — a memória espacial do JARVIS (segundo HUB).

Um espaço interior tecnológico, maior por dentro: câmara central de energia (o dia de hoje),
anéis concêntricos que giram devagar, corredores de dados até os portais das regiões —
projetos, compromissos, tarefas, ideias e memórias — e dois satélites (lembretes e revisão).

* Cada portal mostra números e pontos que são registros REAIS do banco (passe o mouse num
  ponto para ver o título). Clique num portal: a câmera viaja até ele e o painel lateral abre
  a região para consultar, criar, editar, concluir, arquivar e excluir (lixeira ou definitivo
  com autorização) — tudo pelo Neural Core.
* Pulsos percorrem os corredores só quando algo REAL acontece (registro criado/alterado,
  lembrete disparado). A câmara central segue o estado de atividade do núcleo.
* "← JARVIS CORE" volta ao HUB principal (na plataforma, "← SALA DE CONTROLE" volta à sala da
  TARDIS); a janela só se esconde — câmera, região aberta e filtros continuam como estavam.
* Som ambiente discreto e opcional (desligado por padrão).

Desempenho: fundo e trajetórias em cache; partículas limitadas pelo perfil; cadência
econômica em repouso, cadência de fundo quando o CORE está em foco e teto do perfil só durante
transições e pulsos; relógio parado com a janela oculta ou minimizada; nenhuma consulta na
thread da interface.
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..secondbrain import timeutil
from ..secondbrain.models import ACTIONABLE, KINDS
from . import quality, theme
from .panels import (IdeasPage, NotificationsPage, PageHost, ProjectsPage, ReviewPage, SearchPage, TasksPage,
                     TimelinePage, TodayPage, _button, _label)
from .tardis_scene import CORE_KEY, CORE_PAGE, REGIONS, SATELLITES, TardisScene
from .window import app_icon

log = logging.getLogger("ultron.tardis")

QPointF = QtCore.QPointF
PLUS = QtGui.QPainter.CompositionMode_Plus
OVER = QtGui.QPainter.CompositionMode_SourceOver
RINGS = ((170.0, 0.10, 36), (245.0, -0.07, 48), (335.0, 0.05, 60), (470.0, -0.035, 72), (640.0, 0.02, 90))
RING_RATIO = 0.42                    # elipse em perspectiva (altura/largura)
PANEL_FRACTION = 0.46
PAINT_BUDGET = 0.35                  # fração máxima da thread da interface gasta pintando o TARDIS
REGION_LABEL = {key: label for key, (label, *_rest) in REGIONS.items()}
REGION_LABEL[CORE_KEY] = "HOJE"


def _thin(color: QtGui.QColor, alpha: float) -> QtGui.QPen:
    """Traço cosmético de 1 px: o caminho rápido de linhas e curvas do QPainter."""
    pen = QtGui.QPen(theme.with_alpha(color, alpha), 1.0)
    pen.setCosmetic(True)
    return pen


def fetch_regions(service) -> dict:
    """Contagens e itens reais de cada região (roda na thread de leitura)."""
    now = service.now()
    store = service.store
    alive = ["deleted_at IS NULL", "archived_at IS NULL"]
    open_ = alive + ["status IN ('open','in_progress','waiting')"]

    def item(r) -> dict:
        return {"id": r.id, "title": r.title, "kind": r.kind, "status": r.status, "priority": r.priority,
                "overdue": r.overdue(now), "confirmed": r.confirmed}

    def count(where, params=()):
        return store.count(list(where), list(params))

    actionable = [k for k in ACTIONABLE if k != "event"]
    placeholders = ", ".join("?" for _ in actionable)
    tasks_open = count(open_ + [f"kind IN ({placeholders})"], actionable)
    overdue = service.overdue(limit=200)
    task_items = service.list(kinds=actionable, status=("open", "in_progress", "waiting"), limit=14)
    projects = service.projects()
    start = service._day_bounds()[0]
    end = service._day_bounds(13)[1]
    events = service.list(kinds=("event",), status=("open", "in_progress", "waiting"), due_after=start,
                          due_before=end, limit=14)
    ideas = service.list(kinds=("idea",), order="recent", limit=14)
    memories = service.list(kinds=("note", "person"), order="recent", limit=14)
    reminders = service.reminders.upcoming(limit=14) if service.reminders is not None else []
    unread = len(service.notifications(limit=200, unread_only=True))
    review = service.review_queue(limit=14)
    trash = len(service.trash(limit=500))
    wall = service.now_wall()
    first_event = events[0] if events else None
    clashing = {r.id for pair in service.agenda_conflicts(days=14) for r in pair}
    regions = {
        "projects": {"count": len(projects), "items": [item(service.store.get(p["record"]["id"])) for p in projects[:14]
                                                       if service.store.get(p["record"]["id"]) is not None],
                     "detail": f"{sum(p['open'] for p in projects)} item(ns) aberto(s)" if projects else "nenhum projeto"},
        "agenda": {"count": count(open_ + ["kind = 'event'", "due_at >= ?", "due_at < ?"], (start, end)),
                   "items": [{**item(r), "overdue": item(r)["overdue"] or r.id in clashing} for r in events],
                   "alert": bool(clashing),
                   "detail": (f"⚠ {len(clashing)} compromisso(s) em conflito de horário" if clashing else
                              (f"próximo: {first_event.title} · " + timeutil.describe(
                                  timeutil.parse_wall(first_event.due_local), all_day=first_event.all_day, now=wall))
                              if first_event else "nada nos próximos 14 dias")},
        "tasks": {"count": tasks_open, "items": [item(r) for r in task_items], "alert": bool(overdue),
                  "detail": f"{len(overdue)} atrasada(s)" if overdue else "nada atrasado"},
        "ideas": {"count": count(alive + ["kind = 'idea'"]), "items": [item(r) for r in ideas],
                  "detail": f"última: {ideas[0].title}" if ideas else "nenhuma ideia salva"},
        "memories": {"count": count(alive + ["kind IN ('note', 'person')"]), "items": [item(r) for r in memories],
                     "detail": "notas, pessoas e busca"},
        "reminders": {"count": len(reminders), "alert": unread > 0,
                      "items": [{"id": r["record_id"], "title": f"{r['title']} — {r['when_text']}", "kind": "reminder",
                                 "status": "open", "priority": 2, "overdue": False, "confirmed": True}
                                for r in reminders],
                      "detail": f"{unread} aviso(s) não lido(s)" if unread else "sem avisos novos"},
        "review": {"count": len(review), "alert": bool(review), "items": [item(r) for r in review],
                   "detail": f"{trash} na lixeira"},
    }
    day = service.today()
    return {"regions": regions, "today": {"priorities": len(day["priorities"]), "events": len(day["events"]),
                                          "overdue": len(day["overdue"]), "date": day["date"]}}


class TardisView(QtWidgets.QWidget):
    """Desenho do TARDIS em duas camadas:

    * **estrutura** (em cache): fundo, anéis, corredores, portais com rótulos e contagens, títulos.
      Só é refeita quando algo dela muda — câmera, tamanho, dados do banco, foco, cursor sobre um
      portal ou estado de atividade. Com a câmera parada (quase sempre), custa um único blit;
    * **movimento** (a cada quadro): marcas girando nos anéis, corredores e portais acesos por
      eventos reais, pulsos, partículas, câmara central e os registros orbitando cada portal.
    """

    region_clicked = QtCore.Signal(str)

    def __init__(self, scene: TardisScene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setMouseTracking(True)
        self.setMinimumSize(480, 360)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self._background: QtGui.QPixmap | None = None
        self._structure: QtGui.QPixmap | None = None
        self._structure_key: tuple | None = None
        self.structure_renders = 0
        self._corridors: dict[str, QtGui.QPainterPath] = {}
        self._ring_path = QtGui.QPainterPath()
        self._ring_path.addEllipse(QPointF(0, 0), 1.0, RING_RATIO)
        self._static: dict[tuple, QtGui.QStaticText] = {}
        self._hover: str | None = None
        self.frame_times: deque = deque(maxlen=300)
        self.paint_count = 0
        self._build_corridors()
        # marcas de cada anel num círculo unitário: a cada quadro só giram (transformação do QPainter)
        self._tick_paths: list[QtGui.QPainterPath] = []
        for i, (_radius, _speed, ticks) in enumerate(RINGS):
            path = QtGui.QPainterPath()
            outer = 1.02 if i % 2 else 1.035
            for angle in np.linspace(0, math.tau, ticks, endpoint=False):
                c, s = math.cos(angle), math.sin(angle)
                path.moveTo(c * 0.985, s * 0.985)
                path.lineTo(c * outer, s * outer)
            self._tick_paths.append(path)

    # ------------------------------------------------------------ caches
    def _build_corridors(self) -> None:
        for key, (_name, (x, y), _depth, _page, _tone) in REGIONS.items():
            path = QtGui.QPainterPath(QPointF(0, 0))
            path.quadTo(QPointF(x * 0.35, y * 0.05 - 60), QPointF(x, y))
            self._corridors[key] = path

    def _ensure_background(self, w: int, h: int, dpr: float) -> QtGui.QPixmap:
        bg = self._background
        if bg is not None and bg.width() == int(w * dpr) and bg.height() == int(h * dpr):
            return bg
        pix = QtGui.QPixmap(max(1, int(w * dpr)), max(1, int(h * dpr)))
        pix.setDevicePixelRatio(dpr)
        p = QtGui.QPainter(pix)
        grad = QtGui.QRadialGradient(w * 0.5, h * 0.52, max(w, h) * 0.8)
        grad.setColorAt(0.0, theme.PANEL)
        grad.setColorAt(0.45, theme.BG2)
        grad.setColorAt(1.0, theme.BG)
        p.fillRect(0, 0, w, h, grad)
        rng = np.random.default_rng(23)                      # campo de pontos fixo (profundidade)
        for x, y, a in zip(rng.uniform(0, w, 260), rng.uniform(0, h, 260), rng.uniform(0.04, 0.22, 260)):
            p.setPen(theme.with_alpha(theme.TEXT, float(a)))
            p.drawPoint(QPointF(float(x), float(y)))
        p.end()
        self._background = pix
        return pix

    def structure_key(self) -> tuple:
        scene, cam = self.scene, self.scene.camera
        return (self.width(), self.height(), round(self.devicePixelRatioF(), 2), round(cam.x, 1), round(cam.y, 1),
                round(cam.zoom, 4), self._hover, scene.focus, scene.data_version, scene.activity, scene.panel_fraction)

    def _ensure_structure(self) -> QtGui.QPixmap:
        key = self.structure_key()
        if self._structure is not None and key == self._structure_key:
            return self._structure
        w, h, dpr = self.width(), self.height(), self.devicePixelRatioF()
        pix = self._structure
        if pix is None or pix.width() != int(w * dpr) or pix.height() != int(h * dpr):
            pix = QtGui.QPixmap(max(1, int(w * dpr)), max(1, int(h * dpr)))
            pix.setDevicePixelRatio(dpr)
        p = QtGui.QPainter(pix)
        self._paint_structure(p)
        p.end()
        self._structure, self._structure_key = pix, key
        self.structure_renders += 1
        return pix

    def _paint_structure(self, p: QtGui.QPainter) -> None:
        w, h = self.width(), self.height()
        p.drawPixmap(0, 0, self._ensure_background(w, h, self.devicePixelRatioF()))
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self._draw_ring_ellipses(p, float(w), float(h))
        self._draw_corridors(p, float(w), float(h))
        for region in self.scene.regions.values():
            self._draw_portal(p, region, float(w), float(h))
        self._draw_core_labels(p, float(w), float(h))
        self._draw_overlay(p, float(w), float(h))

    def _text(self, text: str, font: QtGui.QFont) -> QtGui.QStaticText:
        key = (text, font.pointSizeF(), font.weight(), font.letterSpacing())
        st = self._static.get(key)
        if st is None:
            if len(self._static) > 400:
                self._static.clear()
            st = QtGui.QStaticText(text)
            st.prepare(QtGui.QTransform(), font)
            self._static[key] = st
        return st

    def _centered(self, p: QtGui.QPainter, text: str, font: QtGui.QFont, color: QtGui.QColor, x: float, y: float) -> None:
        st = self._text(text, font)
        p.setFont(font)
        p.setPen(color)
        p.drawStaticText(QPointF(x - st.size().width() / 2, y), st)

    # ------------------------------------------------------------ pintura
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        started = time.perf_counter()
        scene = self.scene
        w, h = float(self.width()), float(self.height())
        if scene.camera.moving():
            # viagem da câmera: a estrutura muda a cada quadro — desenhada direto, sem a cópia extra
            p = QtGui.QPainter(self)
            self._paint_structure(p)
            self._structure_key = None
            self.structure_renders += 1
        else:
            structure = self._ensure_structure()
            p = QtGui.QPainter(self)
            p.drawPixmap(0, 0, structure)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        now = scene.clock()
        self._draw_ring_ticks(p, w, h)
        self._draw_energy(p, w, h, now)
        self._draw_particles(p, w, h)
        self._draw_core(p, w, h, now)
        self._draw_items(p, w, h)
        p.end()
        self.paint_count += 1
        self.frame_times.append(time.perf_counter() - started)

    # ---- estrutura (camada em cache)
    def _draw_ring_ellipses(self, p: QtGui.QPainter, w: float, h: float) -> None:
        scene = self.scene
        state = theme.state_color(scene.activity)
        cx, cy = scene.world_to_screen(0.0, 0.0, w, h, parallax=0.7)
        scale = scene.screen_scale(w, h, 0.7)
        p.setBrush(QtCore.Qt.NoBrush)
        for i, (radius, _speed, _ticks) in enumerate(RINGS):
            r = radius * scale
            p.setPen(_thin(theme.mix(theme.PRIMARY_DIM, state, 0.35), 0.28 - 0.035 * i))
            p.save()
            p.translate(cx, cy)
            p.scale(r, r)
            p.drawPath(self._ring_path)
            p.restore()

    def _world_transform(self, w: float, h: float) -> QtGui.QTransform:
        scene = self.scene
        cx, cy = scene.world_to_screen(0.0, 0.0, w, h)
        scale = scene.screen_scale(w, h)
        t = QtGui.QTransform()
        t.translate(cx, cy)
        t.scale(scale, scale)
        return t

    def _draw_corridors(self, p: QtGui.QPainter, w: float, h: float) -> None:
        scene = self.scene
        p.save()
        p.setTransform(self._world_transform(w, h), True)
        for key, path in self._corridors.items():
            region = scene.regions[key]
            alpha = 0.12 + (0.14 if key == self._hover or key == scene.focus else 0.0)
            p.setPen(_thin(theme.TONES.get(region.tone, theme.PRIMARY), alpha))
            p.drawPath(path)
        p.restore()

    def _draw_portal(self, p: QtGui.QPainter, region, w: float, h: float) -> None:
        scene = self.scene
        px, py = scene.world_to_screen(*region.pos, w, h)
        scale = scene.screen_scale(w, h) * region.scale
        r = 92 * scale
        hovered = self._hover == region.key
        focused = scene.focus == region.key
        base = theme.TONES.get(region.tone, theme.PRIMARY)
        energy = 0.35 if hovered or focused else 0.0
        dpr = self.devicePixelRatioF()
        p.setCompositionMode(PLUS)
        halo = theme.sprite_px("soft", "alert" if region.alert else region.tone, theme.quantize_radius(r * 1.5), dpr)
        p.setOpacity(min(1.0, 0.18 + 0.45 * energy))
        p.drawPixmap(QPointF(px - halo.width() / dpr / 2, py - halo.height() / dpr / 2), halo)
        p.setOpacity(1.0)
        p.setCompositionMode(OVER)
        # o vidro do portal: preenchimento sem antisserrilhado (a borda é coberta pelo traço) e traços
        # cosméticos de 1 px — o caminho rápido do QPainter (≈5× mais barato que um traço de 1,6 px)
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(theme.with_alpha(theme.BG2, 0.55))
        p.drawEllipse(QPointF(px, py), r, r * 0.62)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setBrush(QtCore.Qt.NoBrush)
        rim = theme.ALERT if region.alert else base
        for factor, alpha, color in ((1.0, 0.85, rim), (1.014, 0.35, rim), (0.82, 0.35, base)):
            p.setPen(_thin(color, min(1.0, alpha + 0.25 * energy)))
            p.drawEllipse(QPointF(px, py), r * factor, r * factor * 0.62)
        title_font = theme.font(9.5 if region.key not in SATELLITES else 8, weight=600, spacing=3)
        self._centered(p, region.label, title_font, theme.with_alpha(theme.TEXT_BRIGHT, 0.95 if hovered else 0.82),
                       px, py - 14)
        self._centered(p, str(region.count), theme.font(15 if region.key not in SATELLITES else 11, weight=300),
                       theme.with_alpha(theme.ALERT if region.alert else base, 0.95), px, py + 2)
        if region.detail and (hovered or focused or region.key not in SATELLITES):
            self._centered(p, region.detail[:46], theme.font(7, spacing=1),
                           theme.with_alpha(theme.TEXT_DIM, 0.9), px, py + r * 0.62 + 6)

    def _draw_core_labels(self, p: QtGui.QPainter, w: float, h: float) -> None:
        scene = self.scene
        cx, cy = scene.world_to_screen(0.0, 0.0, w, h)
        scale = scene.screen_scale(w, h)
        hovered = self._hover == CORE_KEY
        today = scene.today
        self._centered(p, "HOJE", theme.font(9 if not hovered else 10, weight=600, spacing=4),
                       theme.with_alpha(theme.TEXT_BRIGHT, 0.92), cx, cy + 62 * scale)
        if today:
            line = f"{today.get('priorities', 0)} prioridade(s) · {today.get('events', 0)} compromisso(s)"
            if today.get("overdue"):
                line += f" · {today['overdue']} atrasado(s)"
            self._centered(p, line, theme.font(7.5, spacing=1.5),
                           theme.with_alpha(theme.ALERT if today.get("overdue") else theme.TEXT_DIM, 0.9),
                           cx, cy + 62 * scale + 18)

    def _draw_overlay(self, p: QtGui.QPainter, w: float, h: float) -> None:
        p.setFont(theme.font(15, weight=600, spacing=8))
        p.setPen(theme.TEXT_BRIGHT)
        p.drawText(QPointF(26, 40), "JARVIS")
        p.setFont(theme.font(8, weight=600, spacing=5))
        p.setPen(theme.PRIMARY)
        p.drawText(QPointF(28, 58), "TARDIS · MEMÓRIA ESPACIAL")
        label = theme.state_label(self.scene.activity)
        p.setFont(theme.font(8, weight=600, spacing=3))
        p.setPen(theme.with_alpha(theme.state_color(self.scene.activity) if self.scene.activity != "IDLE"
                                  else theme.TEXT_DIM, 0.95))
        width = QtGui.QFontMetricsF(p.font()).horizontalAdvance(f"● {label}")
        p.drawText(QPointF(w * (1 - self.scene.panel_fraction) - width - 24, 40), f"● {label}")

    # ---- movimento (cada quadro)
    def _draw_ring_ticks(self, p: QtGui.QPainter, w: float, h: float) -> None:
        scene = self.scene
        cx, cy = scene.world_to_screen(0.0, 0.0, w, h, parallax=0.7)
        scale = scene.screen_scale(w, h, 0.7)
        p.setPen(_thin(theme.PRIMARY, 0.22))
        for (radius, speed, _ticks), path in zip(RINGS, self._tick_paths):
            r = radius * scale
            p.save()
            p.translate(cx, cy)
            p.scale(r, r * RING_RATIO)                  # elipse em perspectiva...
            p.rotate(math.degrees(scene.camera.orbit * speed * 10))   # ...girando no plano do anel
            p.drawPath(path)
            p.restore()

    def _draw_energy(self, p: QtGui.QPainter, w: float, h: float, now: float) -> None:
        """Corredores e portais acesos por eventos reais (o brilho decai) e pulsos em trânsito."""
        scene = self.scene
        lit = [region for region in scene.regions.values() if region.energy > 0.02]
        transform = self._world_transform(w, h)
        dpr = self.devicePixelRatioF()
        if lit:
            p.save()
            p.setTransform(transform, True)
            for region in lit:
                p.setPen(_thin(theme.TONES.get(region.tone, theme.PRIMARY), 0.35 * region.energy))
                p.drawPath(self._corridors[region.key])
            p.restore()
        p.setCompositionMode(PLUS)
        scale = scene.screen_scale(w, h)
        for region in lit:
            px, py = scene.world_to_screen(*region.pos, w, h)
            halo = theme.sprite_px("soft", "alert" if region.alert else region.tone,
                                   theme.quantize_radius(92 * scale * region.scale * 1.5), dpr)
            p.setOpacity(min(1.0, 0.45 * region.energy))
            p.drawPixmap(QPointF(px - halo.width() / dpr / 2, py - halo.height() / dpr / 2), halo)
        for pulse in scene.pulses:                               # dados reais percorrendo o corredor
            t = min(1.0, (now - pulse.born) / pulse.duration)
            t = 1.0 - t if pulse.inbound else t
            point = self._corridors[pulse.region].pointAtPercent(max(0.0, min(1.0, t)))
            sx, sy = transform.map(point.x(), point.y())
            pix = theme.sprite_px("glow", pulse.tone, 9, dpr)
            p.setOpacity(0.9 * (1.0 - abs(0.5 - t) * 0.6))
            p.drawPixmap(QPointF(sx - 9, sy - 9), pix)
        p.setOpacity(1.0)
        p.setCompositionMode(OVER)

    def _draw_particles(self, p: QtGui.QPainter, w: float, h: float) -> None:
        scene = self.scene
        if not scene.particles:
            return
        arr = np.array([(pt.angle, pt.radius, pt.height, pt.size) for pt in scene.particles], dtype=np.float32)
        scale = scene.screen_scale(w, h, 0.85)
        cx, cy = scene.world_to_screen(0.0, 0.0, w, h, parallax=0.85)
        xs = cx + np.cos(arr[:, 0]) * arr[:, 1] * scale
        ys = cy + (np.sin(arr[:, 0]) * arr[:, 1] * RING_RATIO + arr[:, 2] * 120) * scale
        near = np.clip(1.0 - arr[:, 1] / 760.0, 0.15, 1.0)
        dpr = self.devicePixelRatioF()
        p.setCompositionMode(PLUS)
        rgb = theme.PRIMARY.getRgb()[:3]
        levels = (near * 3).astype(np.int32).clip(0, 2)
        for level in (0, 1, 2):
            sel = levels == level
            if not sel.any():
                continue
            radius = (0.9, 1.3, 1.8)[level]
            size = theme.dot_size(radius)
            half = size // 2
            p.setOpacity((0.25, 0.45, 0.7)[level])
            fx, fy = xs[sel], ys[sel]
            ix, iy = np.floor(fx), np.floor(fy)
            sprites = [[theme.dot_px(rgb, radius, a, b, dpr) for b in range(4)] for a in range(4)]
            draw = p.drawPixmap
            for x, y, a, b in zip((ix - half).astype(np.int32).tolist(), (iy - half).astype(np.int32).tolist(),
                                  ((fx - ix) * 4).astype(np.int32).tolist(), ((fy - iy) * 4).astype(np.int32).tolist()):
                draw(x, y, sprites[a][b])
        p.setOpacity(1.0)
        p.setCompositionMode(OVER)

    def _draw_core(self, p: QtGui.QPainter, w: float, h: float, now: float) -> None:
        scene = self.scene
        cx, cy = scene.world_to_screen(0.0, 0.0, w, h)
        scale = scene.screen_scale(w, h)
        color = theme.state_color(scene.activity)
        glow = theme.state_glow(scene.activity) + 0.4 * scene.core_energy
        breathing = 0.5 + 0.5 * math.sin(now * (0.8 + glow))
        dpr = self.devicePixelRatioF()
        p.setCompositionMode(PLUS)
        tone = {"ERROR": "error", "RECOVERY": "alert"}.get(scene.activity, "cyan")
        halo = theme.sprite_px("soft", tone, theme.quantize_radius(150 * scale * (0.8 + 0.25 * glow)), dpr)
        p.setOpacity(0.55 + 0.3 * glow)
        p.drawPixmap(QPointF(cx - halo.width() / dpr / 2, cy - halo.height() / dpr / 2), halo)
        core = theme.sprite_px("glow", tone, theme.quantize_radius(46 * scale * (0.9 + 0.2 * breathing)), dpr)
        p.setOpacity(0.85)
        p.drawPixmap(QPointF(cx - core.width() / dpr / 2, cy - core.height() / dpr / 2), core)
        p.setOpacity(1.0)
        p.setCompositionMode(OVER)
        # rotor: anéis verticais que sobem e descem com a atividade (só desenho de linhas)
        p.setBrush(QtCore.Qt.NoBrush)
        for i in range(4):
            phase = (now * (0.35 + 0.5 * glow) + i * 0.25) % 1.0
            ry = (18 + 70 * phase) * scale
            rx = (58 - 30 * phase) * scale
            p.setPen(_thin(color if scene.activity != "IDLE" else theme.PRIMARY, 0.45 * (1 - phase)))
            p.drawEllipse(QPointF(cx, cy - ry * 0.6), rx, rx * 0.28)

    def _draw_items(self, p: QtGui.QPainter, w: float, h: float) -> None:
        """Registros reais orbitando cada portal (posição estável por índice, giro lento)."""
        scene = self.scene
        dpr = self.devicePixelRatioF()
        for region in scene.regions.values():
            base = theme.TONES.get(region.tone, theme.PRIMARY)
            for i, item in enumerate(region.items):
                ix, iy = scene.item_position(region, i, w, h)
                tone = "alert" if item.get("overdue") else ("dim" if item.get("status") in ("done", "cancelled") else
                                                            ("ice" if not item.get("confirmed", True) else region.tone))
                radius = 1.6 + 0.55 * int(item.get("priority", 2))
                rgb = theme.TONES.get(tone, base).getRgb()[:3]
                size = theme.dot_size(radius)
                p.drawPixmap(int(ix) - size // 2, int(iy) - size // 2, theme.dot_px(rgb, radius, 0, 0, dpr))

    # ------------------------------------------------------------ interação
    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt)
        pos = event.position()
        hit = self.scene.hit(pos.x(), pos.y(), self.width(), self.height())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(QtCore.Qt.PointingHandCursor if hit else QtCore.Qt.ArrowCursor)
            self.update()
        item = self.scene.item_at(pos.x(), pos.y(), self.width(), self.height())
        if item is not None:
            kind = KINDS.get(item.get("kind"), "Lembrete" if item.get("kind") == "reminder" else "Registro")
            QtWidgets.QToolTip.showText(event.globalPosition().toPoint(), f"{kind}: {item['title']}", self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._hover = None
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() == QtCore.Qt.LeftButton:
            pos = event.position()
            self.region_clicked.emit(self.scene.hit(pos.x(), pos.y(), self.width(), self.height()) or "")
        super().mousePressEvent(event)


class TardisWindow(PageHost):
    return_requested = QtCore.Signal()

    def __init__(self, core, *, state: dict | None = None, profile=None):
        super().__init__(core, state=state, profile=profile)
        self.setObjectName("Panel")
        self.setWindowTitle("JARVIS — TARDIS")
        self.setWindowIcon(app_icon())
        self.resize(1360, 840)
        self.setMinimumSize(980, 600)
        self.profile = profile or quality.get("balanced")
        self.scene = TardisScene(max_particles=self._particle_budget())
        self.scene.set_activity(str(self.state.get("activity") or "IDLE"))
        self.view = TardisView(self.scene)
        self.view.region_clicked.connect(self.open_region)
        # páginas por região (as mesmas do Second Brain, agora dentro do espaço)
        pages = {CORE_PAGE: TodayPage(self), "timeline": TimelinePage(self), "tasks": TasksPage(self),
                 "projects": ProjectsPage(self), "ideas": IdeasPage(self), "search": SearchPage(self),
                 "notifications": NotificationsPage(self), "review": ReviewPage(self)}
        self.side = QtWidgets.QFrame()
        self.side.setObjectName("Panel")
        side_layout = QtWidgets.QVBoxLayout(self.side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(16, 10, 12, 0)
        self.side_title = _label("", "PanelTitle")
        overview = _button("VISÃO GERAL", "Fechar a região e voltar à visão geral do espaço")
        overview.clicked.connect(lambda: self.open_region(""))
        head.addWidget(self.side_title, 1)
        head.addWidget(overview)
        side_layout.addLayout(head)
        self.stack = QtWidgets.QStackedWidget()
        for page in pages.values():
            self.add_page(page)
            self.stack.addWidget(page)
        side_layout.addWidget(self.stack, 1)
        self.side.setMaximumWidth(0)
        self._side_anim = QtCore.QPropertyAnimation(self.side, b"maximumWidth", self)
        self._side_anim.setDuration(320)
        self._side_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._region: str | None = None
        # barra superior sobre o espaço
        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(20, 12, 20, 0)
        back = _button("← JARVIS CORE", "Voltar ao HUB principal (o TARDIS fica como está)", primary=True)
        back.clicked.connect(self.return_requested)
        self.back_button = back                     # na plataforma, volta para a sala de controle
        self.sound = _button("SOM AMBIENTE", "Som ambiente discreto do TARDIS")
        self.sound.setCheckable(True)
        self.sound.setChecked(bool(getattr(core.settings(), "ambient_sound", False)))
        self.sound.toggled.connect(self._toggle_sound)
        export = _button("EXPORTAR", "Exportar a memória pessoal para um arquivo novo (JSON completo ou CSV/planilha)")
        export_menu = QtWidgets.QMenu(export)
        export_menu.addAction("JSON (completo)", lambda: self._export("json"))
        export_menu.addAction("CSV (planilha)", lambda: self._export("csv"))
        export.setMenu(export_menu)
        backup = _button("BACKUP", "Cópia de segurança do banco do JARVIS agora (memórias, lembretes, rede)")
        backup.clicked.connect(lambda: self.run_action("Backup do banco", "memory.backup", {}))
        top.addStretch(1)
        top.addWidget(export)
        top.addWidget(backup)
        top.addWidget(self.sound)
        top.addWidget(back)
        # captura rápida (mesma camada de serviço de voz e texto)
        self.capture = QtWidgets.QLineEdit()
        self.capture.setObjectName("HudLine")
        self.capture.setPlaceholderText("Anotar ou perguntar: \"reunião com a equipe quarta às 14h\", \"ideia: …\", "
                                        "\"o que está atrasado?\"")
        self.capture.returnPressed.connect(self._capture)
        self.capture_kind = QtWidgets.QComboBox()
        self.capture_kind.addItem("Automático", "")
        for key, label in KINDS.items():
            self.capture_kind.addItem(label, key)
        send = _button("REGISTRAR", primary=True)
        send.clicked.connect(self._capture)
        bottom = QtWidgets.QHBoxLayout()
        bottom.setContentsMargins(20, 6, 20, 4)
        bottom.addWidget(self.capture, 1)
        bottom.addWidget(self.capture_kind)
        bottom.addWidget(send)
        space = QtWidgets.QWidget()
        space_layout = QtWidgets.QVBoxLayout(space)
        space_layout.setContentsMargins(0, 0, 0, 0)
        space_layout.setSpacing(0)
        space_layout.addLayout(top)
        space_layout.addWidget(self.view, 1)
        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(space, 1)
        body.addWidget(self.side)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(0)
        root.addLayout(body, 1)
        root.addWidget(self.authorization)
        root.addLayout(bottom)
        root.addWidget(self.feedback)
        self.feedback.setContentsMargins(22, 0, 22, 0)
        self.dirty.add("tardis")
        self._clock = QtCore.QTimer(self)
        self._clock.setTimerType(QtCore.Qt.PreciseTimer)
        self._clock.timeout.connect(self._tick)
        self._last_tick = time.perf_counter()
        self._paint_ema = 0.0
        self._painted = 0
        self.target_fps = 0
        QtGui.QShortcut(QtGui.QKeySequence("Esc"), self, activated=lambda: self.open_region(""))
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+N"), self, activated=self.focus_capture)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), self, activated=lambda: self.open_region("memories"))
        self.present_authorization(self.state.get("pending_authorization"))

    # ------------------------------------------------------------ regiões
    def _particle_budget(self) -> int:
        return int(getattr(self.profile, "max_particles", 120))

    def open_region(self, key: str) -> None:
        """Viaja até a região e abre o painel dela; vazio = visão geral (painel fechado)."""
        if not key:
            self._region = None
            self.scene.focus_region(None)
            self._animate_side(False)
            return
        page_key = CORE_PAGE if key == CORE_KEY else REGIONS[key][3]
        self._region = key
        self.scene.focus_region(key)
        page = self.pages[page_key]
        self.stack.setCurrentWidget(page)
        self.side_title.setText(REGION_LABEL.get(key, key))
        self._animate_side(True)
        self.ensure_loaded(page_key)
        self._wake_clock()

    def _animate_side(self, opening: bool) -> None:
        target = int(self.width() * PANEL_FRACTION) if opening else 0
        self._side_anim.stop()
        self._side_anim.setStartValue(self.side.maximumWidth())
        self._side_anim.setEndValue(target)
        self._side_anim.start()
        # o painel ocupa espaço real no layout: a vista encolhe e a câmera recentraliza sozinha
        self.scene.panel_fraction = 0.0

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self._region is not None and self._side_anim.state() != QtCore.QAbstractAnimation.Running:
            self.side.setMaximumWidth(int(self.width() * PANEL_FRACTION))
        super().resizeEvent(event)

    def visible_keys(self) -> set[str]:
        keys = {"tardis"}
        if self._region is not None:
            keys.add(CORE_PAGE if self._region == CORE_KEY else REGIONS[self._region][3])
        return keys

    def show_section(self, section: str | None) -> None:
        mapping = {"today": CORE_KEY, "timeline": "agenda", "tasks": "tasks", "projects": "projects",
                   "ideas": "ideas", "search": "memories", "notifications": "reminders", "review": "review"}
        if section in mapping:
            self.open_region(mapping[section])
        elif section in REGIONS or section == CORE_KEY:
            self.open_region(section)

    def focus_capture(self) -> None:
        self.capture.setFocus()

    # ------------------------------------------------------------ dados
    def reload(self, key: str, **kwargs) -> None:
        if key == "tardis":
            if self._closed:
                return
            self.dirty.discard("tardis")
            service = self.core.second_brain
            self.reader.request("tardis", lambda: fetch_regions(service))
            return
        super().reload(key, **kwargs)

    @QtCore.Slot(str, int, object)
    def _loaded(self, key: str, generation: int, data) -> None:
        if key == "tardis":
            if self._closed or not self.reader.current(key, generation):
                return
            if isinstance(data, Exception):
                self.feedback.setText(f"Falha ao ler a memória: {data}")
                return
            self.loaded_once.add("tardis")
            self.scene.apply_data(data)
            self.view.update()
            return
        super()._loaded(key, generation, data)

    def on_event(self, kind: str, payload: dict) -> None:
        super().on_event(kind, payload)
        if kind in ("RECORD_CREATED", "RECORD_UPDATED", "RECORD_DELETED", "RECORD_RESTORED", "REMINDER_DUE",
                    "REMINDER_SNOOZED", "NOTIFICATION"):
            self.scene.on_event(kind, payload)
            self.dirty.add("tardis")
            if self.isVisible():
                self._reload_timer.start()
                self._wake_clock()

    def on_state(self, state: dict, names) -> None:
        super().on_state(state, names)
        if "activity" in set(names or ()):
            self.scene.set_activity(str(state.get("activity") or "IDLE"))
            self._wake_clock()

    def on_profile(self, profile) -> None:
        super().on_profile(profile)
        self.scene.set_particle_budget(self._particle_budget())

    # ------------------------------------------------------------ relógio adaptativo
    def _wake_clock(self) -> None:
        if self.isVisible() and not self.isMinimized() and not self._clock.isActive():
            self._last_tick = time.perf_counter()
            self._clock.start(16)

    def _tick(self) -> None:
        if not self.isVisible() or self.isMinimized():
            self._clock.stop()                       # oculto ou minimizado: nenhum quadro
            return
        now = time.perf_counter()
        dt, self._last_tick = now - self._last_tick, now
        self.scene.step(dt)
        if self.view.paint_count != self._painted and self.view.frame_times:
            self._painted = self.view.paint_count
            last = self.view.frame_times[-1]
            self._paint_ema = last if not self._paint_ema else self._paint_ema * 0.85 + last * 0.15
        hud_fps = int(getattr(self.core.settings(), "hud_fps", 60))
        fps = quality.effective_fps(self.profile, hud_fps, active=self.scene.in_motion(),
                                    background=self._core_in_front())
        if self._paint_ema > 0:
            fps = min(fps, max(self.profile.idle_fps, int(PAINT_BUDGET / self._paint_ema)))
        self.target_fps = fps
        interval = max(7, int(1000 / fps))
        if self._clock.interval() != interval:
            self._clock.setInterval(interval)
        self.view.update()

    def _core_in_front(self) -> bool:
        """Outra janela do JARVIS (o CORE) está em foco e o TARDIS ficou atrás: cadência de fundo.
        Com o foco em outro programa, o TARDIS mantém a cadência normal de repouso."""
        active = QtWidgets.QApplication.activeWindow()
        return active is not None and active is not self.window() and not self.isActiveWindow()

    # ------------------------------------------------------------ captura e som
    def _capture(self) -> None:
        text = " ".join(self.capture.text().split())
        if not text:
            return
        self.capture.clear()
        kind = self.capture_kind.currentData()
        from ..secondbrain import queries
        found = queries.classify(text)
        if not kind and (text.endswith("?") or (found is not None and found[0] != "search")):
            self.pages["search"].query.setText(text)
            self.open_region("memories")
            return
        args = {"text": text}
        if kind:
            args["kind"] = kind
        self.run_action(f"Registrar: {text[:40]}", "secondbrain.capture", args)

    def _export(self, fmt: str) -> None:
        import time
        from pathlib import Path
        suggested = str(Path.home() / f"jarvis-memoria-{time.strftime('%Y%m%d')}.{fmt}")
        filters = "JSON (*.json)" if fmt == "json" else "CSV (*.csv)"
        # nunca sobrescreve: se o arquivo existir, a exportação recusa e pede outro nome
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar memória pessoal", suggested, filters,
                                                        options=QtWidgets.QFileDialog.DontConfirmOverwrite)
        if path:
            self.run_action(f"Exportar ({fmt.upper()})", "secondbrain.export", {"format": fmt, "path": path})

    def _toggle_sound(self, on: bool) -> None:
        try:
            self.core.settings_manager.update(ambient_sound=bool(on))
        except Exception:
            pass
        self._apply_sound(self.isVisible())

    def _apply_sound(self, visible: bool) -> None:
        audio = getattr(self.core, "neural_audio", None)
        if audio is not None and hasattr(audio, "set_ambient"):
            audio.set_ambient(bool(visible and self.sound.isChecked()))

    # ------------------------------------------------------------ ciclo de vida
    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self.ensure_loaded("tardis")
        for key in self.visible_keys() - {"tardis"}:
            self.ensure_loaded(key)
        self._apply_sound(True)
        self._wake_clock()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._clock.stop()
        self._apply_sound(False)
        super().hideEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.type() == QtCore.QEvent.WindowStateChange:
            if self.isMinimized():
                self._clock.stop()
                self._apply_sound(False)
            else:
                self._apply_sound(self.isVisible())
                self._wake_clock()
        super().changeEvent(event)

    def shutdown(self) -> None:
        self._clock.stop()
        self._apply_sound(False)
        super().shutdown()
