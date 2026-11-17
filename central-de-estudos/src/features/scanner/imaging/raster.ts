/**
 * Operações sobre imagens RGBA em memória (sem navegador): rotação,
 * redimensionamento com média de área e correção de perspectiva bilinear.
 */
import { homography, project, quadSize, type Quad } from './geometry';

export interface RasterImage {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

export function createRaster(width: number, height: number, rgba: [number, number, number, number] = [255, 255, 255, 255]): RasterImage {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = rgba[0];
    data[i + 1] = rgba[1];
    data[i + 2] = rgba[2];
    data[i + 3] = rgba[3];
  }
  return { width, height, data };
}

/** Gira em múltiplos de 90° no sentido horário. */
export function rotateRaster(img: RasterImage, rotation: 0 | 90 | 180 | 270): RasterImage {
  if (rotation === 0) return img;
  const { width: w, height: h, data } = img;
  const swap = rotation === 90 || rotation === 270;
  const ow = swap ? h : w;
  const oh = swap ? w : h;
  const out = new Uint8ClampedArray(ow * oh * 4);
  const src32 = new Uint32Array(data.buffer, data.byteOffset, w * h);
  const dst32 = new Uint32Array(out.buffer);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let nx: number;
      let ny: number;
      if (rotation === 90) {
        nx = h - 1 - y;
        ny = x;
      } else if (rotation === 180) {
        nx = w - 1 - x;
        ny = h - 1 - y;
      } else {
        nx = y;
        ny = w - 1 - x;
      }
      dst32[ny * ow + nx] = src32[y * w + x]!;
    }
  }
  return { width: ow, height: oh, data: out };
}

/** Reduz para que o maior lado tenha no máximo `maxSide` (média de área: nítido e sem serrilhado). */
export function resizeRaster(img: RasterImage, maxSide: number): RasterImage {
  const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
  if (scale >= 1) return img;
  const ow = Math.max(1, Math.round(img.width * scale));
  const oh = Math.max(1, Math.round(img.height * scale));
  const out = new Uint8ClampedArray(ow * oh * 4);
  const sx = img.width / ow;
  const sy = img.height / oh;
  for (let oy = 0; oy < oh; oy++) {
    const y0 = Math.floor(oy * sy);
    const y1 = Math.max(y0 + 1, Math.min(img.height, Math.floor((oy + 1) * sy)));
    for (let ox = 0; ox < ow; ox++) {
      const x0 = Math.floor(ox * sx);
      const x1 = Math.max(x0 + 1, Math.min(img.width, Math.floor((ox + 1) * sx)));
      let r = 0;
      let g = 0;
      let b = 0;
      let a = 0;
      for (let y = y0; y < y1; y++) {
        let i = (y * img.width + x0) * 4;
        for (let x = x0; x < x1; x++, i += 4) {
          r += img.data[i]!;
          g += img.data[i + 1]!;
          b += img.data[i + 2]!;
          a += img.data[i + 3]!;
        }
      }
      const n = (y1 - y0) * (x1 - x0);
      const o = (oy * ow + ox) * 4;
      out[o] = r / n;
      out[o + 1] = g / n;
      out[o + 2] = b / n;
      out[o + 3] = a / n;
    }
  }
  return { width: ow, height: oh, data: out };
}

/** Amostragem bilinear de um canal. */
function sample(img: RasterImage, x: number, y: number, out: Uint8ClampedArray, o: number) {
  const x0 = Math.max(0, Math.min(img.width - 1, Math.floor(x)));
  const y0 = Math.max(0, Math.min(img.height - 1, Math.floor(y)));
  const x1 = Math.min(img.width - 1, x0 + 1);
  const y1 = Math.min(img.height - 1, y0 + 1);
  const fx = Math.min(1, Math.max(0, x - x0));
  const fy = Math.min(1, Math.max(0, y - y0));
  const i00 = (y0 * img.width + x0) * 4;
  const i10 = (y0 * img.width + x1) * 4;
  const i01 = (y1 * img.width + x0) * 4;
  const i11 = (y1 * img.width + x1) * 4;
  const d = img.data;
  for (let c = 0; c < 4; c++) {
    const top = d[i00 + c]! + (d[i10 + c]! - d[i00 + c]!) * fx;
    const bottom = d[i01 + c]! + (d[i11 + c]! - d[i01 + c]!) * fx;
    out[o + c] = top + (bottom - top) * fy;
  }
}

/**
 * Corrige a perspectiva: o quadrilátero `quadPx` (em pixels da imagem) vira um
 * retângulo `outW × outH`.
 */
export function warpPerspective(img: RasterImage, quadPx: Quad, outW: number, outH: number): RasterImage {
  const dst: Quad = [
    { x: 0, y: 0 },
    { x: outW - 1, y: 0 },
    { x: outW - 1, y: outH - 1 },
    { x: 0, y: outH - 1 },
  ];
  // Mapeia cada pixel de SAÍDA de volta para a imagem de origem.
  const H = homography(dst, quadPx);
  const out = new Uint8ClampedArray(outW * outH * 4);
  for (let y = 0; y < outH; y++) {
    for (let x = 0; x < outW; x++) {
      const p = project(H, x, y);
      sample(img, p.x, p.y, out, (y * outW + x) * 4);
    }
  }
  return { width: outW, height: outH, data: out };
}

/** Recorta pelo quadrilátero normalizado, corrigindo a perspectiva, limitado a `maxSide`. */
export function cropToQuad(img: RasterImage, quad: Quad, maxSide: number): RasterImage {
  const px = quad.map((p) => ({ x: p.x * (img.width - 1), y: p.y * (img.height - 1) })) as Quad;
  const size = quadSize(px);
  const scale = Math.min(1, maxSide / Math.max(size.width, size.height));
  const outW = Math.max(1, Math.round(size.width * scale));
  const outH = Math.max(1, Math.round(size.height * scale));
  return warpPerspective(img, px, outW, outH);
}
