import { describe, expect, it } from 'vitest';
import { DEFAULT_EDITS } from '@/data/services/scans';
import { detectDocument } from './detect';
import { removeShadows, toBlackAndWhite } from './enhance';
import { FULL_QUAD, homography, isConvexQuad, orderQuad, project, quadSize, rotateQuad, type Quad } from './geometry';
import { processPage } from './pipeline';
import { createRaster, resizeRaster, rotateRaster, warpPerspective, type RasterImage } from './raster';

/** Folha de caderno sintética: papel claro com pautas sobre mesa escura, com sombra opcional. */
function notebookPhoto(opts: { width?: number; height?: number; corners: Quad; shadow?: boolean }): RasterImage {
  const width = opts.width ?? 400;
  const height = opts.height ?? 300;
  const img = createRaster(width, height, [55, 50, 48, 255]);
  // homografia folha (0..1) → foto, para desenhar as pautas na perspectiva certa
  const H = homography(FULL_QUAD, opts.corners);
  const Hinv = homography(opts.corners, FULL_QUAD);
  void H;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const p = project(Hinv, x, y);
      if (p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) continue;
      const shade = opts.shadow ? 0.5 + 0.5 * p.x : 1; // sombra forte do lado esquerdo
      const line = Math.abs((p.y * 20) % 1) < 0.12 && p.x > 0.08 && p.x < 0.92; // "texto"
      const v = (line ? 40 : 238) * shade;
      const i = (y * width + x) * 4;
      img.data[i] = v;
      img.data[i + 1] = v;
      img.data[i + 2] = line ? v + 30 * shade : v; // tinta azulada
    }
  }
  return img;
}

const tilted: Quad = [
  { x: 70, y: 40 },
  { x: 330, y: 25 },
  { x: 350, y: 270 },
  { x: 55, y: 280 },
];

function lumaAt(img: RasterImage, x: number, y: number): number {
  const i = (Math.round(y) * img.width + Math.round(x)) * 4;
  return 0.299 * img.data[i]! + 0.587 * img.data[i + 1]! + 0.114 * img.data[i + 2]!;
}

describe('geometria', () => {
  it('homografia leva cada canto ao destino', () => {
    const H = homography(FULL_QUAD, tilted);
    FULL_QUAD.forEach((p, i) => {
      const q = project(H, p.x, p.y);
      expect(q.x).toBeCloseTo(tilted[i]!.x, 6);
      expect(q.y).toBeCloseTo(tilted[i]!.y, 6);
    });
  });

  it('ordena cantos e valida quadriláteros', () => {
    const shuffled = [tilted[2], tilted[0], tilted[3], tilted[1]] as Quad;
    expect(orderQuad(shuffled)).toEqual(tilted);
    expect(isConvexQuad(tilted)).toBe(true);
    expect(isConvexQuad([tilted[0], tilted[2], tilted[1], tilted[3]])).toBe(false); // cruzado
  });

  it('girar o recorte 4×90° volta ao original', () => {
    const q: Quad = [
      { x: 0.1, y: 0.2 },
      { x: 0.8, y: 0.1 },
      { x: 0.9, y: 0.9 },
      { x: 0.2, y: 0.85 },
    ];
    let r = q;
    for (let i = 0; i < 4; i++) r = rotateQuad(r, 90);
    r.forEach((p, i) => {
      expect(p.x).toBeCloseTo(q[i]!.x, 9);
      expect(p.y).toBeCloseTo(q[i]!.y, 9);
    });
  });
});

describe('raster', () => {
  it('rotação de 90° move os pixels corretamente e 4 rotações restauram a imagem', () => {
    const img = createRaster(3, 2, [0, 0, 0, 255]);
    img.data.set([255, 0, 0, 255], 0); // pixel (0,0) vermelho
    const r = rotateRaster(img, 90);
    expect([r.width, r.height]).toEqual([2, 3]);
    expect(Array.from(r.data.slice((0 * 2 + 1) * 4, (0 * 2 + 1) * 4 + 4))).toEqual([255, 0, 0, 255]); // vai para (1,0)
    let back = img;
    for (let i = 0; i < 4; i++) back = rotateRaster(back, 90);
    expect(Array.from(back.data)).toEqual(Array.from(img.data));
  });

  it('redução por média de área preserva a cor média', () => {
    const img = createRaster(100, 50, [10, 200, 30, 255]);
    const small = resizeRaster(img, 20);
    expect([small.width, small.height]).toEqual([20, 10]);
    expect(Array.from(small.data.slice(0, 4))).toEqual([10, 200, 30, 255]);
  });

  it('correção de perspectiva transforma a folha inclinada em retângulo só com papel', () => {
    const photo = notebookPhoto({ corners: tilted });
    const flat = warpPerspective(photo, tilted, 200, 240);
    expect([flat.width, flat.height]).toEqual([200, 240]);
    // bordas da saída são papel (claro), não a mesa (escura ≈ 50)
    for (const [x, y] of [[3, 3], [196, 3], [196, 236], [3, 236], [100, 120]]) {
      expect(lumaAt(flat, x!, y!), `(${x},${y})`).toBeGreaterThan(90);
    }
  });
});

describe('detecção da página', () => {
  it('encontra os 4 cantos da folha sobre a mesa', () => {
    const photo = notebookPhoto({ corners: tilted });
    const found = detectDocument(photo);
    expect(found).not.toBeNull();
    expect(found!.confidence).toBeGreaterThan(0.8);
    found!.quad.forEach((p, i) => {
      expect(Math.abs(p.x * 399 - tilted[i]!.x), `canto ${i} x`).toBeLessThan(12);
      expect(Math.abs(p.y * 299 - tilted[i]!.y), `canto ${i} y`).toBeLessThan(12);
    });
  });

  it('não inventa recorte quando a folha ocupa a foto inteira', () => {
    expect(detectDocument(createRaster(200, 150, [240, 240, 240, 255]))).toBeNull();
  });
});

describe('iluminação', () => {
  it('remove a sombra: o papel fica uniforme e o texto continua visível', () => {
    const photo = notebookPhoto({ corners: [{ x: 0, y: 0 }, { x: 399, y: 0 }, { x: 399, y: 299 }, { x: 0, y: 299 }], shadow: true });
    const paperLeftBefore = lumaAt(photo, 10, 5);
    const paperRightBefore = lumaAt(photo, 390, 5);
    expect(paperRightBefore - paperLeftBefore).toBeGreaterThan(80); // sombra forte

    const clean = removeShadows(photo);
    const paperLeft = lumaAt(clean, 10, 5);
    const paperRight = lumaAt(clean, 390, 5);
    expect(Math.abs(paperRight - paperLeft)).toBeLessThan(25);
    expect(paperLeft).toBeGreaterThan(200);
    // uma linha de "texto" (y≈0 na pauta) continua bem mais escura que o papel
    const textY = 1;
    expect(paperLeft - lumaAt(clean, 100, textY)).toBeGreaterThan(80);

    const bw = toBlackAndWhite(photo);
    expect(lumaAt(bw, 10, 5)).toBeGreaterThan(230);
  });
});

describe('pipeline da página', () => {
  it('gira, recorta e realça sem alterar a imagem original', () => {
    const photo = notebookPhoto({ corners: tilted, shadow: true });
    const before = photo.data.slice();
    const normalized = tilted.map((p) => ({ x: p.x / 399, y: p.y / 299 })) as Quad;
    const out = processPage(photo, { ...DEFAULT_EDITS, quad: normalized, enhance: 'documento' }, 300);
    expect(Math.max(out.width, out.height)).toBeLessThanOrEqual(300);
    // proporção da saída = proporção real da folha (maior lado oposto)
    const size = quadSize(tilted);
    expect(out.width / out.height).toBeCloseTo(size.width / size.height, 1);
    expect(Array.from(photo.data)).toEqual(Array.from(before));

    const rotated = processPage(photo, { ...DEFAULT_EDITS, rotation: 90, quad: rotateQuad(normalized, 90) }, 300);
    expect(Math.abs(rotated.width - out.height)).toBeLessThanOrEqual(2);
    expect(Math.abs(rotated.height - out.width)).toBeLessThanOrEqual(2);
  });
});
