// Roupas, cabelo e sobrancelhas do holograma — sobre o MESMO esqueleto do corpo (avatar.js), deformados pelos
// mesmos ossos na GPU. Tudo é gerado aqui (nenhum modelo de terceiros):
//
// * jaqueta: tronco com caimento, gola alta, mangas com punhos, zíper e costuras;
// * calça: cintura (sob a jaqueta) e pernas até o tornozelo, com vincos;
// * calçados: cabedal fechado com sola e biqueira;
// * cabelo masculino: ~2 400 fios com volume no topo (penteado para trás), laterais curtas, nuca aparada; as
//   pontas balançam no shader;
// * sobrancelhas: três traços por lado presos a ossos próprios (expressões: erguer, franzir).
//
// Os materiais vêm de materials.js (superfície sólida com luz; fios). A cor de cada peça tinge-se pelo estado do
// SAFRA — e muda para grafite/vermelho no Protocolo ULTRON (avatar.js chama ``dressUltron``).
import * as THREE from 'three';
import { holoSolidMaterial, hairMaterial, holoLineMaterial, disposer } from './materials.js';

const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const lerp = (a, b, t) => a + (b - a) * t;
const gauss = (x, mu, s) => Math.exp(-(((x - mu) / s) ** 2));

export const CLOTH = {
  jacket: { base: 0x5a2a32, ultron: 0x3a3d45 },
  pants: { base: 0x2c1c21, ultron: 0x26282e },
  shoes: { base: 0x1a1416, ultron: 0x18191d },
  hair: { base: 0x5a2630, tip: 0xffc2c8 },
};

/** Malha sólida + costuras de uma peça a partir de um BodyGeometry já preenchido. */
function solidPiece(geo, material, seamMaterial) {
  const mk = (indices) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(geo.pos, 3));
    g.setAttribute('skinA', new THREE.Float32BufferAttribute(geo.a, 1));
    g.setAttribute('skinB', new THREE.Float32BufferAttribute(geo.b, 1));
    g.setAttribute('skinW', new THREE.Float32BufferAttribute(geo.w, 1));
    g.setAttribute('weight', new THREE.Float32BufferAttribute(geo.weight, 1));
    g.setIndex(indices);
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.95, 0), 1.6);
    return disposer.track(g);
  };
  const shellGeo = mk(geo.tris);
  shellGeo.computeVertexNormals();
  const mesh = new THREE.Mesh(shellGeo, material);
  const seams = new THREE.LineSegments(mk(geo.lines), seamMaterial);
  for (const o of [mesh, seams]) o.frustumCulled = false;
  mesh.renderOrder = 1; seams.renderOrder = 2;
  return { mesh, seams };
}

/**
 * Roupas. ``tools``: { BodyGeometry, torsoPoint } de avatar.js. Devolve { objects, materials }.
 */
export function buildClothes(rig, u, { BodyGeometry, torsoPoint }) {
  const seamMat = holoLineMaterial(u, { opacity: 0.5, skinned: true });
  const trimMat = holoLineMaterial(u, { opacity: 0.95, skinned: true });
  const mats = {
    jacket: holoSolidMaterial(u, { base: CLOTH.jacket.base, tint: 0.06, weave: 0.35, gloss: 0.3, opacity: 0.97,
                                   rim: 0.12, rimPower: 4.0, glow: 0.0 }),
    pants: holoSolidMaterial(u, { base: CLOTH.pants.base, tint: 0.04, weave: 0.45, gloss: 0.18, opacity: 0.97,
                                  rim: 0.1, rimPower: 4.0, glow: 0.0 }),
    shoes: holoSolidMaterial(u, { base: CLOTH.shoes.base, tint: 0.02, gloss: 0.9, opacity: 0.98, rim: 0.12,
                                  rimPower: 4.0, glow: 0.0 }),
  };
  const objects = [];
  const torsoRows = (geo, y0, y1, rings, liftFn, segs = 30) => {
    const ids = [];
    for (let i = 0; i < rings; i++) {
      const y = lerp(y0, y1, i / (rings - 1));
      const row = [];
      for (let j = 0; j < segs; j++) {
        const q = torsoPoint(rig, y, (j / segs) * Math.PI * 2, liftFn(y, j / segs));
        row.push(geo.vert(q.p, q.a, q.b, q.t, 0.6));
      }
      ids.push(row);
    }
    geo.grid(ids, { ringEvery: 999, meridianEvery: segs / 2, pointEvery: 999 });   // só as costuras laterais
    return ids;
  };


  // ---------- jaqueta: tronco (caimento mais solto embaixo), gola, mangas
  const jacket = new BodyGeometry(rig);
  // caimento: abre só nas laterais (espaço para as coxas); frente e costas descem retas, como um paletó
  const jacketLift = (y, frac = 0.25) => {
    const side = Math.abs(Math.cos(frac * Math.PI * 2)) ** 2;
    return 0.011 + (1 - smooth(0.80, 1.02, y)) * (0.008 + 0.034 * side) + 0.004 * gauss(y, 1.31, 0.08);
  };
  torsoRows(jacket, 0.805, 1.505, 30, jacketLift);                             // até o quadril: cobre a virilha
  jacket.chain([{ bone: 'neck', len: 0.052, rings: 4, profile: (t) => [0.071 - 0.004 * t, 0.077 - 0.004 * t] }],
               { dir: 1, segs: 22, startBone: 'chest', blend: 0.4, ringEvery: 99, meridianEvery: 99, pointEvery: 999 });
  for (const s of ['L', 'R']) {
    jacket.chain([
      { bone: 'arm' + s, len: 0.30, rings: 10,
        profile: (t) => [1.13 * (0.051 - 0.012 * t + 0.006 * gauss(t, 0.08, 0.14)) + 0.005,
                         1.13 * (0.049 - 0.009 * t + 0.006 * gauss(t, 0.45, 0.2)) + 0.005] },
      { bone: 'fore' + s, len: 0.235, rings: 9,
        profile: (t) => [1.12 * (0.040 + 0.004 * gauss(t, 0.2, 0.2) - 0.019 * smooth(0, 1, t)) + 0.006,
                         1.12 * (0.041 + 0.004 * gauss(t, 0.2, 0.2) - 0.013 * smooth(0, 1, t)) + 0.006] },
    ], { segs: 18, startBone: 'clav' + s, capStart: 0.056, blend: 0.22, ringEvery: 999, meridianEvery: 9,
         pointEvery: 999 });
    // punho com acabamento metálico
    const cuff = [];
    for (let j = 0; j <= 18; j++) {
      const a = (j / 18) * Math.PI * 2;
      const idx = rig.index('fore' + s);
      cuff.push({ p: rig.toModel('fore' + s, Math.cos(a) * 0.032, -0.226, Math.sin(a) * 0.036), a: idx, b: idx, t: 1 });
    }
    jacket.polyline(cuff, 1.0, { every: 999 });
  }
  const zipper = [];
  for (let k = 0; k <= 30; k++) {
    const y = lerp(1.49, 0.81, k / 30);
    const q = torsoPoint(rig, y, Math.PI / 2, jacketLift(y) + 0.0025);
    zipper.push({ p: q.p, a: q.a, b: q.b, t: q.t });
  }
  jacket.polyline(zipper, 1.0, { every: 999 });
  const hem = [];                                                             // bainha (segue o caimento)
  for (let j2 = 0; j2 <= 40; j2++) {
    const q = torsoPoint(rig, 0.805, (j2 / 40) * Math.PI * 2, jacketLift(0.805, j2 / 40) + 0.002);
    hem.push({ p: q.p, a: q.a, b: q.b, t: q.t });
  }
  jacket.polyline(hem, 0.9, { every: 999 });
  for (const side of [1, -1]) {                                                // costura do ombro ao peito (recorte)
    const pts = [];
    for (let k = 0; k <= 14; k++) {
      const y = lerp(1.47, 1.18, k / 14);
      const ang = Math.PI / 2 + side * lerp(0.95, 0.35, k / 14);
      const q = torsoPoint(rig, y, ang, 0.014 + 0.004 * gauss(y, 1.31, 0.08));
      pts.push({ p: q.p, a: q.a, b: q.b, t: q.t });
    }
    jacket.polyline(pts, 0.8, { every: 999 });
  }
  const j = solidPiece(jacket, mats.jacket, seamMat);
  objects.push(j.mesh, j.seams);

  // ---------- calça: cintura e pernas
  const pants = new BodyGeometry(rig);
  torsoRows(pants, 0.865, 0.975, 6, () => 0.009);                            // a cintura fica sob a jaqueta
  for (const s of ['L', 'R']) {
    pants.chain([
      { bone: 'thigh' + s, len: 0.43, rings: 13,
        profile: (t) => [1.10 * (0.080 - 0.028 * t + 0.008 * gauss(t, 0.3, 0.25)) + 0.006,
                         1.10 * (0.084 - 0.032 * t + 0.010 * gauss(t, 0.32, 0.22)) + 0.006] },
      { bone: 'shin' + s, len: 0.385, rings: 12,
        profile: (t) => [1.10 * (0.051 - 0.017 * t + 0.004 * gauss(t, 0.25, 0.2)) + 0.008,
                         1.10 * (0.052 - 0.016 * t + 0.010 * gauss(t, 0.27, 0.16)) + 0.008] },
    ], { segs: 20, startBone: 'hips', blend: 0.16, ringEvery: 999, meridianEvery: 5, pointEvery: 999 });
  }
  const p = solidPiece(pants, mats.pants, seamMat);
  objects.push(p.mesh, p.seams);

  // ---------- calçados: cabedal + sola + biqueira
  const shoes = new BodyGeometry(rig);
  for (const s of ['L', 'R']) {
    const side = s === 'L' ? 1 : -1;
    const foot = rig.index('foot' + s), toes = rig.index('toes' + s), shin = rig.index('shin' + s);
    const ids = [];
    const rings = 14, segs = 16;
    for (let i = 0; i < rings; i++) {
      const t = i / (rings - 1), z = lerp(-0.074, 0.218, t);
      const halfW = 0.036 + 0.021 * smooth(0, 0.6, t) - 0.014 * smooth(0.85, 1, t);
      const height = 0.084 * (1 - smooth(0.2, 0.95, t)) + 0.030;
      const row = [];
      for (let k = 0; k < segs; k++) {
        const a = (k / segs) * Math.PI * 2;
        const x = Math.cos(a) * halfW;
        const y = -0.088 + Math.max(0, (0.5 + 0.5 * Math.sin(a)) * height);
        const pnt = rig.toModel('foot' + s, x + 0.008 * side * smooth(0.5, 1, t), y, z);
        const toW = smooth(0.62, 0.76, t);
        row.push(toW > 0.01 ? shoes.vert(pnt, toes, foot, toW, 0.7)
                            : shoes.vert(pnt, foot, shin, 0.5 + 0.5 * smooth(0, 0.25, t), 0.7));
      }
      ids.push(row);
    }
    shoes.grid(ids, { ringEvery: 999, meridianEvery: 999, pointEvery: 999 });
    const sole = [];                                                           // contorno da sola
    for (let i = 0; i < rings; i++) {
      const t = i / (rings - 1), z = lerp(-0.074, 0.218, t);
      const halfW = 0.037 + 0.021 * smooth(0, 0.6, t) - 0.014 * smooth(0.85, 1, t);
      const pnt = rig.toModel('foot' + s, halfW + 0.008 * side * smooth(0.5, 1, t), -0.084, z);
      const toW = smooth(0.62, 0.76, t);
      sole.push({ p: pnt, a: toW > 0.01 ? toes : foot, b: foot, t: toW > 0.01 ? toW : 1 });
    }
    shoes.polyline(sole, 0.9, { every: 999 });
  }
  const sh = solidPiece(shoes, mats.shoes, trimMat);
  objects.push(sh.mesh, sh.seams);
  return { objects, materials: mats };
}

/**
 * Cabelo masculino: fios distribuídos no couro cabeludo (função da cabeça ``headRadius``), penteados para trás
 * com volume no topo, laterais curtas e nuca aparada, mais uma "massa" sólida por baixo para dar corpo.
 */
export function buildHair(rig, u, { headRadius, HEAD_SCALE, BodyGeometry }) {
  const head = rig.index('head');
  const hairline = (th) => {                                    // altura mínima do cabelo em cada direção
    const a = Math.abs(th);
    if (a < 1.05) return 0.62 + 0.06 * (a / 1.05);              // testa (entradas leves nas laterais)
    if (a < 1.75) return lerp(0.66, 0.18, smooth(1.05, 1.75, a)); // têmporas → acima da orelha
    return lerp(0.18, -0.42, smooth(1.75, 2.6, a));             // atrás: até a nuca
  };
  const pos = [], skinA = [], skinB = [], skinW = [], strand = [], seed = [], flow = [], idx = [];
  const surface = (th, y, lift) => {
    const r = headRadius(th, y) + lift;
    return new THREE.Vector3(r * Math.sin(th), y, r * Math.cos(th)).multiplyScalar(HEAD_SCALE);
  };
  let rnd = 7;
  const random = () => { rnd = (rnd * 16807) % 2147483647; return rnd / 2147483647; };
  const COUNT = 2400, POINTS = 5;
  let n = 0;
  for (let i = 0; i < COUNT * 3 && n < COUNT; i++) {
    const th = (random() * 2 - 1) * Math.PI;
    const y = lerp(-0.45, 1.0, Math.pow(random(), 0.7));
    if (y < hairline(th)) continue;
    const a = Math.abs(th);
    const top = smooth(0.55, 0.9, y) * (1 - smooth(1.3, 2.4, a));
    const side = smooth(1.0, 1.5, a) * (1 - smooth(2.2, 2.7, a));
    const back = smooth(2.2, 2.8, a);
    const length = (0.012 + 0.040 * top + 0.010 * back + 0.002 * side) * (0.8 + 0.4 * random());
    const root = surface(th, y, 0.035);
    const normal = root.clone().sub(new THREE.Vector3(0, -0.1 * HEAD_SCALE, 0)).normalize();
    const comb = new THREE.Vector3(0.12 * Math.sign(th) * side, 0.25 * top - 0.85 * side - 0.9 * back, -1.0 + 0.4 * back)
      .normalize();
    const dir = comb.sub(normal.clone().multiplyScalar(comb.dot(normal))).normalize();
    const volume = 0.004 + 0.012 * top + 0.002 * side;
    const s0 = random();
    let prev = -1;
    for (let k = 0; k < POINTS; k++) {
      const s = k / (POINTS - 1);
      const pnt = root.clone().addScaledVector(dir, length * s).addScaledVector(normal, volume * Math.sin(Math.PI * Math.min(1, s * 0.9)) + 0.0015 * s);
      const model = rig.toModel('head', pnt.x, pnt.y, pnt.z);
      pos.push(model.x, model.y, model.z); skinA.push(head); skinB.push(head); skinW.push(1);
      strand.push(s); seed.push(s0); flow.push(dir.x, dir.y, dir.z);
      const id = pos.length / 3 - 1;
      if (prev >= 0) idx.push(prev, id);
      prev = id;
    }
    n++;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('skinA', new THREE.Float32BufferAttribute(skinA, 1));
  g.setAttribute('skinB', new THREE.Float32BufferAttribute(skinB, 1));
  g.setAttribute('skinW', new THREE.Float32BufferAttribute(skinW, 1));
  g.setAttribute('strand', new THREE.Float32BufferAttribute(strand, 1));
  g.setAttribute('seed', new THREE.Float32BufferAttribute(seed, 1));
  g.setAttribute('flow', new THREE.Float32BufferAttribute(flow, 3));
  g.setIndex(idx);
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 1.7, 0), 0.4);
  disposer.track(g);
  const material = hairMaterial(u, { base: CLOTH.hair.base, tip: CLOTH.hair.tip });
  const strands = new THREE.LineSegments(g, material);
  strands.frustumCulled = false; strands.renderOrder = 4;

  // massa sólida sob os fios (o couro cabeludo nunca aparece através do cabelo)
  const cap = new BodyGeometry(rig);
  const rows = [];
  for (let i = 0; i < 18; i++) {
    const y = lerp(-0.42, 1.0, i / 17);
    const row = [];
    for (let k = 0; k < 40; k++) {
      const th = -Math.PI + (k / 40) * Math.PI * 2;
      const inside = y >= hairline(th) - 0.02;
      const a = Math.abs(th);
      const top = smooth(0.55, 0.9, y) * (1 - smooth(1.3, 2.4, a));
      const lift = inside ? 0.03 + 0.06 * top : -0.02;                         // fora da área: some sob a pele
      const pnt = surface(th, y, lift);
      row.push(cap.vert(rig.toModel('head', pnt.x, pnt.y, pnt.z), head, head, 1, 0.5));
    }
    rows.push(row);
  }
  cap.grid(rows, { ringEvery: 999, meridianEvery: 999, pointEvery: 999 });
  const capMat = holoSolidMaterial(u, { base: CLOTH.hair.base, tint: 0.12, weave: 0.6, gloss: 0.5, opacity: 0.97,
                                       rim: 0.35, rimPower: 3.0, glow: 0.04 });
  const capPiece = solidPiece(cap, capMat, holoLineMaterial(u, { opacity: 0.0, skinned: true }));
  return { strands, cap: capPiece.mesh, material, capMaterial: capMat, count: n };
}

/** Sobrancelhas: faixas sólidas escuras (legíveis sobre a pele clara), presas a ``browL``/``browR`` — erguer =
 *  atenção/pergunta, baixar e aproximar = foco (e o olhar frio do ULTRON). */
export function buildBrows(rig, u, { headRadius, HEAD_SCALE, BodyGeometry }) {
  const geo = new BodyGeometry(rig);
  for (const side of [1, -1]) {
    const bone = rig.index(side > 0 ? 'browL' : 'browR');
    const rows = [];
    for (const offset of [0.026, 0.0, -0.022]) {                // de cima para baixo: a faixa tem ~5 mm
      const row = [];
      for (let k = 0; k <= 14; k++) {
        const f = k / 14;
        const th = side * lerp(0.07, 0.82, f);
        const thick = 1 - 0.55 * f * f;                          // mais grossa perto do nariz
        const y = 0.215 - 0.11 * f * f + offset * thick + 0.022 * Math.sin(Math.PI * f);
        const r = headRadius(th, y) + 0.026 + 0.006 * (offset === 0 ? 1 : 0);
        const pnt = new THREE.Vector3(r * Math.sin(th), y, r * Math.cos(th)).multiplyScalar(HEAD_SCALE);
        row.push(geo.vert(rig.toModel('head', pnt.x, pnt.y, pnt.z), bone, bone, 1, 0.8));
      }
      rows.push(row);
    }
    geo.grid(rows, { closed: false, ringEvery: 999, meridianEvery: 999, pointEvery: 999 });
  }
  const material = holoSolidMaterial(u, { base: 0x2a1218, tint: 0.04, gloss: 0.2, opacity: 0.98, rim: 0.15,
                                          rimPower: 3.0, glow: 0.0 });
  const piece = solidPiece(geo, material, holoLineMaterial(u, { opacity: 0.0, skinned: true }));
  piece.mesh.renderOrder = 5;
  return piece.mesh;
}

/** Protocolo ULTRON: roupas grafite e frias; o cabelo escurece. ``k`` 0–1 (transição). */
export function dressUltron(dress, hair, k) {
  for (const key of ['jacket', 'pants', 'shoes']) {
    const m = dress.materials[key];
    m.uniforms.uBase.value.setHex(CLOTH[key].base).lerp(_tmp.setHex(CLOTH[key].ultron), k);
    m.uniforms.uTint.value = lerp(key === 'jacket' ? 0.06 : 0.03, 0.05, k);
    m.uniforms.uGloss.value = lerp(key === 'shoes' ? 0.75 : 0.2, 0.6, k);         // acabamento metálico
  }
  hair.material.uniforms.uTip.value.setHex(CLOTH.hair.tip).lerp(_tmp.setHex(0x9aa0aa), k);
}
const _tmp = new THREE.Color();
