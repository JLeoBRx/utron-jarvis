"""Geometria procedural do cérebro do ULTRON (numpy, sem Qt).

Vista lateral (lobo frontal à esquerda). Coordenadas normalizadas: x em [-1, 1],
y em [-0,75, 0,8] com y para baixo, como na tela.

* contorno do cérebro e do cerebelo (Catmull-Rom sobre pontos de controle);
* giros e sulcos: isolinhas de um ruído fractal com distorção de domínio, recortadas à
  máscara do córtex (marching squares) — o desenho de dobras sinuosas típico do córtex;
* fissuras principais (lateral e central) e estruturas internas (hipocampo, tálamo,
  corpo caloso) reveladas pela profundidade cognitiva;
* regiões funcionais, onde cada tipo de nó do Neural Graph é posicionado de forma
  determinística (o mesmo nó sempre ocupa o mesmo lugar).

O cérebro "cresce" com o grafo: ``development`` (0..1) controla quantas dobras são
desenhadas e com que intensidade.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

CEREBRUM = [(-0.98, 0.05), (-0.93, -0.28), (-0.74, -0.53), (-0.40, -0.68), (0.02, -0.72), (0.42, -0.65),
            (0.76, -0.45), (0.95, -0.15), (0.99, 0.08), (0.88, 0.25), (0.62, 0.30), (0.36, 0.40), (0.05, 0.47),
            (-0.26, 0.42), (-0.40, 0.29), (-0.47, 0.19), (-0.64, 0.24), (-0.87, 0.21)]
CEREBELLUM = [(0.36, 0.38), (0.55, 0.31), (0.78, 0.30), (0.93, 0.38), (0.92, 0.50), (0.78, 0.60), (0.56, 0.62),
              (0.40, 0.55)]
BRAINSTEM = [(0.24, 0.40), (0.38, 0.42), (0.40, 0.58), (0.37, 0.80), (0.27, 0.80), (0.25, 0.58)]
SYLVIAN = [(-0.47, 0.19), (-0.25, 0.10), (0.05, 0.03), (0.30, -0.03), (0.46, -0.12)]
CENTRAL = [(0.10, -0.71), (0.05, -0.50), (-0.02, -0.30), (-0.08, -0.10), (-0.12, 0.06)]
HIPPOCAMPUS = [(-0.30, 0.27), (-0.12, 0.31), (0.08, 0.30), (0.24, 0.24), (0.32, 0.14), (0.28, 0.08)]
THALAMUS = (0.12, -0.02, 0.14, 0.08)                 # cx, cy, rx, ry
CALLOSUM = [(-0.52, -0.08), (-0.40, -0.26), (-0.10, -0.36), (0.25, -0.33), (0.48, -0.18), (0.50, -0.06)]

# região funcional → (cx, cy, raio)
REGIONS: dict[str, tuple[float, float, float]] = {
    "prefrontal": (-0.74, -0.18, 0.20),
    "frontal": (-0.45, -0.42, 0.22),
    "motor": (-0.04, -0.45, 0.17),
    "broca": (-0.50, 0.04, 0.12),
    "parietal": (0.40, -0.42, 0.22),
    "occipital": (0.80, -0.05, 0.16),
    "temporal": (-0.05, 0.28, 0.20),
    "auditory": (0.10, 0.12, 0.12),
    "hippocampus": (0.05, 0.27, 0.13),
    "cerebellum": (0.66, 0.46, 0.20),
    "core": (0.12, -0.04, 0.10),
}

# tipo de nó do grafo → regiões onde ele vive
TYPE_REGIONS: dict[str, tuple[str, ...]] = {
    "MEMORY": ("hippocampus", "temporal"),
    "IDEA": ("prefrontal", "frontal"),
    "CONCEPT": ("prefrontal", "frontal", "parietal"),
    "SKILL": ("motor", "cerebellum"),
    "PROJECT": ("frontal", "prefrontal"),
    "WORLD": ("occipital", "parietal"),
    "SCENARIO": ("prefrontal", "occipital"),
    "DEVICE": ("parietal",),
    "APPLICATION": ("occipital", "parietal"),
}


# ---------------------------------------------------------------- curvas
def catmull_rom(points: list[tuple[float, float]], *, closed: bool, samples: int = 16) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64)
    if closed:
        ext = np.vstack([pts[-1], pts, pts[0], pts[1]])
    else:
        ext = np.vstack([pts[0], pts, pts[-1]])
    out = []
    t = np.linspace(0.0, 1.0, samples, endpoint=False)[:, None]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        a = 2 * p1
        b = p2 - p0
        c = 2 * p0 - 5 * p1 + 4 * p2 - p3
        d = -p0 + 3 * p1 - 3 * p2 + p3
        out.append(0.5 * (a + b * t + c * t ** 2 + d * t ** 3))
    curve = np.vstack(out)
    if not closed:
        curve = np.vstack([curve, pts[-1]])
    return curve


def point_in_polygon(x: np.ndarray, y: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Teste vetorizado (regra par-ímpar)."""
    inside = np.zeros(np.broadcast(x, y).shape, dtype=bool)
    px, py = poly[:, 0], poly[:, 1]
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi, xj, yj = px[i], py[i], px[j], py[j]
        cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi)
        inside ^= cond
        j = i
    return inside


# ---------------------------------------------------------------- ruído
def _value_noise(shape: tuple[int, int], cells: int, rng: np.random.Generator) -> np.ndarray:
    h, w = shape
    grid = rng.random((cells + 2, int(cells * w / h) + 3))
    ys = np.linspace(0, cells, h, endpoint=False)
    xs = np.linspace(0, grid.shape[1] - 3, w, endpoint=False)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = ys - y0, xs - x0
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    a = grid[y0][:, x0]
    b = grid[y0][:, x0 + 1]
    c = grid[y0 + 1][:, x0]
    d = grid[y0 + 1][:, x0 + 1]
    top = a + (b - a) * fx[None, :]
    bottom = c + (d - c) * fx[None, :]
    return top + (bottom - top) * fy[:, None]


def fbm(shape: tuple[int, int], rng: np.random.Generator, *, base: int = 5, octaves: int = 4) -> np.ndarray:
    total = np.zeros(shape)
    amp, norm = 1.0, 0.0
    for octave in range(octaves):
        total += amp * _value_noise(shape, base * 2 ** octave, rng)
        norm += amp
        amp *= 0.5
    return total / norm


def _sample(field_: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    h, w = field_.shape
    xi = np.clip(xs, 0, w - 1.001)
    yi = np.clip(ys, 0, h - 1.001)
    x0, y0 = xi.astype(int), yi.astype(int)
    fx, fy = xi - x0, yi - y0
    a = field_[y0, x0]
    b = field_[y0, x0 + 1]
    c = field_[y0 + 1, x0]
    d = field_[y0 + 1, x0 + 1]
    return (a + (b - a) * fx) + ((c + (d - c) * fx) - (a + (b - a) * fx)) * fy


# ---------------------------------------------------------------- marching squares
def contour_segments(field_: np.ndarray, level: float) -> np.ndarray:
    """Segmentos (N, 4) da isolinha ``level`` em coordenadas de grade (x0, y0, x1, y1)."""
    v = field_
    tl, tr, br, bl = v[:-1, :-1], v[:-1, 1:], v[1:, 1:], v[1:, :-1]
    case = ((tl > level).astype(np.uint8) * 8 + (tr > level) * 4 + (br > level) * 2 + (bl > level) * 1)
    ys, xs = np.nonzero((case != 0) & (case != 15))
    if len(xs) == 0:
        return np.zeros((0, 4))

    def lerp(a, b):
        return np.clip((level - a) / np.where(np.abs(b - a) < 1e-12, 1e-12, b - a), 0, 1)

    a_tl, a_tr, a_br, a_bl = tl[ys, xs], tr[ys, xs], br[ys, xs], bl[ys, xs]
    top = np.stack([xs + lerp(a_tl, a_tr), ys], 1)
    right = np.stack([xs + 1, ys + lerp(a_tr, a_br)], 1)
    bottom = np.stack([xs + lerp(a_bl, a_br), ys + 1], 1)
    left = np.stack([xs, ys + lerp(a_tl, a_bl)], 1)
    edges = {1: [(left, bottom)], 2: [(bottom, right)], 3: [(left, right)], 4: [(top, right)],
             5: [(left, top), (bottom, right)], 6: [(top, bottom)], 7: [(left, top)], 8: [(left, top)],
             9: [(top, bottom)], 10: [(left, bottom), (top, right)], 11: [(top, right)], 12: [(left, right)],
             13: [(bottom, right)], 14: [(left, bottom)]}
    segments = []
    cases = case[ys, xs]
    for value, pairs in edges.items():
        idx = np.nonzero(cases == value)[0]
        if len(idx) == 0:
            continue
        for p, q in pairs:
            segments.append(np.hstack([p[idx], q[idx]]))
    return np.vstack(segments) if segments else np.zeros((0, 4))


def chain_segments(segments: np.ndarray, *, decimals: int = 4) -> list[np.ndarray]:
    """Une segmentos que compartilham extremidades em polilinhas (desenho mais suave)."""
    if len(segments) == 0:
        return []
    key = lambda x, y: (round(float(x), decimals), round(float(y), decimals))  # noqa: E731
    adjacency: dict[tuple, list[int]] = {}
    for i, (x0, y0, x1, y1) in enumerate(segments):
        adjacency.setdefault(key(x0, y0), []).append(i)
        adjacency.setdefault(key(x1, y1), []).append(i)
    used = np.zeros(len(segments), dtype=bool)
    lines = []
    for start in range(len(segments)):
        if used[start]:
            continue
        used[start] = True
        x0, y0, x1, y1 = segments[start]
        line = [(x0, y0), (x1, y1)]
        for forward in (True, False):
            while True:
                end = line[-1] if forward else line[0]
                nxt = None
                for j in adjacency.get(key(*end), ()):
                    if not used[j]:
                        nxt = j
                        break
                if nxt is None:
                    break
                used[nxt] = True
                a0, b0, a1, b1 = segments[nxt]
                point = (a1, b1) if key(a0, b0) == key(*end) else (a0, b0)
                if forward:
                    line.append(point)
                else:
                    line.insert(0, point)
        lines.append(np.asarray(line))
    return lines


# ---------------------------------------------------------------- modelo
@dataclass
class Fold:
    points: np.ndarray            # polilinha em coordenadas normalizadas
    level: int                    # índice da isolinha (0 = principal)
    depth: float                  # 0..1: proximidade da borda (para sombreamento)
    length: float = 0.0


@dataclass
class BrainGeometry:
    seed: int = 7
    resolution: int = 150
    cerebrum: np.ndarray = field(init=False)
    cerebellum: np.ndarray = field(init=False)
    brainstem: np.ndarray = field(init=False)
    folds: list = field(init=False)
    cerebellum_folds: list = field(init=False)
    fissures: dict = field(init=False)
    inner: dict = field(init=False)

    def __post_init__(self):
        self.cerebrum = catmull_rom(CEREBRUM, closed=True, samples=20)
        self.cerebellum = catmull_rom(CEREBELLUM, closed=True, samples=14)
        self.brainstem = catmull_rom(BRAINSTEM, closed=True, samples=10)
        self.fissures = {"lateral": catmull_rom(SYLVIAN, closed=False, samples=14),
                         "central": catmull_rom(CENTRAL, closed=False, samples=14)}
        theta = np.linspace(0, 2 * np.pi, 60)
        cx, cy, rx, ry = THALAMUS
        self.inner = {"hippocampus": catmull_rom(HIPPOCAMPUS, closed=False, samples=12),
                      "thalamus": np.stack([cx + rx * np.cos(theta), cy + ry * np.sin(theta)], 1),
                      "callosum": catmull_rom(CALLOSUM, closed=False, samples=14)}
        self.folds = self._folds()
        self.cerebellum_folds = self._cerebellum_folds()

    # grade normalizada → coordenadas do cérebro
    def _grid(self, x0: float, x1: float, y0: float, y1: float, res: int):
        h = int(res * (y1 - y0) / (x1 - x0))
        xs = np.linspace(x0, x1, res)
        ys = np.linspace(y0, y1, h)
        return np.meshgrid(xs, ys), (x0, x1, y0, y1, res, h)

    def _to_norm(self, pts: np.ndarray, frame) -> np.ndarray:
        x0, x1, y0, y1, w, h = frame
        out = np.empty_like(pts, dtype=np.float64)
        out[:, 0] = x0 + pts[:, 0] / (w - 1) * (x1 - x0)
        out[:, 1] = y0 + pts[:, 1] / (h - 1) * (y1 - y0)
        return out

    def _folds(self) -> list[Fold]:
        rng = np.random.default_rng(self.seed)
        (gx, gy), frame = self._grid(-1.05, 1.05, -0.80, 0.55, self.resolution)
        shape = gx.shape
        warp_x = fbm(shape, rng, base=3, octaves=3)
        warp_y = fbm(shape, rng, base=3, octaves=3)
        base = fbm(shape, rng, base=6, octaves=4)
        h, w = shape
        ii, jj = np.mgrid[0:h, 0:w].astype(np.float64)
        warped = _sample(base, jj + (warp_x - 0.5) * w * 0.18, ii + (warp_y - 0.5) * h * 0.18)
        # alongamento horizontal suave: giros tendem a correr ao longo do hemisfério
        stretch = 0.5 + 0.5 * np.sin(gx * 2.2 + gy * 5.0 + warped * 6.0)
        field_ = 0.65 * warped + 0.35 * stretch
        inside = point_in_polygon(gx, gy, self.cerebrum)
        # distância aproximada à borda (para sombreamento e para não desenhar fora)
        edge = self._edge_distance(gx, gy)
        field_ = np.where(inside, field_, np.nan)
        folds: list[Fold] = []
        levels = np.linspace(0.30, 0.70, 9)
        for level_index, level in enumerate(levels):
            segs = contour_segments(np.nan_to_num(field_, nan=-1.0), level)
            if len(segs) == 0:
                continue
            for line in chain_segments(segs):
                pts = self._to_norm(line, frame)
                mid = pts[len(pts) // 2]
                if not point_in_polygon(np.array(mid[0]), np.array(mid[1]), self.cerebrum):
                    continue
                if len(pts) < 4:
                    continue
                length = float(np.sum(np.hypot(*np.diff(pts, axis=0).T)))
                d = float(_sample(edge, np.array([(mid[0] - frame[0]) / (frame[1] - frame[0]) * (w - 1)]),
                                  np.array([(mid[1] - frame[2]) / (frame[3] - frame[2]) * (h - 1)]))[0])
                folds.append(Fold(pts, level_index, min(1.0, d / 0.25), length))
        # ordem de importância: dobras centrais e longas primeiro (as primeiras a "crescer")
        folds.sort(key=lambda f: (abs(f.level - 4), -f.length))
        return folds

    def _edge_distance(self, gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
        poly = self.cerebrum[::3]
        d = np.full(gx.shape, 9.0)
        for (x0, y0), (x1, y1) in zip(poly, np.roll(poly, -1, axis=0)):
            dx, dy = x1 - x0, y1 - y0
            t = np.clip(((gx - x0) * dx + (gy - y0) * dy) / (dx * dx + dy * dy + 1e-12), 0, 1)
            d = np.minimum(d, np.hypot(gx - (x0 + t * dx), gy - (y0 + t * dy)))
        return d

    def _cerebellum_folds(self) -> list[np.ndarray]:
        lines = []
        cx, cy = 0.64, 0.46
        for k in range(9):
            r = 0.05 + k * 0.032
            theta = np.linspace(-0.15 * np.pi, 1.10 * np.pi, 80)
            pts = np.stack([cx + 1.45 * r * np.cos(theta), cy - 0.02 + 0.55 * r * np.sin(theta) * -1], 1)
            pts[:, 1] += 0.006 * np.sin(theta * (9 + k))
            mask = point_in_polygon(pts[:, 0], pts[:, 1], self.cerebellum)
            run = []
            for p, ok in zip(pts, mask):
                if ok:
                    run.append(p)
                elif len(run) > 3:
                    lines.append(np.asarray(run))
                    run = []
                else:
                    run = []
            if len(run) > 3:
                lines.append(np.asarray(run))
        return lines

    # ------------------------------------------------------------ crescimento
    def visible_folds(self, development: float) -> list[Fold]:
        development = max(0.0, min(1.0, development))
        count = int(len(self.folds) * (0.18 + 0.82 * development))
        return self.folds[:count]

    # ------------------------------------------------------------ posicionamento de nós
    def inside(self, x: float, y: float) -> bool:
        return bool(point_in_polygon(np.array(x), np.array(y), self.cerebrum)) or \
            bool(point_in_polygon(np.array(x), np.array(y), self.cerebellum))

    def place(self, node_id: str, node_type: str) -> tuple[float, float]:
        digest = hashlib.sha1(node_id.encode("utf-8")).digest()
        regions = TYPE_REGIONS.get(node_type, ("core", "parietal", "frontal"))
        region = regions[digest[0] % len(regions)]
        cx, cy, radius = REGIONS[region]
        for attempt in range(12):
            a = (digest[(1 + attempt) % 20] / 255.0) * 2 * math.pi
            r = radius * math.sqrt(digest[(2 + attempt) % 20] / 255.0)
            x, y = cx + r * math.cos(a) * 1.25, cy + r * math.sin(a) * 0.9
            if self.inside(x, y):
                return x, y
        return cx, cy


def development_for(nodes: int, edges: int) -> float:
    """0..1: quanto o cérebro já cresceu (escala logarítmica do tamanho do grafo)."""
    size = nodes + 0.5 * edges
    return max(0.0, min(1.0, math.log10(1 + size) / math.log10(1 + 1500)))
