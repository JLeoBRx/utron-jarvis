"""Textura do córtex (numpy): relevo iluminado com acabamento de metal escuro.

* campo de dobras: soma de ondas planas de mesmo comprimento em direções aleatórias
  (campo aleatório de banda estreita) com distorção de domínio — produz o padrão
  labiríntico de giros e sulcos com espaçamento regular, como no córtex real;
* a amplitude das dobras cresce com ``development`` (o cérebro jovem é liso; o maduro,
  profundamente dobrado), que vem do tamanho real do Neural Graph;
* iluminação: difusa + especular (metal) + luz de borda, em grafite, bronze e ouro.

O campo é calculado uma vez (≈2 s) e guardado em ``<dados>/hud_cortex.npz``; cada nível de
desenvolvimento custa ≈0,3 s e roda fora da thread da interface.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

from .brain_model import BrainGeometry, fbm, point_in_polygon

log = logging.getLogger("ultron.hud.cortex")

X0, X1, Y0, Y1 = -1.05, 1.05, -0.80, 0.85
FIELD_VERSION = 2


def _random_wave(gx: np.ndarray, gy: np.ndarray, k: float, n: int = 24, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros_like(gx)
    for _ in range(n):
        theta = rng.uniform(0, np.pi)
        phase = rng.uniform(0, 2 * np.pi)
        kk = k * rng.uniform(0.9, 1.1)
        out += np.cos(kk * (np.cos(theta) * gx + np.sin(theta) * gy) + phase)
    return out / np.sqrt(n / 2)


class CortexRenderer:
    def __init__(self, geometry: BrainGeometry, *, width: int = 840, cache_path: Path | None = None):
        self.geometry = geometry
        self.width = width
        self.height = int(width * (Y1 - Y0) / (X1 - X0))
        self.cache_path = cache_path
        self._fields: dict[str, np.ndarray] | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ campos (caros, uma vez)
    def _compute_fields(self) -> dict[str, np.ndarray]:
        g = self.geometry
        xs = np.linspace(X0, X1, self.width)
        ys = np.linspace(Y0, Y1, self.height)
        gx, gy = np.meshgrid(xs, ys)
        wx = fbm(gx.shape, np.random.default_rng(1), base=3, octaves=3) - 0.5
        wy = fbm(gx.shape, np.random.default_rng(2), base=3, octaves=3) - 0.5
        folds = _random_wave(gx + 0.16 * wx, gy + 0.16 * wy, k=2 * np.pi / 0.11)
        ring = np.hypot((gx - 0.64) * 0.75, (gy - 0.70) * 1.25)
        folia = np.sin(2 * np.pi * ring / 0.028 + 3 * wx)
        return {
            "folds": folds.astype(np.float32),
            "folia": folia.astype(np.float32),
            "cerebrum": point_in_polygon(gx, gy, g.cerebrum),
            "cerebellum": point_in_polygon(gx, gy, g.cerebellum),
            "brainstem": point_in_polygon(gx, gy, g.brainstem),
        }

    def fields(self) -> dict[str, np.ndarray]:
        with self._lock:
            if self._fields is not None:
                return self._fields
            cached = self._load_cache()
            self._fields = cached if cached is not None else self._compute_fields()
            if cached is None:
                self._save_cache(self._fields)
            return self._fields

    def _load_cache(self) -> dict[str, np.ndarray] | None:
        if self.cache_path is None or not self.cache_path.is_file():
            return None
        try:
            with np.load(self.cache_path) as data:
                if int(data["version"]) != FIELD_VERSION or data["folds"].shape != (self.height, self.width):
                    return None
                return {k: data[k] for k in ("folds", "folia", "cerebrum", "cerebellum", "brainstem")}
        except Exception as exc:                                   # cache corrompido: recalcula
            log.debug("cache do córtex ignorado: %s", exc)
            return None

    def _save_cache(self, fields: dict[str, np.ndarray]) -> None:
        if self.cache_path is None:
            return
        try:
            np.savez_compressed(self.cache_path, version=FIELD_VERSION, **fields)
        except OSError as exc:
            log.debug("não foi possível salvar o cache do córtex: %s", exc)

    # ------------------------------------------------------------ iluminação
    def _shade(self, height: np.ndarray, groove: np.ndarray | None) -> np.ndarray:
        dy, dx = np.gradient(height, (Y1 - Y0) / self.height, (X1 - X0) / self.width)
        nx, ny, nz = -dx, -dy, np.ones_like(dx)
        n = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
        nx, ny, nz = nx / n, ny / n, nz / n
        light = np.array([-0.40, -0.70, 0.60])
        light /= np.linalg.norm(light)
        lam = np.clip(nx * light[0] + ny * light[1] + nz * light[2], 0, 1)
        half = light + np.array([0.0, 0.0, 1.0])
        half /= np.linalg.norm(half)
        spec = np.clip(nx * half[0] + ny * half[1] + nz * half[2], 0, 1) ** 40
        rim = np.clip(1 - nz, 0, 1) ** 2
        col = (np.array([13, 12, 11], np.float32)
               + np.array([58, 47, 34], np.float32) * (lam ** 2.2)[..., None]
               + np.array([235, 172, 72], np.float32) * (spec * 0.85)[..., None]
               + np.array([190, 120, 45], np.float32) * (rim * 0.35)[..., None])
        if groove is not None:
            col *= (1 - 0.6 * groove)[..., None]
        return col

    def texture(self, development: float) -> np.ndarray:
        """RGBA uint8 (altura × largura × 4) para o nível de desenvolvimento dado."""
        f = self.fields()
        dev = max(0.0, min(1.0, float(development)))
        xs = np.linspace(X0, X1, self.width, dtype=np.float32)
        ys = np.linspace(Y0, Y1, self.height, dtype=np.float32)
        gx, gy = np.meshgrid(xs, ys)
        dome = np.clip(1.0 - (gx / 1.05) ** 2 - ((gy + 0.05) / 0.85) ** 2, 0, 1) ** 0.5
        amp = 0.10 * dev ** 1.4
        groove = np.clip(1 - np.abs(f["folds"]) * 1.8, 0, 1) ** 2 * dev ** 1.4
        cerebrum = self._shade(dome + np.tanh(1.6 * f["folds"]) * amp, groove)
        dome_c = np.clip(1.0 - ((gx - 0.66) / 0.32) ** 2 - ((gy - 0.46) / 0.18) ** 2, 0, 1) ** 0.5
        cerebellum = self._shade(dome_c * 0.5 + np.tanh(2 * f["folia"]) * 0.012 * (0.4 + 0.6 * dev), None)
        stem = self._shade(np.clip(1.0 - ((gx - 0.32) / 0.08) ** 2, 0, 1) ** 0.5 * 0.3, None) * 0.8
        m1, m2 = f["cerebrum"], f["cerebellum"]
        m3 = f["brainstem"] & ~m1 & ~m2
        col = np.where(m1[..., None], cerebrum, np.where(m2[..., None], cerebellum, stem))
        alpha = (m1 | m2 | m3).astype(np.float32) * 255
        return np.dstack([np.clip(col, 0, 255), alpha]).astype(np.uint8)
