/**
 * Geometria do recorte: quadriláteros, homografia (correção de perspectiva) e
 * rotação de pontos. Funções puras, sem dependência do navegador.
 */
import type { Point } from '@/data/services/scans';

export type { Point };
/** Cantos na ordem: superior-esquerdo, superior-direito, inferior-direito, inferior-esquerdo. */
export type Quad = [Point, Point, Point, Point];

export const FULL_QUAD: Quad = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
];

export function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/** Ordena 4 pontos quaisquer como [SE, SD, ID, IE]. */
export function orderQuad(points: Point[]): Quad {
  const bySum = [...points].sort((a, b) => a.x + a.y - (b.x + b.y));
  const byDiff = [...points].sort((a, b) => a.x - a.y - (b.x - b.y));
  return [bySum[0]!, byDiff[3]!, bySum[3]!, byDiff[0]!];
}

/** Largura/altura do retângulo de saída (maior lado oposto). */
export function quadSize(q: Quad): { width: number; height: number } {
  return {
    width: Math.max(distance(q[0], q[1]), distance(q[3], q[2])),
    height: Math.max(distance(q[0], q[3]), distance(q[1], q[2])),
  };
}

export function polygonArea(points: Point[]): number {
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i]!;
    const b = points[(i + 1) % points.length]!;
    area += a.x * b.y - b.x * a.y;
  }
  return Math.abs(area) / 2;
}

/** Quadrilátero convexo e sem cruzamentos (cantos arrastados de forma válida). */
export function isConvexQuad(q: Quad): boolean {
  let sign = 0;
  for (let i = 0; i < 4; i++) {
    const a = q[i]!;
    const b = q[(i + 1) % 4]!;
    const c = q[(i + 2) % 4]!;
    const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
    if (Math.abs(cross) < 1e-9) return false;
    const s = Math.sign(cross);
    if (sign === 0) sign = s;
    else if (s !== sign) return false;
  }
  return polygonArea(q) > 1e-4;
}

/**
 * Homografia H (3×3, linha a linha) tal que H·src = dst.
 * Resolve o sistema linear 8×8 por eliminação de Gauss com pivoteamento.
 */
export function homography(src: Quad, dst: Quad): number[] {
  const A: number[][] = [];
  const b: number[] = [];
  for (let i = 0; i < 4; i++) {
    const { x, y } = src[i]!;
    const { x: u, y: v } = dst[i]!;
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]);
    b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]);
    b.push(v);
  }
  const n = 8;
  for (let col = 0; col < n; col++) {
    let pivot = col;
    for (let r = col + 1; r < n; r++) if (Math.abs(A[r]![col]!) > Math.abs(A[pivot]![col]!)) pivot = r;
    if (Math.abs(A[pivot]![col]!) < 1e-12) throw new Error('Pontos degenerados: não é possível corrigir a perspectiva.');
    [A[col], A[pivot]] = [A[pivot]!, A[col]!];
    [b[col], b[pivot]] = [b[pivot]!, b[col]!];
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const f = A[r]![col]! / A[col]![col]!;
      if (f === 0) continue;
      for (let c = col; c < n; c++) A[r]![c]! -= f * A[col]![c]!;
      b[r]! -= f * b[col]!;
    }
  }
  const h = b.map((value, i) => value / A[i]![i]!);
  return [...h, 1];
}

export function project(H: number[], x: number, y: number): Point {
  const w = H[6]! * x + H[7]! * y + H[8]!;
  return { x: (H[0]! * x + H[1]! * y + H[2]!) / w, y: (H[3]! * x + H[4]! * y + H[5]!) / w };
}

/** Gira um ponto normalizado junto com a imagem (sentido horário). */
export function rotatePoint(p: Point, rotation: 0 | 90 | 180 | 270): Point {
  switch (rotation) {
    case 90:
      return { x: 1 - p.y, y: p.x };
    case 180:
      return { x: 1 - p.x, y: 1 - p.y };
    case 270:
      return { x: p.y, y: 1 - p.x };
    default:
      return { ...p };
  }
}

export function rotateQuad(q: Quad, rotation: 0 | 90 | 180 | 270): Quad {
  return orderQuad(q.map((p) => rotatePoint(p, rotation)));
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}
