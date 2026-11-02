// Materiais e texturas compartilhados — feitos aqui, sem imagens de terceiros.
//
// Holograma: linhas topológicas, pontos luminosos e uma casca translúcida (Fresnel). Os três aceitam
// "skinning" rígido-misto na GPU: cada vértice segue até dois ossos (atributos skinA, skinB, skinW) cujas
// matrizes vêm de uma textura (boneTex) — o corpo inteiro são 3 chamadas de desenho.
import * as THREE from 'three';

export const PALETTE = {
  ink: 0x020611, deep: 0x061428, cyan: 0x38e1ff, glow: 0x9ef4ff, electric: 0x2b8cff,
  ice: 0xdcefff, amber: 0xffb347, coral: 0xff5d73, dim: 0x3d5873,
};

/** Registro do que precisa ser liberado da GPU ao encerrar (geometrias, materiais, texturas). */
export class Disposer {
  constructor() { this.items = new Set(); }
  track(x) { if (x) this.items.add(x); return x; }
  dispose() { for (const x of this.items) { try { x.dispose(); } catch (e) { /* já liberado */ } } this.items.clear(); }
}
export const disposer = new Disposer();

export function canvasTexture(w, h, draw, { repeat = null, srgb = true } = {}) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat[0], repeat[1]); }
  return disposer.track(t);
}

let glowTex = null;
/** Disco luminoso suave (pontos, faíscas, halos). */
export function glowTexture() {
  if (glowTex) return glowTex;
  glowTex = canvasTexture(64, 64, (g, w, h) => {
    const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    r.addColorStop(0, 'rgba(255,255,255,1)');
    r.addColorStop(0.18, 'rgba(255,255,255,0.85)');
    r.addColorStop(0.45, 'rgba(255,255,255,0.22)');
    r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, w, h);
  }, { srgb: false });
  return glowTex;
}

/** Uniformes do holograma compartilhados por linhas, pontos e casca (um estado, três desenhos). */
export function holoUniforms(color = PALETTE.cyan) {
  return {
    uTime: { value: 0 },
    uColor: { value: new THREE.Color(color) },
    uAccent: { value: new THREE.Color(PALETTE.glow) },
    uGlow: { value: 0.8 },          // intensidade geral (estado)
    uScanY: { value: -10 },          // faixa de energia que percorre o corpo (altura no modelo)
    uScanW: { value: 0.12 },
    uScanStrength: { value: 0.0 },
    uPulse: { value: 0.0 },          // pulsos de circuito (pensando/executando)
    uPulseSpeed: { value: 2.0 },
    uFlicker: { value: 0.0 },        // falha de projeção (erro)
    uReveal: { value: 10.0 },        // montagem na inicialização: acima desta altura não desenha
    uVoice: { value: 0.0 },          // energia real da fala
    uFade: { value: 1.0 },
    boneTex: { value: null },
    uPixel: { value: 1.0 },
  };
}

const SKIN_DECL = /* glsl */`
  uniform sampler2D boneTex;
  attribute float skinA; attribute float skinB; attribute float skinW;
  mat4 boneMat(float i) {
    int y = int(i + 0.5);
    return mat4(texelFetch(boneTex, ivec2(0, y), 0), texelFetch(boneTex, ivec2(1, y), 0),
                texelFetch(boneTex, ivec2(2, y), 0), texelFetch(boneTex, ivec2(3, y), 0));
  }
`;
const SKIN_POS = /* glsl */`
  mat4 skinM = boneMat(skinA) * skinW + boneMat(skinB) * (1.0 - skinW);
  vec4 sp = skinM * vec4(position, 1.0);
`;
const COMMON_VARY = /* glsl */`
  uniform float uTime; uniform float uScanY; uniform float uScanW; uniform float uScanStrength;
  uniform float uPulse; uniform float uPulseSpeed; uniform float uFlicker; uniform float uReveal;
  uniform float uGlow; uniform float uVoice; uniform float uFade; uniform vec3 uColor; uniform vec3 uAccent;
  varying float vY; varying float vDepth;
`;
const ENERGY = /* glsl */`
  float energy(float y) {
    float band = exp(-pow((y - uScanY) / max(uScanW, 0.001), 2.0)) * uScanStrength;
    float circuit = uPulse * pow(0.5 + 0.5 * sin(y * 22.0 - uTime * uPulseSpeed), 8.0);
    float flick = 1.0 - uFlicker * step(0.86, fract(sin(floor(uTime * 24.0) * 12.9898) * 43758.5453));
    return (uGlow + band + circuit * 0.9 + uVoice * 0.35) * flick;
  }
`;

function skinnedVertex(body, skinned) {
  return skinned ? SKIN_DECL + body.replace('/*POS*/', SKIN_POS).replace(/position_/g, 'sp')
                 : body.replace('/*POS*/', 'vec4 sp = vec4(position, 1.0);').replace(/position_/g, 'sp');
}

/** Linhas da malha (contornos e meridianos). Aditivas, sem escrever profundidade. */
export function holoLineMaterial(u, { opacity = 0.55, skinned = false } = {}) {
  const vertexShader = skinnedVertex(COMMON_VARY + /* glsl */`
    attribute float weight;
    varying float vW;
    void main() {
      /*POS*/
      vY = sp.y; vW = weight;
      vec4 mv = modelViewMatrix * sp;
      vDepth = -mv.z;
      gl_Position = projectionMatrix * mv;
    }`, skinned);
  const fragmentShader = COMMON_VARY + ENERGY + /* glsl */`
    uniform float uOpacity; varying float vW;
    void main() {
      if (vY > uReveal) discard;
      float e = energy(vY);
      float edge = smoothstep(uReveal, uReveal - 0.06, vY);
      vec3 col = mix(uColor, uAccent, clamp(e - 0.9, 0.0, 1.0) * 0.6);
      float a = uOpacity * vW * e * uFade * mix(1.0, 0.55, smoothstep(2.0, 9.0, vDepth));
      gl_FragColor = vec4(col * (1.0 + (1.0 - edge) * 2.5), a);
    }`;
  return disposer.track(new THREE.ShaderMaterial({
    uniforms: { ...u, uOpacity: { value: opacity } }, vertexShader, fragmentShader,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
}

/** Nós luminosos sobre a malha. */
export function holoPointsMaterial(u, { size = 0.018, opacity = 0.9, skinned = false } = {}) {
  const vertexShader = skinnedVertex(COMMON_VARY + /* glsl */`
    uniform float uSize; uniform float uPixel; attribute float weight; varying float vW;
    void main() {
      /*POS*/
      vY = sp.y; vW = weight;
      vec4 mv = modelViewMatrix * sp;
      vDepth = -mv.z;
      gl_PointSize = uSize * uPixel * (900.0 / max(vDepth, 0.1)) * (0.6 + 0.6 * weight);
      gl_Position = projectionMatrix * mv;
    }`, skinned);
  const fragmentShader = COMMON_VARY + ENERGY + /* glsl */`
    uniform float uOpacity; uniform sampler2D map; varying float vW;
    void main() {
      if (vY > uReveal) discard;
      vec4 t = texture2D(map, gl_PointCoord);
      float e = energy(vY);
      gl_FragColor = vec4(mix(uColor, uAccent, 0.55) * e, t.a * uOpacity * uFade * vW);
    }`;
  return disposer.track(new THREE.ShaderMaterial({
    uniforms: { ...u, uOpacity: { value: opacity }, uSize: { value: size }, map: { value: glowTexture() } },
    vertexShader, fragmentShader, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
}

/** Casca translúcida: brilho nas bordas (Fresnel), quase invisível de frente — dá volume ao holograma. */
export function holoShellMaterial(u, { opacity = 0.32, skinned = false, power = 2.4 } = {}) {
  const vertexShader = skinnedVertex(COMMON_VARY + /* glsl */`
    varying vec3 vN; varying vec3 vV;
    void main() {
      /*POS*/
      vY = sp.y;
      ${skinned ? 'vec3 n = mat3(skinM) * normal;' : 'vec3 n = normal;'}
      vN = normalize(normalMatrix * n);
      vec4 mv = modelViewMatrix * sp;
      vV = normalize(-mv.xyz); vDepth = -mv.z;
      gl_Position = projectionMatrix * mv;
    }`, skinned);
  const fragmentShader = COMMON_VARY + ENERGY + /* glsl */`
    uniform float uOpacity; uniform float uPower; varying vec3 vN; varying vec3 vV;
    void main() {
      if (vY > uReveal) discard;
      float rim = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), uPower);
      float e = energy(vY);
      gl_FragColor = vec4(uColor * (0.25 + rim * 1.4) * e, (0.05 + rim) * uOpacity * uFade);
    }`;
  return disposer.track(new THREE.ShaderMaterial({
    uniforms: { ...u, uOpacity: { value: opacity }, uPower: { value: power } }, vertexShader, fragmentShader,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.FrontSide,
  }));
}

/** Material aditivo simples (anéis, feixes, painéis holográficos). */
export function glowMaterial(color, opacity = 0.6, { map = null, side = THREE.DoubleSide } = {}) {
  return disposer.track(new THREE.MeshBasicMaterial({
    color, transparent: true, opacity, map, side, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
}

// ---------------------------------------------------------------- materiais físicos (TARDIS)
export const PHYS = {};

function noiseCanvas(g, w, h, base, spread, alpha = 0.06) {
  g.fillStyle = base; g.fillRect(0, 0, w, h);
  for (let i = 0; i < w * h / 18; i++) {
    const v = Math.random() * spread;
    g.fillStyle = `rgba(${v},${v},${v + 10},${alpha})`;
    g.fillRect(Math.random() * w, Math.random() * h, 1 + Math.random() * 2, 1);
  }
}

export function physical() {
  if (PHYS.ready) return PHYS;
  const brushed = canvasTexture(256, 256, (g, w, h) => {
    noiseCanvas(g, w, h, '#7d8a99', 255, 0.05);
    for (let y = 0; y < h; y += 2) { g.fillStyle = `rgba(255,255,255,${Math.random() * 0.05})`; g.fillRect(0, y, w, 1); }
  }, { repeat: [2, 2] });
  PHYS.metal = disposer.track(new THREE.MeshStandardMaterial({ color: 0x6c7a8c, metalness: 0.85, roughness: 0.32, map: brushed }));
  PHYS.darkMetal = disposer.track(new THREE.MeshStandardMaterial({ color: 0x1a2533, metalness: 0.8, roughness: 0.45 }));
  PHYS.steel = disposer.track(new THREE.MeshStandardMaterial({ color: 0x9aa7b6, metalness: 0.95, roughness: 0.22 }));
  PHYS.brass = disposer.track(new THREE.MeshStandardMaterial({ color: 0xb58a3c, metalness: 0.9, roughness: 0.3 }));
  PHYS.copper = disposer.track(new THREE.MeshStandardMaterial({ color: 0xa8643a, metalness: 0.9, roughness: 0.35 }));
  PHYS.panel = disposer.track(new THREE.MeshStandardMaterial({ color: 0x24344a, metalness: 0.6, roughness: 0.55 }));
  PHYS.rubber = disposer.track(new THREE.MeshStandardMaterial({ color: 0x0b1018, metalness: 0.1, roughness: 0.85 }));
  PHYS.glass = disposer.track(new THREE.MeshStandardMaterial({
    color: 0x9fd8ff, metalness: 0.1, roughness: 0.05, transparent: true, opacity: 0.16, depthWrite: false,
    envMapIntensity: 1.6 }));
  const grate = canvasTexture(256, 256, (g, w, h) => {
    noiseCanvas(g, w, h, '#151d28', 90, 0.08);
    g.strokeStyle = 'rgba(120,150,180,0.35)'; g.lineWidth = 2;
    for (let i = 0; i <= 8; i++) { g.beginPath(); g.moveTo(i * w / 8, 0); g.lineTo(i * w / 8, h); g.stroke();
      g.beginPath(); g.moveTo(0, i * h / 8); g.lineTo(w, i * h / 8); g.stroke(); }
    g.fillStyle = 'rgba(0,0,0,0.55)';
    for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) g.fillRect(i * w / 8 + 5, j * h / 8 + 5, w / 8 - 10, h / 8 - 10);
  }, { repeat: [10, 10] });
  PHYS.grate = disposer.track(new THREE.MeshStandardMaterial({ color: 0x8394a8, metalness: 0.8, roughness: 0.5, map: grate }));
  // madeira pintada de azul (cabine): veios + desgaste leve, como relevo
  const wood = canvasTexture(512, 512, (g, w, h) => {
    g.fillStyle = '#183f8a'; g.fillRect(0, 0, w, h);
    for (let x = 0; x < w; x++) {
      const v = Math.sin(x * 0.11) * 6 + Math.sin(x * 0.53 + 2) * 3 + Math.random() * 4;
      g.fillStyle = `rgba(${4 + v},${18 + v},${60 + v * 2},0.35)`; g.fillRect(x, 0, 1, h);
    }
    for (let i = 0; i < 1400; i++) {
      g.fillStyle = `rgba(255,255,255,${Math.random() * 0.035})`;
      g.fillRect(Math.random() * w, Math.random() * h, 1, 2 + Math.random() * 18);
    }
  }, { repeat: [1, 1] });
  const woodBump = canvasTexture(256, 256, (g, w, h) => {
    g.fillStyle = '#808080'; g.fillRect(0, 0, w, h);
    for (let x = 0; x < w; x++) { const v = 128 + Math.sin(x * 0.4) * 18 + Math.random() * 20;
      g.fillStyle = `rgb(${v},${v},${v})`; g.fillRect(x, 0, 1, h); }
  }, { srgb: false });
  PHYS.wood = disposer.track(new THREE.MeshStandardMaterial({ color: 0x2a5bb5, map: wood, bumpMap: woodBump,
    bumpScale: 0.6, roughness: 0.62, metalness: 0.0 }));
  PHYS.woodDark = disposer.track(new THREE.MeshStandardMaterial({ color: 0x1b3f86, map: wood, bumpMap: woodBump,
    bumpScale: 0.6, roughness: 0.66, metalness: 0.0 }));
  PHYS.black = disposer.track(new THREE.MeshStandardMaterial({ color: 0x07090d, roughness: 0.5, metalness: 0.2 }));
  PHYS.ready = true;
  return PHYS;
}

// ---------------------------------------------------------------- agrupamento de geometria
/** Junta peças estáticas que usam o mesmo material numa só geometria (uma chamada de desenho por material).
 *  add(geometria, matriz, chave) — a geometria de entrada é liberada depois de copiada. */
export class Batch {
  constructor() { this.parts = new Map(); }

  add(geometry, matrix, key) {
    if (!this.parts.has(key)) this.parts.set(key, []);
    this.parts.get(key).push([geometry, matrix.clone()]);
    return this;
  }

  /** Atalho: caixa, cilindro etc. já posicionados (posição, rotação em radianos, escala). */
  put(geometry, key, [x, y, z] = [0, 0, 0], [rx, ry, rz] = [0, 0, 0], [sx, sy, sz] = [1, 1, 1], parent = null) {
    const m = new THREE.Matrix4().compose(new THREE.Vector3(x, y, z),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)), new THREE.Vector3(sx, sy, sz));
    if (parent) m.premultiply(parent);
    return this.add(geometry, m, key);
  }

  build(materials, group = new THREE.Group()) {
    for (const [key, list] of this.parts) {
      const material = materials[key];
      if (!material) throw new Error(`material ausente: ${key}`);
      const geo = mergeGeometries(list);
      const mesh = new THREE.Mesh(geo, material);
      mesh.name = key;
      group.add(mesh);
    }
    this.parts.clear();
    return group;
  }
}

/** Junta geometrias (posição, normal, uv) aplicando a matriz de cada uma; índices preservados. */
export function mergeGeometries(list) {
  let vertices = 0, indices = 0;
  for (const [g] of list) { vertices += g.attributes.position.count; indices += g.index ? g.index.count : g.attributes.position.count; }
  const pos = new Float32Array(vertices * 3), nor = new Float32Array(vertices * 3), uv = new Float32Array(vertices * 2);
  const idx = vertices > 65535 ? new Uint32Array(indices) : new Uint16Array(indices);
  const v = new THREE.Vector3(), nm = new THREE.Matrix3();
  let vo = 0, io = 0;
  for (const [g, m] of list) {
    const p = g.attributes.position, n = g.attributes.normal, t = g.attributes.uv;
    nm.getNormalMatrix(m);
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i).applyMatrix4(m); pos.set([v.x, v.y, v.z], (vo + i) * 3);
      if (n) { v.fromBufferAttribute(n, i).applyMatrix3(nm).normalize(); nor.set([v.x, v.y, v.z], (vo + i) * 3); }
      if (t) { uv[(vo + i) * 2] = t.getX(i); uv[(vo + i) * 2 + 1] = t.getY(i); }
    }
    if (g.index) for (let i = 0; i < g.index.count; i++) idx[io + i] = g.index.getX(i) + vo;
    else for (let i = 0; i < p.count; i++) idx[io + i] = vo + i;
    vo += p.count; io += g.index ? g.index.count : p.count;
    g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  out.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  out.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  out.setIndex(new THREE.BufferAttribute(idx, 1));
  out.computeBoundingSphere();
  return disposer.track(out);
}

/** Texto numa textura (placas, letreiros, telas). Devolve { texture, draw(lines) } para redesenhar. */
export function textPlate(w, h, paint) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const g = c.getContext('2d');
  const texture = disposer.track(new THREE.CanvasTexture(c));
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  const draw = (...args) => { g.clearRect(0, 0, w, h); paint(g, w, h, ...args); texture.needsUpdate = true; };
  return { texture, draw, canvas: c };
}
