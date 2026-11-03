// O holograma do JARVIS: corpo humano inteiro (1,80 m), construído aqui por seções ao longo de um esqueleto.
//
// * Esqueleto de 51 ossos (dedos com três falanges); proporções antropométricas.
// * Cada parte é uma superfície "loft" ao longo do seu osso, com perfis de músculo; a cabeça é a mesma função
//   do rosto holográfico 2D (ultron/hud/avatar/geometry.py), portada — mantém a identidade do JARVIS.
// * Desenho: linhas topológicas (contornos e meridianos), nós luminosos e casca translúcida (Fresnel), todos
//   deformados pelos ossos na GPU (materials.js). Mais uma camada interna: o próprio esqueleto, tênue.
// * Movimento: procedural, por estado REAL resolvido pelo JARVIS (nada é simulado aqui): respiração, apoio,
//   olhar, piscadas, gestos pela energia real da fala, mãos na execução, boca pela trilha labial do áudio.
import * as THREE from 'three';
import { ULTRON_RED, ULTRON_GLOW } from './ultron.js';
import { holoUniforms, holoLineMaterial, holoPointsMaterial, holoShellMaterial, holoCircuitMaterial, glowMaterial, glowTexture,
         disposer, canvasTexture, PALETTE, holoSolidMaterial } from './materials.js';
import { buildClothes, buildHair, buildBrows, dressUltron } from './avatar_dress.js';

const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const lerp = (a, b, t) => a + (b - a) * t;
const gauss = (x, mu, s) => Math.exp(-(((x - mu) / s) ** 2));

// ---------------------------------------------------------------- cabeça (porte de avatar/geometry.py)
const Y_EYE = -0.02, Y_BROW = 0.15, Y_NOSE = -0.36, Y_MOUTH = -0.60, HINGE_Y = -0.22, HINGE_Z = -0.05;
const EYE_THETA = 0.36;
export const HEAD_SCALE = 0.113;                    // unidades da função → metros (queixo ao topo ≈ 0,23 m)

export function headRadius(theta, y) {
  const c = Math.cos(theta), s = Math.sin(theta);
  const u = clamp((y + 0.05) / 1.05, 0, 1);
  const cranium = Math.pow(1 - Math.pow(u, 2.6), 1 / 2.6);
  const d = clamp((-0.05 - y) / 1.0, 0, 1);
  const jaw = 1 - 0.40 * Math.pow(d, 1.4) - 0.25 * Math.pow(clamp((d - 0.75) / 0.25, 0, 1), 2);
  const profile = y >= -0.05 ? cranium : jaw;
  const n = 2.6;
  const section = 1 / Math.pow(Math.pow(Math.abs(c / 0.94), n) + Math.pow(Math.abs(s / 0.78), n), 1 / n);
  let r = 0.80 * profile * section;
  const f3 = Math.pow(Math.max(0, c), 3);
  r *= 1 - 0.07 * f3 * gauss(y, -0.2, 0.6);
  r += 0.07 * f3 * gauss(y, Y_BROW, 0.045) * gauss(theta, 0, 0.6);           // arco da sobrancelha marcado
  for (const side of [-1, 1]) {
    r -= 0.085 * gauss(theta, side * EYE_THETA, 0.14) * gauss(y, Y_EYE, 0.075);
    r += 0.06 * gauss(theta, side * 0.64, 0.13) * gauss(y, -0.20, 0.10);       // maçã do rosto (plano sintético)
    r -= 0.05 * gauss(theta, side * 0.52, 0.12) * gauss(y, -0.48, 0.12);       // bochecha cavada
    r += 0.028 * gauss(theta, side * 0.78, 0.12) * gauss(y, -0.78, 0.09);      // ângulo da mandíbula
  }
  const k = clamp((Y_BROW - 0.03 - y) / (Y_BROW - 0.03 - Y_NOSE), 0, 1);
  let nose = 0.17 * Math.pow(k, 1.1) * (y > Y_NOSE - 0.05 ? 1 : 0) * gauss(y, Y_NOSE + 0.02, 0.6);
  if (y < Y_NOSE) nose = 0.17 * gauss(y, Y_NOSE, 0.05);
  r += nose * gauss(theta, 0, 0.065 + 0.05 * k);
  r += 0.030 * gauss(theta, 0, 0.32) * gauss(y, Y_MOUTH, 0.07);
  r += 0.055 * gauss(theta, 0, 0.24) * gauss(y, -0.90, 0.09);                 // queixo
  return r;
}

// ---------------------------------------------------------------- esqueleto
class Rig {
  constructor(root) { this.root = root; this.bones = []; this.map = {}; }

  bone(name, parent, [x, y, z], [rx, ry, rz] = [0, 0, 0]) {
    const b = new THREE.Object3D();
    b.name = name;
    b.position.set(x, y, z);
    b.rotation.set(rx, ry, rz);
    (parent ? this.map[parent] : this.root).add(b);
    b.userData.index = this.bones.length;
    this.bones.push(b);
    this.map[name] = b;
    return b;
  }

  bind() {
    this.root.updateMatrixWorld(true);
    const rootInv = new THREE.Matrix4().copy(this.root.matrixWorld).invert();
    this.bindModel = this.bones.map((b) => new THREE.Matrix4().multiplyMatrices(rootInv, b.matrixWorld));
    this.inverseBind = this.bindModel.map((m) => m.clone().invert());
    for (const b of this.bones) {
      b.userData.bindQ = b.quaternion.clone();
      b.userData.bindP = b.position.clone();
    }
    const rows = this.bones.length;
    this.data = new Float32Array(4 * 4 * rows);
    this.texture = disposer.track(new THREE.DataTexture(this.data, 4, rows, THREE.RGBAFormat, THREE.FloatType));
    this.texture.minFilter = this.texture.magFilter = THREE.NearestFilter;
    this.update();
  }

  /** Ponto no espaço local do osso (pose de ligação) → espaço do modelo. */
  toModel(name, x, y, z) { return new THREE.Vector3(x, y, z).applyMatrix4(this.bindModel[this.map[name].userData.index]); }

  index(name) { return this.map[name].userData.index; }

  /** Rotação relativa à pose de ligação (radianos). */
  rot(name, x = 0, y = 0, z = 0) {
    const b = this.map[name];
    _e.set(x, y, z);
    b.quaternion.copy(b.userData.bindQ).multiply(_q.setFromEuler(_e));
  }

  update() {
    this.root.updateMatrixWorld(true);
    _m1.copy(this.root.matrixWorld).invert();
    for (let i = 0; i < this.bones.length; i++) {
      _m2.multiplyMatrices(_m1, this.bones[i].matrixWorld).multiply(this.inverseBind[i]);
      this.data.set(_m2.elements, i * 16);
    }
    this.texture.needsUpdate = true;
  }
}
const _e = new THREE.Euler(), _q = new THREE.Quaternion(), _m1 = new THREE.Matrix4(), _m2 = new THREE.Matrix4();

// ---------------------------------------------------------------- construtor da malha
class BodyGeometry {
  constructor(rig) {
    this.rig = rig;
    this.pos = []; this.a = []; this.b = []; this.w = []; this.weight = [];
    this.lines = []; this.tris = []; this.points = [];
  }

  vert(p, a, b = a, w = 1, weight = 0.7) {
    this.pos.push(p.x, p.y, p.z); this.a.push(a); this.b.push(b); this.w.push(w); this.weight.push(weight);
    return this.pos.length / 3 - 1;
  }

  /** Grade de anéis (rings × segs) já construída → linhas, triângulos e pontos. */
  grid(ids, { closed = true, ringEvery = 1, meridianEvery = 1, pointEvery = 2, shell = true }) {
    const R = ids.length, S = ids[0].length;
    for (let i = 0; i < R; i++) {
      for (let j = 0; j < S; j++) {
        const jn = j + 1 < S ? j + 1 : (closed ? 0 : -1);
        if (jn >= 0 && i % ringEvery === 0) this.lines.push(ids[i][j], ids[i][jn]);
        if (i + 1 < R && j % meridianEvery === 0) this.lines.push(ids[i][j], ids[i + 1][j]);
        if (shell && i + 1 < R && jn >= 0) {
          this.tris.push(ids[i][j], ids[i + 1][j], ids[i + 1][jn], ids[i][j], ids[i + 1][jn], ids[i][jn]);
        }
        if ((i + j) % pointEvery === 0) this.points.push(ids[i][j]);
      }
    }
  }

  /**
   * Superfície ao longo do eixo −Y do osso (comprimento ``len``). ``profile(t)`` → [rx, rz]; ``frame`` gira a
   * seção (ex.: mãos achatadas no eixo Z). Perto do início, mistura com o osso pai (junta suave).
   */
  loft(bone, parent, len, { rings = 10, segs = 12, profile, blend = 0.22, shift = null, ...opts } = {}) {
    const ia = this.rig.index(bone), ib = parent ? this.rig.index(parent) : ia;
    const ids = [];
    for (let i = 0; i < rings; i++) {
      const t = i / (rings - 1);
      const [rx, rz] = profile(t);
      const row = [];
      const w = parent ? 0.5 + 0.5 * smooth(0, blend, t) : 1;
      for (let j = 0; j < segs; j++) {
        const ang = (j / segs) * Math.PI * 2;
        let x = Math.cos(ang) * rx, z = Math.sin(ang) * rz;
        if (shift) { const s = shift(t, ang); x += s[0]; z += s[1]; }
        const p = this.rig.toModel(bone, x, -t * len, z);
        const weight = (i === 0 || i === rings - 1) ? 0.95 : 0.62;
        row.push(this.vert(p, ia, ib, w, weight));
      }
      ids.push(row);
    }
    this.grid(ids, opts);
    return ids;
  }

  /** Linha avulsa (contorno anatômico, sulco do rosto): [{ p, a, b, t }] — sem casca, só traço e nós. */
  polyline(points, weight = 0.9, { every = 3 } = {}) {
    let prev = -1;
    points.forEach((q, k) => {
      const id = this.vert(q.p, q.a, q.b ?? q.a, q.t ?? 1, weight);
      if (prev >= 0) this.lines.push(prev, id);
      if (k % every === 0) this.points.push(id);
      prev = id;
    });
  }

  /**
   * Membro contínuo ao longo de uma cadeia de ossos — sem emendas nas juntas: perto de cada junta o vértice
   * mistura os dois ossos (dobra suave). ``parts``: [{ bone, len, rings, profile(t) → [rx, rz], shift? }].
   * ``capStart``/``capEnd`` fecham as pontas em cúpula (ombro, ponta dos dedos); ``dir`` = sentido do osso.
   */
  chain(parts, { segs = 14, blend = 0.2, capStart = 0, capEnd = 0, startBone = null, endBone = null, dir = -1,
                 fadeStart = 0, fadeEnd = 0, accent = 3, ringEvery = 2, meridianEvery = 2, pointEvery = 3 } = {}) {
    const idx = parts.map((p) => this.rig.index(p.bone));
    const before = startBone ? this.rig.index(startBone) : null, after = endBone ? this.rig.index(endBone) : null;
    const total = parts.reduce((s, p) => s + p.len, 0);
    const rows = [];
    let n = 0;
    const ring = (k, t, scale = 1, extra = 0) => {
      const part = parts[k];
      const tt = clamp(t, 0, 1);
      const [rx, rz] = part.profile(tt);
      let a = idx[k], b = idx[k], w = 1;
      if (tt < blend && (k > 0 || before !== null)) { b = k > 0 ? idx[k - 1] : before; w = 0.5 + 0.5 * smooth(0, blend, tt); }
      else if (tt > 1 - blend && (k < parts.length - 1 || after !== null)) {
        b = k < parts.length - 1 ? idx[k + 1] : after; w = 0.5 + 0.5 * (1 - smooth(1 - blend, 1, tt));
      }
      const along = (parts.slice(0, k).reduce((s, p) => s + p.len, 0) + tt * part.len) / total;
      const fade = (fadeStart > 0 ? 0.25 + 0.75 * smooth(0, fadeStart, along) : 1) *
                   (fadeEnd > 0 ? 0.15 + 0.85 * (1 - smooth(1 - fadeEnd, 1, along)) : 1);
      const weight = (n++ % accent === 0 ? 0.9 : 0.55) * fade;
      const row = [];
      for (let j = 0; j < segs; j++) {
        const ang = (j / segs) * Math.PI * 2;
        let x = Math.cos(ang) * rx * scale, z = Math.sin(ang) * rz * scale;
        if (part.shift) { const sh = part.shift(tt, ang); x += sh[0] * scale; z += sh[1] * scale; }
        row.push(this.vert(this.rig.toModel(part.bone, x, dir * tt * part.len + extra, z), a, b, w, weight));
      }
      rows.push(row);
    };
    const CAP = [1, 0.8, 0.55, 0.28];
    if (capStart) for (const f of CAP) ring(0, 0, Math.sqrt(Math.max(0, 1 - f * f)) || 0.02, -dir * capStart * f);
    parts.forEach((part, k) => {
      for (let i = k === 0 ? 0 : 1; i < part.rings; i++) ring(k, i / (part.rings - 1));
    });
    if (capEnd) for (const f of [...CAP].reverse()) ring(parts.length - 1, 1, Math.sqrt(Math.max(0, 1 - f * f)) || 0.02, dir * capEnd * f);
    this.grid(rows, { ringEvery, meridianEvery, pointEvery });
    return rows;
  }

  build(u) {
    const mk = (indices) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
      g.setAttribute('skinA', new THREE.Float32BufferAttribute(this.a, 1));
      g.setAttribute('skinB', new THREE.Float32BufferAttribute(this.b, 1));
      g.setAttribute('skinW', new THREE.Float32BufferAttribute(this.w, 1));
      g.setAttribute('weight', new THREE.Float32BufferAttribute(this.weight, 1));
      if (indices) g.setIndex(indices);
      g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.95, 0), 1.6);
      return disposer.track(g);
    };
    const shellGeo = mk(this.tris);
    shellGeo.computeVertexNormals();
    const lines = new THREE.LineSegments(mk(this.lines), holoLineMaterial(u, { opacity: 0.44, skinned: true }));
    const shell = new THREE.Mesh(shellGeo, holoShellMaterial(u, { opacity: 0.36, skinned: true }));
    const pts = new THREE.Points(mk(this.points), holoPointsMaterial(u, { size: 0.010, opacity: 0.75, skinned: true }));
    for (const o of [lines, shell, pts]) o.frustumCulled = false;
    shell.renderOrder = 1; lines.renderOrder = 2; pts.renderOrder = 3;
    return { lines, shell, points: pts,
             counts: { vertices: this.pos.length / 3, lines: this.lines.length / 2, triangles: this.tris.length / 3 } };
  }
}

// ---------------------------------------------------------------- o corpo
function buildSkeleton(rig) {
  const B = (n, p, pos, rot) => rig.bone(n, p, pos, rot);
  B('hips', null, [0, 0.95, 0]);
  B('spine', 'hips', [0, 0.12, 0]);
  B('chest', 'spine', [0, 0.18, 0]);
  B('neck', 'chest', [0, 0.27, -0.012]);
  B('head', 'neck', [0, 0.172, 0.014]);
  B('jaw', 'head', [0, HINGE_Y * HEAD_SCALE, HINGE_Z * HEAD_SCALE]);
  B('mouth', 'head', [0, Y_MOUTH * HEAD_SCALE, 0.07]);
  for (const [side, s] of [['L', 1], ['R', -1]]) {
    const ex = Math.sin(EYE_THETA) * 0.71 * HEAD_SCALE * s, ez = Math.cos(EYE_THETA) * 0.71 * HEAD_SCALE;
    B('eye' + side, 'head', [ex, Y_EYE * HEAD_SCALE, ez]);
    B('brow' + side, 'head', [ex * 1.05, (Y_BROW + 0.04) * HEAD_SCALE, ez * 1.04]);   // expressões
    B('clav' + side, 'chest', [0.03 * s, 0.19, -0.005]);
    B('arm' + side, 'clav' + side, [0.155 * s, 0.015, -0.01], [0, 0, 0.13 * s]);
    B('fore' + side, 'arm' + side, [0, -0.30, 0], [-0.12, 0, 0]);
    B('hand' + side, 'fore' + side, [0, -0.26, 0], [0, 0, -0.04 * s]);
    const fingers = { index: [0.030, [0.040, 0.024, 0.020], 0.0082], middle: [0.010, [0.045, 0.028, 0.022], 0.0085],
                      ring: [-0.010, [0.042, 0.026, 0.021], 0.0080], pinky: [-0.028, [0.033, 0.019, 0.017], 0.0070] };
    for (const [f, [z, lens]] of Object.entries(fingers)) {
      B(`${f}1${side}`, 'hand' + side, [0, -0.095, z], [0, 0, 0.02 * s * (z < 0 ? 1 : -1)]);
      B(`${f}2${side}`, `${f}1${side}`, [0, -lens[0], 0]);
      B(`${f}3${side}`, `${f}2${side}`, [0, -lens[1], 0]);
    }
    B('thumb1' + side, 'hand' + side, [-0.004 * s, -0.018, 0.030], [0.75, 0, -0.30 * s]);
    B('thumb2' + side, 'thumb1' + side, [0, -0.040, 0]);
    B('thumb3' + side, 'thumb2' + side, [0, -0.032, 0]);
    B('thigh' + side, 'hips', [0.092 * s, -0.035, 0], [0, 0, 0.025 * s]);
    B('shin' + side, 'thigh' + side, [0, -0.43, 0], [0.03, 0, 0]);
    B('foot' + side, 'shin' + side, [0, -0.41, 0], [-0.03, 0, -0.025 * s]);
    B('toes' + side, 'foot' + side, [0, -0.062, 0.135]);
  }
  rig.bind();
  return { fingers: ['index', 'middle', 'ring', 'pinky'] };
}

function interp(keys, x) {           // Catmull-Rom sobre [[x, v], ...]
  if (x <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) {
    const [x1, v1] = keys[i], [x2, v2] = keys[i + 1];
    if (x <= x2) {
      const v0 = (keys[i - 1] || keys[i])[1], v3 = (keys[i + 2] || keys[i + 1])[1];
      const t = (x - x1) / (x2 - x1), t2 = t * t, t3 = t2 * t;
      return 0.5 * ((2 * v1) + (-v0 + v2) * t + (2 * v0 - 5 * v1 + 4 * v2 - v3) * t2 + (-v0 + 3 * v1 - 3 * v2 + v3) * t3);
    }
  }
  return keys[keys.length - 1][1];
}

const TORSO_W = [[0.80, 0.150], [0.90, 0.168], [0.98, 0.160], [1.06, 0.140], [1.12, 0.139], [1.20, 0.150],
                 [1.29, 0.163], [1.38, 0.170], [1.44, 0.168], [1.49, 0.132], [1.52, 0.085], [1.545, 0.058]];
const TORSO_D = [[0.80, 0.098], [0.90, 0.110], [0.98, 0.104], [1.06, 0.092], [1.14, 0.095], [1.22, 0.104],
                 [1.30, 0.114], [1.38, 0.110], [1.445, 0.095], [1.49, 0.075], [1.52, 0.062], [1.545, 0.052]];

/** Ponto da superfície do tronco: altura ``y`` (m) e ângulo ``ang`` (π/2 = frente, 3π/2 = costas). Devolve a
 *  posição no modelo e os ossos que o seguem (mesma função da malha, das linhas anatômicas e dos circuitos). */
function torsoPoint(rig, y, ang, lift = 0) {
  const bones = { hips: rig.index('hips'), spine: rig.index('spine'), chest: rig.index('chest'), neck: rig.index('neck') };
  const w = interp(TORSO_W, y), d = interp(TORSO_D, y);
  const n = 2.15 + 0.35 * gauss(y, 1.30, 0.10);              // seções arredondadas; peito um pouco mais cheio
  let a, b, t;
  if (y < 1.04) { a = bones.hips; b = bones.spine; t = 1 - smooth(0.98, 1.08, y); }
  else if (y < 1.26) { a = bones.spine; b = bones.chest; t = 1 - smooth(1.18, 1.28, y); }
  else if (y < 1.49) { a = bones.chest; b = bones.neck; t = 1 - smooth(1.47, 1.53, y); }
  else { a = bones.neck; b = bones.chest; t = smooth(1.48, 1.53, y); }
  const ca = Math.cos(ang), sa = Math.sin(ang);
  let x = w * Math.sign(ca) * Math.pow(Math.abs(ca), 2 / n);
  let z = d * Math.sign(sa) * Math.pow(Math.abs(sa), 2 / n);
  if (sa > 0) {                                                // frente: peitoral e abdômen
    z += 0.014 * gauss(y, 1.31, 0.05) * gauss(Math.abs(x), 0.075, 0.05);
    z += 0.006 * gauss(y, 1.08, 0.08) * gauss(x, 0, 0.06);
  } else {                                                     // costas: escápulas e glúteos
    z -= 0.010 * gauss(y, 1.36, 0.06) * gauss(Math.abs(x), 0.08, 0.05);
    z -= 0.018 * gauss(y, 0.86, 0.06) * gauss(Math.abs(x), 0.07, 0.06);
  }
  const len = Math.hypot(x, z) || 1;
  return { p: new THREE.Vector3(x + x / len * lift, y, z + z / len * lift), a, b, t };
}

function buildTorso(geo, rig) {
  const rings = 30, segs = 28, ids = [];
  for (let i = 0; i < rings; i++) {
    const y = lerp(0.80, 1.545, i / (rings - 1));
    const row = [];
    for (let j = 0; j < segs; j++) {
      const q = torsoPoint(rig, y, (j / segs) * Math.PI * 2);
      const weight = ((i % 6 === 0) ? 0.75 : 0.42) * (0.3 + 0.7 * smooth(0.80, 0.9, y));
      row.push(geo.vert(q.p, q.a, q.b, q.t, weight));
    }
    ids.push(row);
  }
  // malha mais rala: a anatomia fica a cargo das linhas de contorno e dos circuitos
  geo.grid(ids, { pointEvery: 4, meridianEvery: 2, ringEvery: 3 });
}

/** Contornos anatômicos do tronco (esterno, peitorais, clavículas, abdômen, linhas em V, coluna, escápulas):
 *  as linhas seguem a forma do corpo em vez de anéis horizontais. ``u`` = ângulo a partir da frente. */
function buildAnatomy(geo, rig) {
  const at = (y, u, lift = 0.0015) => torsoPoint(rig, y, Math.PI / 2 - u, lift);
  const curve = (pts, weight = 0.95, steps = 10) => {
    const out = [];
    for (let k = 0; k < pts.length - 1; k++) {
      for (let s = 0; s < steps; s++) {
        const f = s / steps, [y0, u0] = pts[k], [y1, u1] = pts[k + 1];
        out.push(at(lerp(y0, y1, f), lerp(u0, u1, f)));
      }
    }
    const last = pts[pts.length - 1];
    out.push(at(last[0], last[1]));
    geo.polyline(out, weight);
  };
  const mirror = (pts, weight) => { curve(pts, weight); curve(pts.map(([y, u]) => [y, -u]), weight); };
  curve([[1.17, 0], [1.30, 0], [1.44, 0]], 0.9);                                      // esterno
  mirror([[1.268, 0.04], [1.252, 0.28], [1.27, 0.52], [1.32, 0.76], [1.39, 0.96]]);    // borda do peitoral
  mirror([[1.47, 0.06], [1.462, 0.38], [1.45, 0.78], [1.44, 1.06]], 0.85);             // clavícula
  curve([[0.97, 0], [1.10, 0], [1.24, 0]], 0.8);                                       // linha alba
  mirror([[0.99, 0.24], [1.10, 0.25], [1.23, 0.24]], 0.8);                             // reto abdominal
  for (const y of [1.075, 1.135, 1.195]) curve([[y, -0.24], [y + 0.004, 0], [y, 0.24]], 0.7, 8);
  mirror([[1.07, 0.6], [0.99, 0.42], [0.905, 0.14]], 0.85);                            // linhas em V (oblíquos)
  for (const [y, u] of [[1.24, 0.9], [1.19, 0.95], [1.14, 1.0]]) mirror([[y, u], [y - 0.03, u + 0.16]], 0.6);  // serrátil
  curve([[0.93, Math.PI], [1.2, Math.PI], [1.49, Math.PI]], 0.8);                      // coluna
  mirror([[1.44, Math.PI - 0.25], [1.40, Math.PI - 0.75], [1.31, Math.PI - 0.62], [1.27, Math.PI - 0.3],
          [1.36, Math.PI - 0.18], [1.44, Math.PI - 0.25]], 0.65);                      // escápulas
}

/** Trilhas de circuito no tronco: caminhos em ângulo reto (determinísticos) com pulsos que correm por elas. */
function buildCircuits(rig, u) {
  const pos = [], a = [], b = [], w = [], weight = [], along = [], idx = [];
  let seed = 7;
  const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const push = (q, dist) => {
    pos.push(q.p.x, q.p.y, q.p.z); a.push(q.a); b.push(q.b); w.push(q.t); weight.push(0.95); along.push(dist);
    return pos.length / 3 - 1;
  };
  const starts = [[1.40, 0.18], [1.36, 0.5], [1.30, 0.32], [1.22, 0.12], [1.12, 0.36], [1.02, 0.18], [1.42, 0.85],
                  [1.18, 0.7], [1.34, Math.PI - 0.12], [1.15, Math.PI - 0.4], [1.0, Math.PI - 0.2]];
  for (const [y0, u0] of starts) {
    for (const side of [1, -1]) {
      let y = y0, uu = u0, dist = 0, vertical = rand() < 0.5;
      let prev = push(torsoPoint(rig, y, Math.PI / 2 - side * uu, 0.002), dist);
      let last = new THREE.Vector3().copy(torsoPoint(rig, y, Math.PI / 2 - side * uu, 0.002).p);
      for (let leg = 0; leg < 4; leg++) {
        const steps = 4 + Math.floor(rand() * 6);
        const dy = (rand() < 0.5 ? -1 : 1) * 0.012, du = (rand() < 0.5 ? -1 : 1) * 0.045;
        for (let k = 0; k < steps; k++) {
          if (vertical) y = clamp(y + dy, 0.92, 1.46); else uu = clamp(uu + du, 0.04, Math.PI - 0.04);
          const q = torsoPoint(rig, y, Math.PI / 2 - side * uu, 0.002);
          dist += q.p.distanceTo(last); last.copy(q.p);
          const id = push(q, dist);
          idx.push(prev, id); prev = id;
        }
        vertical = !vertical;
      }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('skinA', new THREE.Float32BufferAttribute(a, 1));
  g.setAttribute('skinB', new THREE.Float32BufferAttribute(b, 1));
  g.setAttribute('skinW', new THREE.Float32BufferAttribute(w, 1));
  g.setAttribute('weight', new THREE.Float32BufferAttribute(weight, 1));
  g.setAttribute('along', new THREE.Float32BufferAttribute(along, 1));
  g.setIndex(idx);
  disposer.track(g);
  const lines = new THREE.LineSegments(g, holoCircuitMaterial(u, { opacity: 0.85 }));
  lines.frustumCulled = false;
  lines.renderOrder = 2;
  return lines;
}

function buildHead(geo, rig) {
  const head = rig.index('head'), jaw = rig.index('jaw');
  const front = 30, back = 14, thetas = [];
  for (let i = 0; i < front; i++) thetas.push(lerp(-1.25, 1.25, i / (front - 1)));
  for (let i = 1; i <= back; i++) { let t = lerp(1.25, Math.PI * 2 - 1.25, i / (back + 1)); if (t > Math.PI) t -= Math.PI * 2; thetas.push(t); }
  thetas.sort((p, q) => p - q);
  const ys = [];
  for (let i = 0; i < 30; i++) ys.push(lerp(-1.04, 0.995, Math.pow(i / 29, 0.95)));
  const ids = [];
  for (const y of ys) {
    const row = [];
    for (const th of thetas) {
      const r = headRadius(th, y);
      const hx = r * Math.sin(th), hz = r * Math.cos(th);
      const p = rig.toModel('head', hx * HEAD_SCALE, y * HEAD_SCALE, hz * HEAD_SCALE);
      const jw = clamp((Y_MOUTH + 0.01 - y) / 0.10, 0, 1) * clamp(1 - (Math.abs(hx) - 0.45) / 0.25, 0, 1);
      const accent = (Math.abs(th) < 0.5 && y < 0.3 && y > -0.95) ? 0.5 : 0.36;   // grade discreta: os sulcos falam mais alto
      row.push(jw > 0.01 ? geo.vert(p, jaw, head, jw, accent) : geo.vert(p, head, head, 1, accent));
    }
    ids.push(row);
  }
  geo.grid(ids, { pointEvery: 7, meridianEvery: 2, ringEvery: 2 });
  // sulcos do rosto de androide: placas e cristas que seguem a forma (não anéis)
  const at = (th, y) => {
    const r = headRadius(th, y) + 0.012;
    const hx = r * Math.sin(th), hz = r * Math.cos(th);
    const p = rig.toModel('head', hx * HEAD_SCALE, y * HEAD_SCALE, hz * HEAD_SCALE);
    const jw = clamp((Y_MOUTH + 0.01 - y) / 0.10, 0, 1) * clamp(1 - (Math.abs(hx) - 0.45) / 0.25, 0, 1);
    return jw > 0.01 ? { p, a: jaw, b: head, t: jw } : { p, a: head, b: head, t: 1 };
  };
  const seam = (pts, weight = 1.0, steps = 8) => {
    const out = [];
    for (let k = 0; k < pts.length - 1; k++) {
      for (let q = 0; q < steps; q++) {
        const f = q / steps;
        out.push(at(lerp(pts[k][0], pts[k + 1][0], f), lerp(pts[k][1], pts[k + 1][1], f)));
      }
    }
    out.push(at(...pts[pts.length - 1]));
    geo.polyline(out, weight, { every: 8 });
  };
  const both = (pts, weight) => { seam(pts, weight); seam(pts.map(([th, y]) => [-th, y]), weight); };
  seam([[0, 0.92], [0, 0.6], [0, 0.32]], 0.9);                                       // crista central da testa
  both([[0.07, 0.30], [0.25, 0.22], [0.52, 0.16], [0.82, 0.08]]);                   // arco das sobrancelhas
  both([[0.16, 0.34], [0.34, 0.5], [0.6, 0.72], [1.0, 0.82]], 0.75);                // placa frontal
  both([[0.55, -0.06], [0.6, -0.3], [0.52, -0.55], [0.4, -0.84]], 0.9);             // sulco da maçã ao queixo
  both([[0.2, -0.12], [0.36, -0.13], [0.5, -0.08]], 0.8);                            // olheira (placa sob o olho)
  both([[0.13, -0.40], [0.2, -0.52], [0.25, -0.66]], 0.85);                          // sulco nasolabial
  both([[1.35, -0.3], [1.0, -0.62], [0.6, -0.88], [0.2, -0.99], [0.0, -1.0]], 0.9);  // linha da mandíbula
  both([[0.95, 0.35], [1.3, 0.55], [1.7, 0.62], [2.3, 0.55]], 0.7);                  // têmporas
  // olhos (íris em anel), lábios e linhas de relevo do rosto
  for (const side of ['L', 'R']) {
    const e = rig.index('eye' + side), ring = [];
    for (let j = 0; j < 14; j++) {
      const a = (j / 14) * Math.PI * 2;
      ring.push(geo.vert(rig.toModel('eye' + side, Math.cos(a) * 0.0105, Math.sin(a) * 0.0068, 0.004), e, e, 1, 1.0));
    }
    const pupil = [];
    for (let j = 0; j < 8; j++) {
      const a = (j / 8) * Math.PI * 2;
      pupil.push(geo.vert(rig.toModel('eye' + side, Math.cos(a) * 0.004, Math.sin(a) * 0.004, 0.005), e, e, 1, 1.0));
    }
    geo.grid([ring], { shell: false, pointEvery: 1 });
    geo.grid([pupil], { shell: false, pointEvery: 99 });
  }
  const mouth = rig.index('mouth');
  const lip = (yOff, bone, curve) => {
    const row = [];
    for (let j = 0; j <= 12; j++) {
      const x = lerp(-0.026, 0.026, j / 12);
      const th = Math.asin(clamp(x / (0.80 * HEAD_SCALE), -1, 1));
      const y = Y_MOUTH + yOff + curve * (1 - Math.pow(x / 0.026, 2));
      const r = headRadius(th, y) * HEAD_SCALE + 0.0015;
      const p = rig.toModel('head', r * Math.sin(th), y * HEAD_SCALE, r * Math.cos(th));
      row.push(bone === jaw ? geo.vert(p, jaw, head, 0.95, 1.0) : geo.vert(p, mouth, head, 1, 1.0));
    }
    return row;
  };
  geo.grid([lip(0.012, mouth, 0.008)], { closed: false, shell: false, pointEvery: 4 });
  geo.grid([lip(-0.020, jaw, -0.010)], { closed: false, shell: false, pointEvery: 4 });
}

function buildLimbs(geo, rig, info) {
  // pescoço: sobe do peito até dentro da cabeça (antes descia para dentro do tórax e aparecia como um bloco)
  geo.chain([{ bone: 'neck', len: 0.16, rings: 9, profile: (t) => [0.058 - 0.013 * t, 0.063 - 0.016 * t],
               shift: (t, a) => [0, -0.006 * t * Math.max(0, -Math.sin(a))] }],
            { dir: 1, segs: 18, startBone: 'chest', endBone: 'head', fadeStart: 0.35, fadeEnd: 0.4, blend: 0.3,
              ringEvery: 3, meridianEvery: 1 });
  for (const s of ['L', 'R']) {
    const side = s === 'L' ? 1 : -1;
    // braço inteiro numa peça: deltoide em cúpula, bíceps, antebraço afinando até o punho e a palma
    geo.chain([
      { bone: 'arm' + s, len: 0.30, rings: 12,
        profile: (t) => [0.051 - 0.012 * t + 0.006 * gauss(t, 0.08, 0.14), 0.049 - 0.009 * t + 0.006 * gauss(t, 0.45, 0.2)] },
      { bone: 'fore' + s, len: 0.26, rings: 11,
        profile: (t) => [0.040 + 0.004 * gauss(t, 0.2, 0.2) - 0.021 * smooth(0, 1, t), 0.041 + 0.004 * gauss(t, 0.2, 0.2) - 0.014 * smooth(0, 1, t)] },
      { bone: 'hand' + s, len: 0.098, rings: 6,
        profile: (t) => [0.0175 - 0.003 * t, 0.028 + 0.014 * smooth(0, 0.7, t)] },
    ], { segs: 16, startBone: 'clav' + s, capStart: 0.05, capEnd: 0.012 });
    const lens = { index: [0.040, 0.024, 0.020], middle: [0.045, 0.028, 0.022], ring: [0.042, 0.026, 0.021],
                   pinky: [0.033, 0.019, 0.017] };
    const radius = { index: 0.0082, middle: 0.0085, ring: 0.0080, pinky: 0.0070 };
    for (const f of info.fingers) {
      const r0 = radius[f];
      geo.chain([1, 2, 3].map((k) => ({ bone: `${f}${k}${s}`, len: lens[f][k - 1], rings: 3,
        profile: (t) => { const r = r0 * (1 - 0.1 * (k - 1 + t)); return [r, r * 0.88]; } })),
        { segs: 8, startBone: 'hand' + s, capEnd: r0 * 0.8, blend: 0.3, accent: 99, meridianEvery: 2, pointEvery: 4 });
    }
    geo.chain([[0.040, 0.0120], [0.032, 0.0098], [0.026, 0.0088]].map(([len, r0], i) => ({ bone: `thumb${i + 1}${s}`, len, rings: 3,
      profile: (t) => [r0 * (1 - 0.08 * t), r0 * 0.88] })),
      { segs: 8, startBone: 'hand' + s, capEnd: 0.007, blend: 0.3, accent: 99, meridianEvery: 2, pointEvery: 4 });
    // perna inteira: coxa (com quadríceps à frente) e canela (panturrilha atrás), contínuas no joelho
    geo.chain([
      { bone: 'thigh' + s, len: 0.43, rings: 15,
        profile: (t) => [0.080 - 0.028 * t + 0.008 * gauss(t, 0.3, 0.25), 0.084 - 0.032 * t + 0.010 * gauss(t, 0.32, 0.22)],
        shift: (t, a) => [0, 0.010 * gauss(t, 0.35, 0.25) * Math.max(0, Math.sin(a))] },
      { bone: 'shin' + s, len: 0.41, rings: 14,
        profile: (t) => [0.051 - 0.019 * t + 0.004 * gauss(t, 0.25, 0.2), 0.052 - 0.018 * t + 0.010 * gauss(t, 0.27, 0.16)],
        shift: (t, a) => [0, -0.008 * gauss(t, 0.27, 0.16) * Math.max(0, -Math.sin(a))] },
    ], { segs: 18, startBone: 'hips', endBone: 'foot' + s, fadeStart: 0.12, blend: 0.16 });
    // pé: seções ao longo de +Z, sola plana; o terço da frente segue o osso dos dedos
    const foot = rig.index('foot' + s), toes = rig.index('toes' + s), shin = rig.index('shin' + s);
    const ids = [];
    const rings = 12, segs = 14;
    for (let i = 0; i < rings; i++) {
      const t = i / (rings - 1), z = lerp(-0.065, 0.205, t);
      const halfW = 0.030 + 0.020 * smooth(0, 0.6, t) - 0.012 * smooth(0.85, 1, t);
      const height = 0.075 * (1 - smooth(0.2, 0.95, t)) + 0.020;
      const row = [];
      for (let j = 0; j < segs; j++) {
        const a = (j / segs) * Math.PI * 2;
        const x = Math.cos(a) * halfW * (side > 0 ? 1 : 1);
        const y = -0.080 + Math.max(0, (0.5 + 0.5 * Math.sin(a)) * height);
        const p = rig.toModel('foot' + s, x + 0.008 * side * smooth(0.5, 1, t), y, z);
        const toW = smooth(0.62, 0.76, t);
        const wt = i % 3 === 0 ? 0.9 : 0.55;
        row.push(toW > 0.01 ? geo.vert(p, toes, foot, toW, wt) : geo.vert(p, foot, shin, 0.5 + 0.5 * smooth(0, 0.25, t), wt));
      }
      ids.push(row);
    }
    geo.grid(ids, { pointEvery: 3, meridianEvery: 2 });
  }
}

/** Esqueleto interno: os ossos como linhas tênues e as articulações como pontos. */
function buildSkeletonLines(rig, u) {
  const pos = [], a = [], b = [], w = [], weight = [], idx = [];
  for (const bone of rig.bones) {
    const parent = bone.parent;
    if (!parent || parent === rig.root || /eye|mouth|jaw/.test(bone.name)) continue;
    const i0 = parent.userData.index, i1 = bone.userData.index;
    const p0 = new THREE.Vector3().setFromMatrixPosition(rig.bindModel[i0]);
    const p1 = new THREE.Vector3().setFromMatrixPosition(rig.bindModel[i1]);
    pos.push(p0.x, p0.y, p0.z, p1.x, p1.y, p1.z);
    a.push(i0, i1); b.push(i0, i1); w.push(1, 1); weight.push(0.5, 0.5);
    idx.push(pos.length / 3 - 2, pos.length / 3 - 1);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('skinA', new THREE.Float32BufferAttribute(a, 1));
  g.setAttribute('skinB', new THREE.Float32BufferAttribute(b, 1));
  g.setAttribute('skinW', new THREE.Float32BufferAttribute(w, 1));
  g.setAttribute('weight', new THREE.Float32BufferAttribute(weight, 1));
  g.setIndex(idx);
  disposer.track(g);
  const lines = new THREE.LineSegments(g, holoLineMaterial(u, { opacity: 0.32, skinned: true }));
  const joints = new THREE.Points(g, holoPointsMaterial(u, { size: 0.012, opacity: 0.6, skinned: true }));
  for (const o of [lines, joints]) o.frustumCulled = false;
  return [lines, joints];
}

// ---------------------------------------------------------------- plataforma de projeção
class Projector {
  constructor(group, particleScale = 1) {
    this.group = new THREE.Group();
    group.add(this.group);
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.95, 1.05, 0.10, 64),
      disposer.track(new THREE.MeshStandardMaterial({ color: 0x0c1726, metalness: 0.85, roughness: 0.35 })));
    base.position.y = 0.05;
    const lip = new THREE.Mesh(new THREE.TorusGeometry(0.97, 0.012, 8, 96), glowMaterial(PALETTE.cyan, 0.65));
    lip.rotation.x = Math.PI / 2; lip.position.y = 0.102;
    this.lip = lip;
    this.group.add(base, lip);
    disposer.track(base.geometry); disposer.track(lip.geometry);
    // anéis gravados no topo: segmentos e marcas de telemetria (textura feita aqui)
    const ringTex = canvasTexture(1024, 1024, (g, w, h) => {
      g.translate(w / 2, h / 2);
      const ring = (r, width, alpha, dash = null) => {
        g.beginPath(); g.setLineDash(dash || []); g.lineWidth = width; g.strokeStyle = `rgba(150,235,255,${alpha})`;
        g.arc(0, 0, r, 0, Math.PI * 2); g.stroke();
      };
      ring(500, 3, 0.65); ring(470, 1.5, 0.35, [24, 10]); ring(380, 2, 0.5); ring(352, 10, 0.12, [4, 14]);
      ring(250, 1.5, 0.45, [60, 20]); ring(150, 2, 0.4); ring(90, 1, 0.3, [6, 6]);
      for (let i = 0; i < 120; i++) {
        const a = (i / 120) * Math.PI * 2, r0 = i % 10 === 0 ? 400 : 420;
        g.strokeStyle = `rgba(150,235,255,${i % 10 === 0 ? 0.7 : 0.3})`; g.lineWidth = i % 10 === 0 ? 3 : 1.4;
        g.setLineDash([]); g.beginPath(); g.moveTo(Math.cos(a) * r0, Math.sin(a) * r0); g.lineTo(Math.cos(a) * 440, Math.sin(a) * 440); g.stroke();
      }
    }, { srgb: true });
    this.disc = new THREE.Mesh(new THREE.CircleGeometry(0.95, 96), glowMaterial(PALETTE.cyan, 0.55, { map: ringTex }));
    this.disc.rotation.x = -Math.PI / 2; this.disc.position.y = 0.103;
    this.inner = new THREE.Mesh(new THREE.RingGeometry(0.30, 0.62, 96, 1, 0, Math.PI * 1.4), glowMaterial(PALETTE.electric, 0.09));
    this.inner.rotation.x = -Math.PI / 2; this.inner.position.y = 0.106;
    this.group.add(this.disc, this.inner);
    disposer.track(this.disc.geometry); disposer.track(this.inner.geometry);
    // feixe de projeção: cone aditivo que esmaece para cima
    const beamMat = disposer.track(new THREE.ShaderMaterial({
      uniforms: { uColor: { value: new THREE.Color(PALETTE.cyan) }, uTime: { value: 0 }, uPower: { value: 0.55 } },
      vertexShader: 'varying vec2 vUv; varying vec3 vN; varying vec3 vV; void main(){ vUv=uv; vN=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(position,1.0); vV=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }',
      fragmentShader: 'uniform vec3 uColor; uniform float uTime; uniform float uPower; varying vec2 vUv; varying vec3 vN; varying vec3 vV; void main(){ float fade=pow(1.0-vUv.y,2.2); float side=pow(1.0-abs(dot(vN,vV)),2.0); float streak=0.7+0.3*sin(vUv.x*80.0+uTime*0.7); gl_FragColor=vec4(uColor, fade*(0.03+0.22*side)*streak*uPower); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    this.beam = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.86, 2.2, 64, 1, true), beamMat);
    this.beam.position.y = 0.105 + 1.1;
    this.group.add(this.beam);
    disposer.track(this.beam.geometry);
    this.beamMat = beamMat;
    // partículas que sobem no feixe (movimento todo na GPU)
    this.maxParticles = 420;
    const seeds = new Float32Array(this.maxParticles * 3);
    for (let i = 0; i < this.maxParticles; i++) { seeds[i * 3] = Math.random(); seeds[i * 3 + 1] = Math.random(); seeds[i * 3 + 2] = Math.random(); }
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(this.maxParticles * 3), 3));
    pg.setAttribute('seed', new THREE.Float32BufferAttribute(seeds, 3));
    disposer.track(pg);
    this.pMat = disposer.track(new THREE.ShaderMaterial({
      uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(PALETTE.glow) }, uSpeed: { value: 1 }, map: { value: glowTexture() },
                  uPixel: { value: 1 } },
      vertexShader: 'attribute vec3 seed; uniform float uTime; uniform float uSpeed; uniform float uPixel; varying float vA; void main(){ float h=fract(seed.y+uTime*0.06*uSpeed*(0.5+seed.z)); float r=mix(0.85,0.55,h)*sqrt(seed.x); float a=seed.z*6.2831+uTime*0.2*(seed.x-0.5); vec3 p=vec3(cos(a)*r, 0.12+h*2.1, sin(a)*r); vA=sin(h*3.1416)*(0.4+0.6*seed.x); vec4 mv=modelViewMatrix*vec4(p,1.0); gl_PointSize=uPixel*(3.0+5.0*seed.z)*(6.0/max(-mv.z,0.1)); gl_Position=projectionMatrix*mv; }',
      fragmentShader: 'uniform vec3 uColor; uniform sampler2D map; varying float vA; void main(){ vec4 t=texture2D(map,gl_PointCoord); gl_FragColor=vec4(uColor, t.a*vA*0.8); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.particles = new THREE.Points(pg, this.pMat);
    this.particles.frustumCulled = false;
    this.group.add(this.particles);
    // ondas de pulso (escuta/fala): anéis que se expandem a partir da base
    this.waves = [];
    for (let i = 0; i < 3; i++) {
      const m = glowMaterial(PALETTE.glow, 0);
      const ringMesh = new THREE.Mesh(new THREE.RingGeometry(0.98, 1.0, 96), m);
      ringMesh.rotation.x = -Math.PI / 2; ringMesh.position.y = 0.11;
      disposer.track(ringMesh.geometry);
      this.group.add(ringMesh);
      this.waves.push({ mesh: ringMesh, t: i / 3 });
    }
    this.setParticleScale(particleScale);
    this.waveRate = 0;
  }

  setParticleScale(s) { this.particles.geometry.setDrawRange(0, Math.round(this.maxParticles * Math.min(1, 0.45 * s + 0.1))); }

  update(dt, time, look) {
    this.disc.rotation.z += dt * 0.03 * look.ring;
    this.inner.rotation.z -= dt * 0.12 * look.ring;
    this.beamMat.uniforms.uTime.value = time;
    this.beamMat.uniforms.uPower.value = lerp(this.beamMat.uniforms.uPower.value, look.beam, 0.08);
    this.beamMat.uniforms.uColor.value.copy(look.color);
    this.lip.material.color.copy(look.color);             // a base acompanha a cor do holograma (e o ULTRON)
    this.disc.material.color.copy(look.color);
    this.inner.material.color.copy(look.color);
    this.pMat.uniforms.uTime.value = time;
    this.pMat.uniforms.uSpeed.value = look.particles;
    for (const w of this.waves) {
      w.t += dt * look.waveRate * 0.6;
      if (w.t > 1) w.t -= 1;
      const s = 0.35 + w.t * 1.4;
      w.mesh.scale.set(s, s, s);
      w.mesh.material.opacity = look.waveRate > 0.01 ? (1 - w.t) * 0.35 * Math.min(1, look.waveRate) : 0;
      w.mesh.material.color.copy(look.color);
    }
  }
}

// ---------------------------------------------------------------- comportamento por estado
// Cada estado REAL vira metas de pose e de luz; tudo é amortecido (nada salta).
const MOTION = {
  aguardando:    { glow: 0.85, look: 1.0, breath: 1.0, sway: 1.0, scan: 0.35, pulse: 0.0, beam: 0.55, ring: 1.0, particles: 1.0, waves: 0 },
  escutando:     { glow: 0.95, look: 0.35, breath: 0.8, sway: 0.5, scan: 0.5, pulse: 0.1, beam: 0.75, ring: 1.4, particles: 1.3, waves: 1.0, lean: 0.05, attend: 1 },
  reconhecendo:  { glow: 1.05, look: 0.25, breath: 0.8, sway: 0.4, scan: 0.7, pulse: 0.2, beam: 0.85, ring: 1.8, particles: 1.5, waves: 1.6, lean: 0.06, attend: 1 },
  pensando:      { glow: 0.95, look: 0.4, breath: 0.9, sway: 0.5, scan: 0.6, pulse: 0.9, beam: 0.7, ring: 1.6, particles: 1.2, waves: 0, think: 1 },
  falando:       { glow: 1.0, look: 0.6, breath: 0.7, sway: 0.6, scan: 0.45, pulse: 0.2, beam: 0.8, ring: 1.3, particles: 1.3, waves: 0.6, talk: 1, attend: 0.6 },
  executando:    { glow: 1.0, look: 0.3, breath: 0.8, sway: 0.4, scan: 0.9, pulse: 1.0, beam: 0.85, ring: 2.2, particles: 1.6, waves: 0, work: 1 },
  tardis:        { glow: 0.95, look: 0.2, breath: 0.8, sway: 0.4, scan: 0.7, pulse: 0.7, beam: 0.75, ring: 1.8, particles: 1.3, waves: 0, tardis: 1 },
  confirmacao:   { glow: 0.95, look: 0.15, breath: 0.9, sway: 0.4, scan: 0.4, pulse: 0.2, beam: 0.7, ring: 0.8, particles: 1.0, waves: 0, attend: 1, ask: 1 },
  alerta:        { glow: 1.1, look: 0.2, breath: 1.0, sway: 0.3, scan: 0.9, pulse: 0.5, beam: 0.9, ring: 1.6, particles: 1.4, waves: 1.2, attend: 1 },
  erro:          { glow: 0.75, look: 0.3, breath: 0.6, sway: 0.2, scan: 0.3, pulse: 0.0, beam: 0.45, ring: 0.5, particles: 0.6, waves: 0, slump: 1, flicker: 0.55 },
  privacidade:   { glow: 0.35, look: 0.15, breath: 0.5, sway: 0.2, scan: 0.0, pulse: 0.0, beam: 0.25, ring: 0.3, particles: 0.3, waves: 0, eyes: 0.06 },
  inicializando: { glow: 0.9, look: 0.0, breath: 0.4, sway: 0.0, scan: 1.0, pulse: 0.4, beam: 0.9, ring: 2.0, particles: 1.5, waves: 0.4 },
};
const KEYS = ['glow', 'look', 'breath', 'sway', 'scan', 'pulse', 'beam', 'ring', 'particles', 'waves', 'lean', 'attend',
              'think', 'talk', 'work', 'tardis', 'ask', 'slump', 'flicker', 'eyes'];

export class Avatar {
  constructor({ particleScale = 1 } = {}) {
    this.group = new THREE.Group();
    this.group.name = 'jarvis-holograma';
    this.root = new THREE.Group();
    this.group.add(this.root);
    this.rig = new Rig(this.root);
    const info = buildSkeleton(this.rig);
    this.u = holoUniforms(PALETTE.cyan);
    this.u.boneTex.value = this.rig.texture;
    const geo = new BodyGeometry(this.rig);
    buildTorso(geo, this.rig);
    buildAnatomy(geo, this.rig);
    buildHead(geo, this.rig);
    buildLimbs(geo, this.rig, info);
    const body = geo.build(this.u);
    this.counts = body.counts;
    // pele SÓLIDA de androide (escreve profundidade: o que está atrás do corpo não aparece através dele); as linhas
    // topológicas ficam por cima, mais discretas, só onde a superfície é visível
    this.skinMat = holoSolidMaterial(this.u, { base: 0x9fd6ea, tint: 0.3, opacity: 0.95, gloss: 0.45, rimPower: 3.0,
                                               rim: 0.55, glow: 0.03 });
    this.skinMat.polygonOffset = true; this.skinMat.polygonOffsetFactor = 1; this.skinMat.polygonOffsetUnits = 2;
    body.shell.material = this.skinMat;
    body.lines.material.uniforms.uOpacity.value = 0.2;
    body.points.material.uniforms.uOpacity.value = 0.3;
    const tools = { BodyGeometry, torsoPoint, headRadius, HEAD_SCALE };
    this.dress = buildClothes(this.rig, this.u, tools);
    this.hair = buildHair(this.rig, this.u, tools);
    this.brows = buildBrows(this.rig, this.u, tools);
    this.counts.hair = this.hair.count;
    this.root.add(body.shell, body.lines, body.points, buildCircuits(this.rig, this.u), ...buildSkeletonLines(this.rig, this.u),
                  ...this.dress.objects, this.hair.cap, this.hair.strands, this.brows);
    this.projector = new Projector(this.group, particleScale);
    this.root.position.y = 0.14;
    this.state = 'inicializando';
    this.p = {};
    for (const k of KEYS) this.p[k] = MOTION.inicializando[k] || 0;
    this.color = new THREE.Color(PALETTE.cyan);
    this.accent = new THREE.Color(PALETTE.glow);
    this.targetColor = new THREE.Color(PALETTE.cyan);
    this.targetAccent = new THREE.Color(PALETTE.glow);
    this.mouth = { open: 0, wide: 0, round: 0, energy: 0 };
    this.voice = 0; this.mic = 0;
    this.boot = 0;
    this.blinkAt = 2.5; this.blink = 0;
    this.gesture = { L: 0, R: 0, targetL: 0, targetR: 0, next: 0 };
    this.lookTarget = new THREE.Vector2(); this.look = new THREE.Vector2(); this.lookNext = 0;
    this.camera = null;
    this.headWorld = new THREE.Vector3();
    this._dataPanels = this._buildDataPanels();
    this._buildFaceLights();
  }

  /** Olhos amendoados luminosos (seguem as pálpebras: escala do osso do olho) e a gema da testa. */
  _buildFaceLights() {
    const almond = new THREE.Shape();
    const w = 0.0115, h = 0.0052;
    almond.moveTo(-w, 0);
    almond.quadraticCurveTo(-w * 0.2, h * 1.9, w, h * 0.25);
    almond.quadraticCurveTo(w * 0.1, -h * 1.6, -w, 0);
    const eyeGeo = disposer.track(new THREE.ShapeGeometry(almond, 10));
    this.eyeMat = glowMaterial(PALETTE.glow, 0.85);
    this.irisMat = disposer.track(new THREE.SpriteMaterial({ map: glowTexture(), color: 0xffffff, transparent: true,
                                                              opacity: 0.9, blending: THREE.AdditiveBlending,
                                                              depthWrite: false }));
    this.irises = [];
    for (const side of ['L', 'R']) {
      const bone = this.rig.map['eye' + side];
      const eye = new THREE.Mesh(eyeGeo, this.eyeMat);
      eye.position.z = 0.0045;
      if (side === 'R') eye.scale.x = -1;
      const iris = new THREE.Sprite(this.irisMat);
      iris.scale.setScalar(0.011); iris.position.z = 0.006;
      bone.add(eye, iris);
      this.irises.push(iris);
    }
    // boca: abertura escura que aparece com a mandíbula (a fala real abre a boca de verdade)
    const mouthShape = new THREE.Shape();
    mouthShape.absellipse(0, 0, 0.019, 0.006, 0, Math.PI * 2, false, 0);
    this.mouthHole = new THREE.Mesh(disposer.track(new THREE.ShapeGeometry(mouthShape, 20)),
      disposer.track(new THREE.MeshBasicMaterial({ color: 0x02070d, transparent: true, opacity: 0, depthWrite: false })));
    this.mouthHole.position.set(0, -0.0045, 0.0035);
    this.mouthHole.renderOrder = 6;
    this.rig.map.mouth.add(this.mouthHole);
    const yGem = 0.42;
    const gem = new THREE.Mesh(disposer.track(new THREE.OctahedronGeometry(0.0065, 0)), glowMaterial(PALETTE.glow, 0.95));
    gem.scale.set(0.8, 1.25, 0.45);
    gem.position.set(0, yGem * HEAD_SCALE, headRadius(0, yGem) * HEAD_SCALE + 0.002);
    const halo = new THREE.Sprite(disposer.track(new THREE.SpriteMaterial({ map: glowTexture(), color: PALETTE.glow,
      transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending, depthWrite: false })));
    halo.scale.setScalar(0.04); halo.position.copy(gem.position).add(new THREE.Vector3(0, 0, 0.002));
    this.rig.map.head.add(gem, halo);
    this.gem = { gem, halo };
  }

  setParticleScale(s) { this.projector.setParticleScale(s); }

  /** Metas vindas do JARVIS: estado resolvido, cores reais do estado, trilha labial e níveis de áudio. */
  apply(sig) {
    if (sig.state && MOTION[sig.state]) this.state = sig.state;
    if (sig.rgb) this.targetColor.setRGB(sig.rgb[0] / 255, sig.rgb[1] / 255, sig.rgb[2] / 255, THREE.SRGBColorSpace);
    if (sig.iris) this.targetAccent.setRGB(sig.iris[0] / 255, sig.iris[1] / 255, sig.iris[2] / 255, THREE.SRGBColorSpace);
    if (sig.mouth) this.mouth = sig.mouth;
    if (typeof sig.out_level === 'number') this.voice = sig.out_level;
    if (typeof sig.mic_level === 'number') this.mic = sig.mic_level;
    if (typeof sig.boot === 'number') this.boot = sig.boot;
    if (sig.task !== undefined) this._setTask(sig.task);
  }

  _buildDataPanels() {
    // painéis de dados da execução: aparecem só no estado "executando", com o texto REAL da tarefa
    this.taskCanvas = document.createElement('canvas'); this.taskCanvas.width = 512; this.taskCanvas.height = 128;
    this.taskTex = disposer.track(new THREE.CanvasTexture(this.taskCanvas));
    this.taskTex.colorSpace = THREE.SRGBColorSpace;
    const mat = glowMaterial(PALETTE.glow, 0, { map: this.taskTex });
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(0.46, 0.115), mat);
    disposer.track(panel.geometry);
    panel.position.set(0, 1.22, 0.42);
    panel.rotation.x = -0.35;
    this.group.add(panel);
    const ringMat = glowMaterial(PALETTE.cyan, 0);
    const halo = new THREE.Mesh(new THREE.RingGeometry(0.06, 0.065, 48), ringMat);
    disposer.track(halo.geometry);
    halo.position.set(0, 1.22, 0.40); halo.rotation.x = -0.35;
    this.group.add(halo);
    this._setTask('');
    return { panel, halo };
  }

  _setTask(text) {
    if (text === this._task) return;
    this._task = text;
    const g = this.taskCanvas.getContext('2d');
    g.clearRect(0, 0, 512, 128);
    if (!text) { this.taskTex.needsUpdate = true; return; }
    g.strokeStyle = 'rgba(150,235,255,0.7)'; g.lineWidth = 3; g.strokeRect(4, 4, 504, 120);
    g.fillStyle = 'rgba(150,235,255,0.9)'; g.font = '600 22px Segoe UI, Arial'; g.fillText('EXECUTANDO', 22, 42);
    g.fillStyle = 'rgba(230,248,255,0.95)'; g.font = '26px Segoe UI, Arial';
    g.fillText(text.length > 34 ? text.slice(0, 33) + '…' : text, 22, 90);
    this.taskTex.needsUpdate = true;
  }

  headPosition(target) { return this.rig.map.head.getWorldPosition(target); }

  update(dt, time) {
    const target = MOTION[this.state] || MOTION.aguardando;
    const k = 1 - Math.exp(-dt * 3.2);
    for (const key of KEYS) this.p[key] += ((target[key] || 0) - this.p[key]) * k;
    this.color.lerp(this.targetColor, k * 0.8);
    this.accent.lerp(this.targetAccent, k * 0.8);
    const uk = this.ultron || 0;                             // Protocolo ULTRON (só aparência)
    if (uk > 0) { this.color.lerp(ULTRON_RED, uk); this.accent.lerp(ULTRON_GLOW, uk); }
    const p = this.p, R = this.rig;
    const speed = p.slump > 0.5 ? 0.55 : 1;
    const t = time * speed;
    const voice = this.state === 'falando' ? Math.max(this.mouth.energy || 0, this.voice) : 0;

    // ---------- tronco: respiração, apoio, inclinações
    const breath = Math.sin(t * Math.PI * 2 / 4.6) * p.breath;
    const shift = Math.sin(t * 0.21) * p.sway;
    R.rot('hips', 0, Math.sin(t * 0.13) * 0.03 * p.sway, shift * 0.025);
    R.rot('spine', p.lean * 0.6 + p.slump * 0.06 + breath * 0.006, -Math.sin(t * 0.13) * 0.025 * p.sway, -shift * 0.02);
    R.rot('chest', p.lean * 0.4 + p.slump * 0.08 - breath * 0.012 + p.think * 0.04, p.think * -0.08, -shift * 0.015);
    R.map.chest.scale.set(1 + breath * 0.012, 1, 1 + breath * 0.02);
    R.rot('neck', -p.slump * 0.05, 0, 0);
    for (const s of ['L', 'R']) R.rot('clav' + s, 0, 0, (s === 'L' ? 1 : -1) * (breath * 0.012 - p.slump * 0.05 + p.ask * 0.03));

    // ---------- olhar: deriva natural; atenção ao usuário; TARDIS à esquerda do observador
    if (time > this.lookNext) {
      this.lookNext = time + 1.6 + Math.random() * 3.2;
      this.lookTarget.set((Math.random() - 0.5) * 0.5, (Math.random() - 0.5) * 0.18);
    }
    const lk = 1 - Math.exp(-dt * 2.2);
    this.look.x += (this.lookTarget.x * p.look - this.look.x) * lk;
    this.look.y += (this.lookTarget.y * p.look - this.look.y) * lk;
    let yaw = this.look.x - 0.55 * p.tardis * (this.inRoom ? 0 : 1) - 0.18 * p.think;
    let pitch = this.look.y + 0.13 * p.think + 0.05 * p.slump - 0.03 * p.attend;
    // na TARDIS: olha o painel real em uso (ou o escolhido, ou o rotor) — a inteligência que opera a nave
    if (this.inRoom && this.focus) {
      this.root.updateMatrixWorld();
      _v.copy(this.focus); this.root.worldToLocal(_v); _v.sub(_h.set(0, 1.68, 0));
      const w = clamp(0.55 + 0.45 * Math.max(p.tardis, p.work, this.operating ? 1 : 0), 0, 1) * (1 - 0.7 * p.talk);
      yaw = lerp(yaw, clamp(Math.atan2(_v.x, _v.z), -0.9, 0.9), w);
      pitch = lerp(pitch, clamp(-Math.atan2(_v.y, Math.hypot(_v.x, _v.z)), -0.2, 0.55), w);
    }
    // olhar para o usuário (a câmera é o ponto de vista dele) ao ouvir, falar e pedir confirmação
    const meet = clamp(p.attend + 0.8 * p.talk, 0, 1) * (1 - p.tardis) * (1 - 0.6 * p.think);
    if (this.camera && meet > 0.01) {
      this.root.updateMatrixWorld();
      _v.copy(this.camera.position);
      this.root.worldToLocal(_v);
      _v.sub(_h.set(0, 1.68, 0));
      const toYaw = clamp(Math.atan2(_v.x, _v.z), -0.6, 0.6);
      const toPitch = clamp(-Math.atan2(_v.y, Math.hypot(_v.x, _v.z)), -0.35, 0.3);
      yaw = lerp(yaw, toYaw, meet * 0.85);
      pitch = lerp(pitch, toPitch, meet * 0.7);
    }
    let roll = 0.07 * p.attend * Math.sin(t * 0.35) + 0.05 * p.think;
    if (voice > 0) {                                         // acenos ligados à energia real da fala
      pitch += (voice - 0.35) * 0.06 * p.talk;
      yaw += Math.sin(t * 1.7) * 0.05 * p.talk * voice;
    }
    pitch += 0.11 * uk; roll *= 1 - uk;                    // ULTRON: queixo baixo, olhar fixo
    R.rot('head', pitch, yaw, roll);
    const jaw = clamp(this.mouth.open || 0, 0, 1);
    R.rot('jaw', jaw * 0.32, 0, 0);
    this.mouthHole.material.opacity = smooth(0.04, 0.25, jaw) * 0.92;
    this.mouthHole.scale.set(0.75 + 0.35 * (this.mouth.wide || 0) - 0.25 * (this.mouth.round || 0), 0.3 + 2.4 * jaw, 1);
    const wide = 1 + 0.28 * (this.mouth.wide || 0) - 0.22 * (this.mouth.round || 0);
    R.map.mouth.scale.set(wide, 1 + 0.4 * jaw, 1);

    // ---------- piscadas (e olhos apagados na privacidade)
    if (time > this.blinkAt) { this.blink = 1; this.blinkAt = time + 2.4 + Math.random() * 4.2; }
    this.blink = Math.max(0, this.blink - dt * 7);
    const lid = Math.max(0.06, 1 - Math.sin(Math.min(1, this.blink) * Math.PI) * 0.94);
    const squint = 0.18 * p.think + 0.3 * uk + 0.1 * p.work;              // foco: olhos um pouco mais fechados
    const eyes = this.state === 'privacidade' ? 0.06 : lid * (1 - squint);
    for (const s of ['L', 'R']) R.map['eye' + s].scale.set(1, eyes, 1);
    for (const iris of this.irises) iris.position.set(clamp(yaw * 0.006, -0.004, 0.004), clamp(-pitch * 0.004, -0.002, 0.002), 0.006);
    // sobrancelhas: erguem na atenção e na pergunta; baixam e aproximam no foco e no ULTRON
    const raise = 0.0035 * p.attend + 0.005 * p.ask + 0.002 * voice * p.talk - 0.003 * p.think - 0.0045 * uk - 0.002 * p.slump;
    for (const s of ['L', 'R']) {
      const brow = R.map['brow' + s], side = s === 'L' ? 1 : -1;
      brow.position.copy(brow.userData.bindP).add(_h.set(-side * 0.0012 * (p.think + uk), raise, 0));
      brow.quaternion.copy(brow.userData.bindQ).multiply(_q2.setFromEuler(_e2.set(0, 0, side * (0.12 * (p.think + uk) - 0.06 * p.ask))));
    }

    // ---------- braços: repouso, gesto na fala, trabalho na execução, palmas na confirmação, pensamento
    const g = this.gesture;
    if (this.state === 'falando' && time > g.next && voice > 0.25) {
      g.next = time + 0.9 + Math.random() * 1.4;
      const side = Math.random() < 0.6 ? 'R' : 'L';
      g['target' + side] = 0.55 + Math.random() * 0.45;
      g['target' + (side === 'R' ? 'L' : 'R')] *= 0.4;
    }
    if (this.state !== 'falando' || voice < 0.05) { g.targetL *= 0.96; g.targetR *= 0.96; }
    g.L += (g.targetL * p.talk - g.L) * (1 - Math.exp(-dt * 3));
    g.R += (g.targetR * p.talk - g.R) * (1 - Math.exp(-dt * 3));
    for (const s of ['L', 'R']) {
      const side = s === 'L' ? 1 : -1;
      const gest = g[s];
      const sway = Math.sin(t * 0.7 + (side > 0 ? 0 : 1.7)) * 0.02 * p.sway;
      const thinkHand = s === 'R' ? p.think : 0;
      this._op = lerp(this._op || 0, this.inRoom && this.operating ? 1 : 0, 1 - Math.exp(-dt * 1.5));
      const operate = this._op * (s === 'R' ? 1 : 0.6) * (0.75 + 0.25 * Math.sin(t * 0.8 + (s === 'R' ? 0 : 2)));
      const fwd = -(0.55 * p.work + 0.42 * gest + 0.28 * p.ask + 0.62 * thinkHand + 0.5 * operate) + sway;
      const abd = side * (0.06 * p.ask + 0.04 * gest - 0.05 * p.work - 0.12 * thinkHand);
      R.rot('arm' + s, fwd, side * (0.2 * thinkHand), abd);
      const elbow = 0.02 + 0.95 * p.work + 0.9 * gest + 0.35 * p.ask + 1.65 * thinkHand + 0.04 * breath + 0.6 * operate;
      R.rot('fore' + s, -elbow, side * (0.5 * gest + 0.6 * p.work), 0);
      const typing = p.work * Math.sin(t * 9 + (side > 0 ? 0 : 1.3)) * 0.12;
      R.rot('hand' + s, -0.1 * gest + typing - 0.2 * thinkHand, side * 0.6 * p.ask, side * (0.15 * gest));
      const curl = 0.18 + 0.25 * p.slump + 0.35 * thinkHand - 0.12 * gest - 0.12 * p.ask + 0.55 * uk;
      for (const [fi, f] of ['index', 'middle', 'ring', 'pinky'].entries()) {
        const wave = p.work * Math.sin(t * 11 + fi * 1.3 + side) * 0.25;
        for (let kk = 1; kk <= 3; kk++) R.rot(`${f}${kk}${s}`, 0, 0, -side * (curl + wave) * (kk === 1 ? 0.6 : 1));
      }
      R.rot('thumb2' + s, 0, 0, -side * curl * 0.5);
    }

    // ---------- pernas: apoio alternado discreto; pés firmes
    R.rot('thighL', 0.01 * shift, 0, -shift * 0.012);
    R.rot('thighR', -0.01 * shift, 0, -shift * 0.012);
    R.rot('shinL', Math.max(0, -shift) * 0.04, 0, 0);
    R.rot('shinR', Math.max(0, shift) * 0.04, 0, 0);
    this.root.position.y = 0.14 + Math.sin(t * 0.9) * 0.008 + breath * 0.002;
    R.update();

    // ---------- olhos e gema: cor da íris do estado; apagados na privacidade; a gema respira com a voz real
    const lit = this.state === 'privacidade' ? 0.12 : (0.55 + 0.45 * p.glow);
    this.eyeMat.color.copy(this.accent); this.eyeMat.opacity = 0.9 * lit;
    this.irisMat.color.copy(this.accent).lerp(_white, 0.35); this.irisMat.opacity = 0.85 * lit;
    this.gem.gem.material.color.copy(this.accent);
    this.gem.halo.material.color.copy(this.accent);
    this.gem.halo.material.opacity = (0.35 + 0.3 * p.pulse + 0.4 * voice) * lit;
    this.gem.halo.scale.setScalar(0.034 + 0.02 * voice + 0.006 * Math.sin(t * 2.0));

    // ---------- roupas e cabelo: ULTRON deixa tudo grafite e metálico; o cabelo balança com o movimento
    if (uk !== this._dressK) { dressUltron(this.dress, this.hair, uk); this._dressK = uk; }
    this.hair.material.uniforms.uSway.value = 0.6 + 0.8 * voice + 0.6 * p.sway + 0.5 * p.work;
    // ---------- luz e energia
    const u = this.u;
    u.uTime.value = time;
    u.uColor.value.copy(this.color);
    u.uAccent.value.copy(this.accent);
    u.uGlow.value = p.glow * (1 + 0.18 * uk);
    u.uPulse.value = p.pulse;
    u.uPulseSpeed.value = 2.2 + p.pulse * 2.5;
    u.uFlicker.value = Math.max(p.flicker, 0.12 * uk);
    u.uVoice.value = voice * p.talk + (this.state === 'escutando' || this.state === 'reconhecendo' ? this.mic * 0.6 : 0);
    const period = this.state === 'inicializando' ? 1.0 : (p.scan > 0.6 ? 2.6 : 6.5);
    const phase = (time / period) % 1;
    u.uScanY.value = this.state === 'inicializando' ? this.boot * 2.0 : lerp(-0.1, 2.0, phase);
    u.uScanStrength.value = p.scan * (this.state === 'inicializando' ? 1.6 : 0.9);
    u.uScanW.value = 0.08 + 0.05 * p.scan;
    u.uReveal.value = this.state === 'inicializando' ? 0.05 + this.boot * 2.0 : 10.0;
    this.projector.update(dt, time, { ring: p.ring, beam: p.beam, particles: p.particles, waveRate: p.waves + voice * p.talk,
                                      color: this.color });
    const panelA = p.work * 0.85;
    this._dataPanels.panel.material.opacity = this._task ? panelA : 0;
    this._dataPanels.halo.material.opacity = panelA * 0.6;
    this._dataPanels.halo.scale.setScalar(1 + 0.25 * Math.sin(time * 4));
  }
}
const _white = new THREE.Color(0xffffff);
const _v = new THREE.Vector3(), _h = new THREE.Vector3(), _q2 = new THREE.Quaternion(), _e2 = new THREE.Euler();
