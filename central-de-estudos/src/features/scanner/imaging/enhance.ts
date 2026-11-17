/**
 * Correção de iluminação para fotos de caderno:
 *  - realce: estica os níveis (contraste automático) preservando as cores;
 *  - documento: estima a iluminação de fundo e a remove (tira sombras, deixa o
 *    papel uniforme) mantendo cores de canetas e marca-texto;
 *  - pb: documento + preto e branco suave (bom para lápis claro).
 */
import type { RasterImage } from './raster';

const luma = (r: number, g: number, b: number) => 0.299 * r + 0.587 * g + 0.114 * b;

function clone(img: RasterImage): RasterImage {
  return { width: img.width, height: img.height, data: new Uint8ClampedArray(img.data) };
}

function percentile(hist: Uint32Array, total: number, p: number): number {
  const target = total * p;
  let acc = 0;
  for (let i = 0; i < 256; i++) {
    acc += hist[i]!;
    if (acc >= target) return i;
  }
  return 255;
}

export function autoLevels(img: RasterImage, low = 0.01, high = 0.99): RasterImage {
  const hist = new Uint32Array(256);
  const d = img.data;
  const n = img.width * img.height;
  for (let i = 0; i < d.length; i += 4) hist[Math.round(luma(d[i]!, d[i + 1]!, d[i + 2]!))]! += 1;
  const lo = percentile(hist, n, low);
  const hi = percentile(hist, n, high);
  if (hi - lo < 8) return clone(img);
  const scale = 255 / (hi - lo);
  const out = clone(img);
  for (let i = 0; i < d.length; i += 4) {
    out.data[i] = (d[i]! - lo) * scale;
    out.data[i + 1] = (d[i + 1]! - lo) * scale;
    out.data[i + 2] = (d[i + 2]! - lo) * scale;
  }
  return out;
}

/** Mapa de iluminação: máximo por bloco (pega o papel, ignora a tinta) + suavização. */
export function estimateBackground(img: RasterImage, blocks = 48): { map: Float32Array; width: number; height: number } {
  const bw = Math.max(1, Math.ceil(img.width / blocks));
  const bh = Math.max(1, Math.ceil(img.height / blocks));
  const gw = Math.ceil(img.width / bw);
  const gh = Math.ceil(img.height / bh);
  let grid = new Float32Array(gw * gh);
  const d = img.data;
  for (let gy = 0; gy < gh; gy++) {
    for (let gx = 0; gx < gw; gx++) {
      // percentil alto (≈ máximo robusto) do bloco
      const values: number[] = [];
      for (let y = gy * bh; y < Math.min(img.height, (gy + 1) * bh); y += 2) {
        for (let x = gx * bw; x < Math.min(img.width, (gx + 1) * bw); x += 2) {
          const i = (y * img.width + x) * 4;
          values.push(luma(d[i]!, d[i + 1]!, d[i + 2]!));
        }
      }
      values.sort((a, b) => a - b);
      grid[gy * gw + gx] = values[Math.floor(values.length * 0.9)] ?? 255;
    }
  }
  // dilatação (máximo entre vizinhos, 2 passadas): blocos cheios de texto
  // herdam o brilho do papel ao redor — evita manchas claras em volta da escrita.
  for (let pass = 0; pass < 2; pass++) {
    const next = new Float32Array(grid.length);
    for (let y = 0; y < gh; y++) {
      for (let x = 0; x < gw; x++) {
        let max = 0;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            const nx = x + dx;
            const ny = y + dy;
            if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) continue;
            max = Math.max(max, grid[ny * gw + nx]!);
          }
        }
        next[y * gw + x] = max;
      }
    }
    grid = next;
  }
  // suaviza (3 passadas de média 3×3)
  for (let pass = 0; pass < 3; pass++) {
    const next = new Float32Array(grid.length);
    for (let y = 0; y < gh; y++) {
      for (let x = 0; x < gw; x++) {
        let sum = 0;
        let count = 0;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            const nx = x + dx;
            const ny = y + dy;
            if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) continue;
            sum += grid[ny * gw + nx]!;
            count++;
          }
        }
        next[y * gw + x] = sum / count;
      }
    }
    grid = next;
  }
  return { map: grid, width: gw, height: gh };
}

function backgroundAt(bg: { map: Float32Array; width: number; height: number }, fx: number, fy: number): number {
  const x = Math.min(bg.width - 1, Math.max(0, fx * bg.width - 0.5));
  const y = Math.min(bg.height - 1, Math.max(0, fy * bg.height - 0.5));
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const x1 = Math.min(bg.width - 1, x0 + 1);
  const y1 = Math.min(bg.height - 1, y0 + 1);
  const tx = x - x0;
  const ty = y - y0;
  const m = bg.map;
  const top = m[y0 * bg.width + x0]! * (1 - tx) + m[y0 * bg.width + x1]! * tx;
  const bottom = m[y1 * bg.width + x0]! * (1 - tx) + m[y1 * bg.width + x1]! * tx;
  return top * (1 - ty) + bottom * ty;
}

export function removeShadows(img: RasterImage): RasterImage {
  const bg = estimateBackground(img);
  const out = clone(img);
  const d = img.data;
  for (let y = 0; y < img.height; y++) {
    const fy = (y + 0.5) / img.height;
    for (let x = 0; x < img.width; x++) {
      const light = Math.max(24, backgroundAt(bg, (x + 0.5) / img.width, fy));
      const gain = 245 / light;
      const i = (y * img.width + x) * 4;
      out.data[i] = d[i]! * gain;
      out.data[i + 1] = d[i + 1]! * gain;
      out.data[i + 2] = d[i + 2]! * gain;
    }
  }
  return autoLevels(out, 0.005, 0.995);
}

export function toBlackAndWhite(img: RasterImage): RasterImage {
  const clean = removeShadows(img);
  const out = clone(clean);
  const d = clean.data;
  for (let i = 0; i < d.length; i += 4) {
    const v = luma(d[i]!, d[i + 1]!, d[i + 2]!);
    // limiar suave: preserva traços finos sem serrilhar
    const t = 255 / (1 + Math.exp(-(v - 175) / 14));
    out.data[i] = t;
    out.data[i + 1] = t;
    out.data[i + 2] = t;
  }
  return out;
}

/** brightness e contrast em −100…100. */
export function brightnessContrast(img: RasterImage, brightness: number, contrast: number): RasterImage {
  if (!brightness && !contrast) return img;
  const c = (contrast / 100) * 128;
  const factor = (259 * (c + 255)) / (255 * (259 - c));
  const b = brightness * 1.28;
  const out = clone(img);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    out.data[i] = factor * (d[i]! - 128) + 128 + b;
    out.data[i + 1] = factor * (d[i + 1]! - 128) + 128 + b;
    out.data[i + 2] = factor * (d[i + 2]! - 128) + 128 + b;
  }
  return out;
}
