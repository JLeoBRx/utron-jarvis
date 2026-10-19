"""Malha neural 3D do cérebro do JARVIS (numpy, sem Qt).

Cérebro de nós e sinapses: uma casca com giros e fissura longitudinal entre os
hemisférios, lobos temporais, cerebelo e tronco; cada ponto ligado aos vizinhos mais
próximos. A malha gira em perspectiva; pontos à frente são maiores e mais brilhantes.

* a densidade da malha **cresce com o Neural Graph real** (``development``): um JARVIS
  novo tem uma rede esparsa; com o uso, ela se adensa;
* os nós do grafo ocupam posições fixas na região do seu tipo (memórias no hipocampo e
  lobo temporal, ideias no pré-frontal, skills no córtex motor e cerebelo...);
* regiões funcionais permitem acender a parte certa do cérebro para cada evento real.

Coordenadas: ``x`` frente (−) / trás (+); ``y`` cima (−) / baixo (+), como na tela;
``z`` hemisfério esquerdo (−) / direito (+). Ângulo 0 = vista lateral direita.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

MAX_POINTS = 640
MIN_VISIBLE = 260
GROWTH_STEP = 20
STRETCH = 1.18                 # alongamento horizontal da projeção (o cérebro é mais largo que alto)
PERSPECTIVE = 0.22
TILT = -0.16                   # leve inclinação: vemos um pouco do topo

# região → (x, y, z lateral, raio). Regiões com z > 0 existem nos dois hemisférios.
REGIONS: dict[str, tuple[float, float, float, float]] = {
    "prefrontal": (-0.80, -0.10, 0.34, 0.30),
    "frontal": (-0.45, -0.52, 0.40, 0.32),
    "motor": (-0.05, -0.66, 0.40, 0.28),
    "broca": (-0.52, 0.10, 0.62, 0.22),
    "parietal": (0.40, -0.55, 0.44, 0.32),
    "occipital": (0.86, -0.10, 0.34, 0.28),
    "temporal": (-0.12, 0.30, 0.66, 0.32),
    "auditory": (0.06, 0.10, 0.72, 0.22),
    "hippocampus": (0.05, 0.20, 0.28, 0.22),
    "cerebellum": (0.56, 0.62, 0.0, 0.28),
    "core": (0.0, 0.0, 0.0, 0.18),
}
LEFT_ONLY = {"broca"}          # área da linguagem: hemisfério esquerdo

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


def development_for(nodes: int, edges: int) -> float:
    """0..1: quanto o cérebro já cresceu (escala logarítmica do tamanho do grafo)."""
    size = nodes + 0.5 * edges
    return max(0.0, min(1.0, math.log10(1 + size) / math.log10(1 + 1500)))


def _shell(rng: np.random.Generator, n: int) -> np.ndarray:
    """Casca cerebral: esfera deformada com giros, base achatada e fissura longitudinal."""
    theta = rng.uniform(0, 2 * np.pi, n)
    phi = np.arccos(rng.uniform(-0.72, 1.0, n))
    gyri = 1 + 0.10 * np.sin(5 * theta + 3 * phi) * np.sin(4 * phi) + 0.035 * np.sin(11 * theta - 7 * phi)
    x = np.sin(phi) * np.cos(theta)
    y = -np.cos(phi) * 0.78
    z = np.sin(phi) * np.sin(theta) * 0.80
    back = x > 0                                          # occipital mais estreito e baixo que o frontal
    x = np.where(back, x * 1.04, x)
    y = np.where(back, y * (1 - 0.10 * x), y)
    z = np.where(back, z * (1 - 0.12 * x), z)
    z = np.where(np.abs(z) < 0.07, np.where(z >= 0, z + 0.10, z - 0.10), z)   # fissura entre hemisférios
    return np.stack([x * gyri, y * gyri, z * gyri], axis=1)


def _spread_order(points: np.ndarray, start: int) -> np.ndarray:
    """Ordem de amostragem pelo ponto mais distante: qualquer prefixo cobre a forma inteira de
    modo uniforme (um cérebro jovem é esparso, mas já tem a silhueta completa)."""
    n = len(points)
    order = np.empty(n, dtype=np.int64)
    nearest = np.full(n, np.inf)
    current = start
    for k in range(n):
        order[k] = current
        np.minimum(nearest, ((points - points[current]) ** 2).sum(axis=1), out=nearest)
        nearest[current] = -1.0
        current = int(np.argmax(nearest))
    return order


def _ellipsoid(rng: np.random.Generator, n: int, center, radii) -> np.ndarray:
    v = rng.normal(size=(n, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return np.asarray(center) + v * np.asarray(radii)


@dataclass
class BrainMesh:
    seed: int = 11
    max_points: int = MAX_POINTS
    points: np.ndarray = field(init=False)
    growth_order: np.ndarray = field(init=False)      # ordem de adensamento (uniforme em qualquer etapa)
    inner_mask: np.ndarray = field(init=False)        # pontos internos (revelados pela profundidade)
    genesis_rank: np.ndarray = field(init=False)      # 0..1: ordem de nascimento na inicialização
    membership: dict = field(init=False)              # região → índices dos pontos dentro dela
    _edges_cache: dict = field(init=False, default_factory=dict)

    def __post_init__(self):
        rng = np.random.default_rng(self.seed)
        n_temporal, n_cerebellum, n_stem, n_inner = 56, 56, 18, 44
        n_shell = self.max_points - n_temporal - n_cerebellum - n_stem - n_inner
        parts = [_shell(rng, n_shell)]
        for side in (-1, 1):                              # lobos temporais
            parts.append(_ellipsoid(rng, n_temporal // 2, (-0.18, 0.30, 0.60 * side), (0.46, 0.17, 0.17)))
        parts.append(_ellipsoid(rng, n_cerebellum, (0.58, 0.62, 0.0), (0.28, 0.15, 0.30)))
        stem_t = rng.uniform(0, 1, n_stem)
        angle = rng.uniform(0, 2 * np.pi, n_stem)
        parts.append(np.stack([0.26 + 0.07 * stem_t + 0.06 * np.cos(angle), 0.48 + 0.42 * stem_t,
                               0.06 * np.sin(angle)], axis=1))
        inner = []                                        # estruturas profundas: tálamo e hipocampos
        for side in (-1, 1):
            inner.append(_ellipsoid(rng, n_inner // 4, (0.04, 0.0, 0.16 * side), (0.16, 0.10, 0.09)))
            inner.append(_ellipsoid(rng, n_inner // 4, (0.06, 0.22, 0.28 * side), (0.22, 0.06, 0.07)))
        parts.extend(inner)
        self.points = np.vstack(parts).astype(np.float64)
        n = len(self.points)
        self.inner_mask = np.zeros(n, dtype=bool)
        self.inner_mask[n - sum(len(x) for x in inner):] = True
        self.growth_order = _spread_order(self.points, int(rng.integers(n)))
        # nascimento: do tronco para a coroa (como uma gênese), com variação
        height = -self.points[:, 1] + rng.uniform(-0.35, 0.35, n)
        order = np.argsort(height)
        self.genesis_rank = np.empty(n)
        self.genesis_rank[order] = np.linspace(0.0, 1.0, n)
        self.membership = {}
        for name, (rx, ry, rz, radius) in REGIONS.items():
            sides = (-rz,) if name in LEFT_ONLY else ((rz, -rz) if rz else (0.0,))
            hits = np.zeros(n, dtype=bool)
            for z in sides:
                d = np.linalg.norm(self.points - np.array([rx, ry, z]), axis=1)
                hits |= d < radius * 1.25
            self.membership[name] = np.nonzero(hits)[0]

    # ------------------------------------------------------------ crescimento
    def visible_count(self, development: float) -> int:
        """Pontos visíveis; cresce em degraus de ``GROWTH_STEP`` (as sinapses só são recalculadas
        quando o cérebro cresce de fato, não a cada nó novo)."""
        development = max(0.0, min(1.0, development))
        grown = int((len(self.points) - MIN_VISIBLE) * development / GROWTH_STEP) * GROWTH_STEP
        return MIN_VISIBLE + grown

    def visible_indices(self, development: float, cap: int | None = None) -> np.ndarray:
        """Pontos visíveis; ``cap`` limita o desenho (perfil de desempenho) mantendo a cobertura
        uniforme, pois a ordem de crescimento é a do ponto mais distante."""
        count = self.visible_count(development)
        if cap is not None:
            count = max(min(MIN_VISIBLE, len(self.points)), min(count, int(cap)))
        return np.sort(self.growth_order[:count])

    def edges(self, indices: np.ndarray, *, k: int = 3) -> np.ndarray:
        """Sinapses da malha: cada ponto ligado aos ``k`` vizinhos mais próximos (pares únicos)."""
        key = (len(indices), int(indices.sum()) if len(indices) else 0, k)
        cached = self._edges_cache.pop(key, None)
        if cached is not None:
            self._edges_cache[key] = cached                 # mais recente por último (LRU)
            return cached
        pts = self.points[indices]
        sq = (pts ** 2).sum(axis=1)
        d2 = sq[:, None] + sq[None, :] - 2.0 * (pts @ pts.T)          # distâncias² (matriz de Gram)
        np.fill_diagonal(d2, np.inf)
        limit = 0.30 ** 2 * (MIN_VISIBLE / max(MIN_VISIBLE, len(indices))) ** (2 / 3) * 1.6
        neighbors = np.argpartition(d2, k, axis=1)[:, :k]
        rows = np.repeat(np.arange(len(indices)), k)
        cols = neighbors.ravel()
        keep = d2[rows, cols] <= limit
        a, b = indices[rows[keep]], indices[cols[keep]]
        pairs = np.stack([np.minimum(a, b), np.maximum(a, b)], axis=1)
        result = np.unique(pairs, axis=0).astype(np.int32) if len(pairs) else np.zeros((0, 2), np.int32)
        self._edges_cache[key] = result
        while len(self._edges_cache) > 6:                  # HUB e orbe usam conjuntos diferentes
            self._edges_cache.pop(next(iter(self._edges_cache)))
        return result

    # ------------------------------------------------------------ regiões e nós do grafo
    @staticmethod
    def region_center(name: str, side: float = 1.0) -> np.ndarray:
        x, y, z, _r = REGIONS.get(name, REGIONS["core"])
        if name in LEFT_ONLY:
            side = -1.0
        return np.array([x, y, z * (1.0 if side >= 0 else -1.0)])

    @staticmethod
    def inside(x: float, y: float, z: float) -> bool:
        main = (x / 1.02) ** 2 + (y / 0.80) ** 2 + (z / 0.82) ** 2 <= 1.0
        cerebellum = ((x - 0.58) / 0.30) ** 2 + ((y - 0.62) / 0.17) ** 2 + (z / 0.32) ** 2 <= 1.0
        return main or cerebellum

    def place(self, node_id: str, node_type: str) -> tuple[float, float, float]:
        """Posição fixa de um nó do grafo dentro da região do seu tipo."""
        digest = hashlib.sha1(node_id.encode("utf-8")).digest()
        regions = TYPE_REGIONS.get(node_type, ("core", "parietal", "frontal"))
        region = regions[digest[0] % len(regions)]
        rx, ry, rz, radius = REGIONS[region]
        side = -1.0 if region in LEFT_ONLY else (1.0 if digest[1] & 1 else -1.0)
        for attempt in range(16):
            u = np.array([digest[(2 + 3 * attempt) % 20], digest[(3 + 3 * attempt) % 20],
                          digest[(4 + 3 * attempt) % 20]], dtype=np.float64) / 255.0 * 2 - 1
            x, y, z = rx + u[0] * radius, ry + u[1] * radius * 0.8, rz * side + u[2] * radius * 0.6
            if self.inside(x, y, z):
                return float(x), float(y), float(z)
        return float(rx), float(ry), float(rz * side)

    # ------------------------------------------------------------ projeção
    @staticmethod
    def rotate(points: np.ndarray, angle: float, tilt: float = TILT) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Gira em torno do eixo vertical e inclina. Devolve (X, Y, Z) com Z > 0 = mais perto."""
        ca, sa = math.cos(angle), math.sin(angle)
        ct, st = math.cos(tilt), math.sin(tilt)
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        X = x * ca + z * sa
        Z = -x * sa + z * ca
        Y2 = y * ct - Z * st
        Z2 = y * st + Z * ct
        return X, Y2, Z2

    @classmethod
    def project(cls, points: np.ndarray, angle: float, cx: float, cy: float, scale: float,
                tilt: float = TILT) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Coordenadas de tela (sx, sy), profundidade (Z, −1 longe … +1 perto) e fator de perspectiva."""
        X, Y, Z = cls.rotate(points, angle, tilt)
        f = 1.0 / (1.0 - Z * PERSPECTIVE)
        return cx + X * scale * STRETCH * f, cy + Y * scale * f, Z, f

    @staticmethod
    def facing_angle(name: str) -> float:
        """Ângulo de rotação que vira a região para o observador."""
        x, _y, z, _r = REGIONS.get(name, REGIONS["core"])
        if name in LEFT_ONLY:
            z = -z
        if abs(x) < 1e-6 and abs(z) < 1e-6:
            return 0.0
        return math.atan2(-x, z)
