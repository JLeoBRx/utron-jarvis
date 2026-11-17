/**
 * Detecção automática da página (sem bibliotecas pesadas):
 * reduz a imagem, separa o papel (claro) do fundo por limiar de Otsu, pega a
 * maior região clara conectada e usa seus cantos extremos. Funciona bem com a
 * folha sobre uma mesa mais escura; quando não há contraste, devolve `null` e
 * o recorte fica manual.
 */
import { orderQuad, polygonArea, type Quad } from './geometry';
import { resizeRaster, type RasterImage } from './raster';

export interface Detection {
  quad: Quad;
  /** 0–1: quão "retangular" e bem definida é a região encontrada. */
  confidence: number;
}

function otsu(gray: Uint8Array): number {
  const hist = new Uint32Array(256);
  for (const v of gray) hist[v]! += 1;
  const total = gray.length;
  let sum = 0;
  for (let i = 0; i < 256; i++) sum += i * hist[i]!;
  let sumB = 0;
  let wB = 0;
  let best = 0;
  let threshold = 127;
  for (let t = 0; t < 256; t++) {
    wB += hist[t]!;
    if (!wB) continue;
    const wF = total - wB;
    if (!wF) break;
    sumB += t * hist[t]!;
    const mB = sumB / wB;
    const mF = (sum - sumB) / wF;
    const between = wB * wF * (mB - mF) ** 2;
    if (between > best) {
      best = between;
      threshold = t;
    }
  }
  return threshold;
}

export function detectDocument(img: RasterImage): Detection | null {
  const small = resizeRaster(img, 256);
  const { width: w, height: h, data } = small;
  const gray = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    gray[i] = 0.299 * data[i * 4]! + 0.587 * data[i * 4 + 1]! + 0.114 * data[i * 4 + 2]!;
  }
  // suavização leve (média 3×3) para ignorar pautas e textura do papel
  const blurred = new Uint8Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let s = 0;
      let n = 0;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          const ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
          s += gray[ny * w + nx]!;
          n++;
        }
      }
      blurred[y * w + x] = s / n;
    }
  }
  const t = otsu(blurred);
  const bright = new Uint8Array(w * h);
  let brightCount = 0;
  for (let i = 0; i < w * h; i++) {
    if (blurred[i]! > t) {
      bright[i] = 1;
      brightCount++;
    }
  }
  if (brightCount > w * h * 0.97) return null; // a folha ocupa tudo: nada a recortar

  // maior componente conectado (vizinhança 4)
  const label = new Int32Array(w * h).fill(-1);
  let bestStart = -1;
  let bestSize = 0;
  const stack: number[] = [];
  for (let start = 0; start < w * h; start++) {
    if (!bright[start] || label[start] !== -1) continue;
    let size = 0;
    stack.push(start);
    label[start] = start;
    while (stack.length) {
      const p = stack.pop()!;
      size++;
      const x = p % w;
      const y = (p - x) / w;
      const neighbors = [x > 0 ? p - 1 : -1, x < w - 1 ? p + 1 : -1, y > 0 ? p - w : -1, y < h - 1 ? p + w : -1];
      for (const q of neighbors) {
        if (q >= 0 && bright[q] && label[q] === -1) {
          label[q] = start;
          stack.push(q);
        }
      }
    }
    if (size > bestSize) {
      bestSize = size;
      bestStart = start;
    }
  }
  if (bestStart < 0 || bestSize < w * h * 0.12) return null;

  let tl = { x: 0, y: 0, v: Infinity };
  let br = { x: 0, y: 0, v: -Infinity };
  let tr = { x: 0, y: 0, v: -Infinity };
  let bl = { x: 0, y: 0, v: Infinity };
  for (let p = 0; p < w * h; p++) {
    if (label[p] !== bestStart) continue;
    const x = p % w;
    const y = (p - x) / w;
    if (x + y < tl.v) tl = { x, y, v: x + y };
    if (x + y > br.v) br = { x, y, v: x + y };
    if (x - y > tr.v) tr = { x, y, v: x - y };
    if (x - y < bl.v) bl = { x, y, v: x - y };
  }
  const quadPx = orderQuad([tl, tr, br, bl].map(({ x, y }) => ({ x, y })));
  const quadArea = polygonArea(quadPx);
  if (quadArea < 1) return null;
  // Região quase retangular → área da região ≈ área do quadrilátero.
  const fill = Math.min(1, bestSize / quadArea);
  const coverage = quadArea / (w * h);
  const confidence = Math.max(0, Math.min(1, fill * (coverage > 0.95 ? 0.5 : 1)));
  // Recua 1% em direção ao centro: evita sobrar uma faixa da mesa nas bordas.
  const cx = quadPx.reduce((sum, p) => sum + p.x, 0) / 4;
  const cy = quadPx.reduce((sum, p) => sum + p.y, 0) / 4;
  const inset = 0.01;
  const quad = quadPx.map((p) => ({
    x: (p.x + (cx - p.x) * inset) / (w - 1),
    y: (p.y + (cy - p.y) * inset) / (h - 1),
  })) as Quad;
  return { quad, confidence };
}
