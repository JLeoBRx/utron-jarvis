// O ORBE: o núcleo de inteligência do JARVIS em 3D, no mesmo motor e na mesma linguagem visual da cena.
//
// * Núcleo luminoso com campos de superfície; casca translúcida.
// * Rede neural COERENTE: nós em três cascas (esfera de Fibonacci) ligados aos vizinhos mais próximos na
//   mesma casca e ao nó mais próximo da casca de dentro — conexões que se formam por proximidade, não ao
//   acaso; pulsos percorrem as ligações (mais e mais rápidos ao pensar e executar).
// * Filamentos de energia do núcleo até os nós-ponte da casca externa.
// * Anéis orbitais em planos diferentes, com segmentos e marcas de telemetria, giro independente.
// * Partículas que entram no núcleo (escuta), saem dele (fala, pela energia REAL da voz) ou orbitam.
//
// Estados (só eventos reais): EM ESPERA, ESCUTANDO, PENSANDO, FALANDO, EXECUTANDO, ERRO, ALERTA,
// PRIVACIDADE, INICIALIZANDO e SEM CONEXÃO (a página não recebe nada do JARVIS — o orbe apaga).
import * as THREE from 'three';
import { disposer, canvasTexture, glowMaterial, glowTexture, PALETTE } from './materials.js';

const SHELLS = [[0.27, 26], [0.39, 44], [0.52, 70]];

/** Comportamento por estado: pulsos (taxa, velocidade), anéis, fluxo das partículas, brilho, lentidão. */
const LOOK = {
  idle:      { pulses: 0.25, pulseSpeed: 0.5, rings: 1.0, flow: 0.0, core: 0.75, field: 0.4, net: 0.5, slow: 1.0, waves: 0 },
  listening: { pulses: 0.45, pulseSpeed: 0.8, rings: 1.3, flow: -1.0, core: 0.9, field: 0.6, net: 0.65, slow: 1.0, waves: -1 },
  thinking:  { pulses: 1.0, pulseSpeed: 1.8, rings: 2.2, flow: 0.0, core: 0.95, field: 0.9, net: 0.95, slow: 1.0, waves: 0 },
  speaking:  { pulses: 0.6, pulseSpeed: 1.2, rings: 1.4, flow: 1.0, core: 1.0, field: 0.7, net: 0.7, slow: 1.0, waves: 1 },
  executing: { pulses: 0.9, pulseSpeed: 2.4, rings: 2.6, flow: 0.4, core: 1.0, field: 0.8, net: 0.9, slow: 1.0, waves: 0 },
  alert:     { pulses: 0.5, pulseSpeed: 1.0, rings: 1.2, flow: 0.0, core: 0.95, field: 0.7, net: 0.7, slow: 1.0, waves: 1 },
  error:     { pulses: 0.08, pulseSpeed: 0.25, rings: 0.35, flow: 0.0, core: 0.55, field: 0.25, net: 0.4, slow: 0.4, waves: 0 },
  privacy:   { pulses: 0.05, pulseSpeed: 0.3, rings: 0.3, flow: 0.0, core: 0.35, field: 0.15, net: 0.25, slow: 0.5, waves: 0 },
  boot:      { pulses: 0.6, pulseSpeed: 1.4, rings: 1.8, flow: -0.5, core: 0.7, field: 0.8, net: 0.6, slow: 1.0, waves: -1 },
  offline:   { pulses: 0.0, pulseSpeed: 0.2, rings: 0.12, flow: 0.0, core: 0.18, field: 0.08, net: 0.12, slow: 0.3, waves: 0 },
};
export const ORB_STATE = { aguardando: 'idle', escutando: 'listening', reconhecendo: 'listening', pensando: 'thinking',
  falando: 'speaking', executando: 'executing', tardis: 'executing', confirmacao: 'alert', alerta: 'alert', erro: 'error',
  privacidade: 'privacy', inicializando: 'boot' };
export const ORB_LABEL = { idle: 'EM ESPERA', listening: 'ESCUTANDO', thinking: 'PENSANDO', speaking: 'FALANDO',
  executing: 'EXECUTANDO', alert: 'ATENÇÃO', error: 'ERRO', privacy: 'PRIVACIDADE', boot: 'INICIALIZANDO', offline: 'SEM CONEXÃO' };
const KEYS = Object.keys(LOOK.idle);

function fibonacci(n, r) {
  const pts = [], g = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i + 0.5) * 2 / n, rr = Math.sqrt(1 - y * y), a = i * g;
    pts.push(new THREE.Vector3(Math.cos(a) * rr * r, y * r, Math.sin(a) * rr * r));
  }
  return pts;
}

function ringTexture(style) {
  return canvasTexture(512, 512, (g, w, h) => {
    g.translate(w / 2, h / 2);
    const R = w / 2 - 4;
    const arc = (r, a0, a1, width, alpha) => { g.beginPath(); g.lineWidth = width; g.strokeStyle = `rgba(170,240,255,${alpha})`; g.arc(0, 0, r, a0, a1); g.stroke(); };
    if (style === 0) {                                  // segmentos com intervalos
      for (let i = 0; i < 12; i++) arc(R - 6, i * Math.PI / 6 + 0.04, (i + 1) * Math.PI / 6 - 0.04, 7, i % 3 ? 0.55 : 0.95);
      arc(R - 18, 0, Math.PI * 2, 1.5, 0.35);
    } else if (style === 1) {                           // marcas de escala (telemetria)
      for (let i = 0; i < 120; i++) { const a = i / 120 * Math.PI * 2, long = i % 10 === 0;
        g.strokeStyle = `rgba(170,240,255,${long ? 0.9 : 0.4})`; g.lineWidth = long ? 3 : 1.5;
        g.beginPath(); g.moveTo(Math.cos(a) * (R - (long ? 22 : 12)), Math.sin(a) * (R - (long ? 22 : 12))); g.lineTo(Math.cos(a) * R, Math.sin(a) * R); g.stroke(); }
    } else {                                            // arco com indicadores
      arc(R - 8, 0.2, Math.PI * 1.35, 4, 0.8); arc(R - 8, Math.PI * 1.5, Math.PI * 1.9, 4, 0.5);
      for (let i = 0; i < 6; i++) { const a = 0.2 + i * 0.22; g.fillStyle = 'rgba(200,250,255,0.95)';
        g.beginPath(); g.arc(Math.cos(a) * (R - 22), Math.sin(a) * (R - 22), 4, 0, Math.PI * 2); g.fill(); }
    }
  }, { srgb: true });
}

export class Orb {
  constructor({ particleScale = 1 } = {}) {
    this.group = new THREE.Group();
    this.group.name = 'orbe';
    this.body = new THREE.Group();
    this.group.add(this.body);
    this.u = { uTime: { value: 0 }, uColor: { value: new THREE.Color(PALETTE.cyan) }, uAccent: { value: new THREE.Color(PALETTE.glow) },
               uField: { value: 0.4 }, uCore: { value: 0.8 }, uVoice: { value: 0 }, uPixel: { value: 1 } };

    // ---------- núcleo: esfera com campos de superfície + brilho interno
    this.nucleus = new THREE.Mesh(disposer.track(new THREE.IcosahedronGeometry(0.15, 12)), disposer.track(new THREE.ShaderMaterial({
      uniforms: this.u,
      vertexShader: `uniform float uTime; uniform float uField; uniform float uVoice; varying vec3 vN; varying vec3 vV; varying vec3 vP;
        void main(){ vec3 p=position; float w=sin(p.y*38.0+uTime*1.6)*sin(p.x*31.0-uTime*1.1)*sin(p.z*27.0+uTime*0.7);
          p+=normal*w*0.004*(uField+uVoice*2.0); vP=position; vN=normalize(normalMatrix*normal);
          vec4 mv=modelViewMatrix*vec4(p,1.0); vV=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }`,
      fragmentShader: `uniform float uTime; uniform vec3 uColor; uniform vec3 uAccent; uniform float uField; uniform float uCore; uniform float uVoice;
        varying vec3 vN; varying vec3 vV; varying vec3 vP;
        void main(){ float rim=pow(1.0-abs(dot(vN,vV)),2.2);
          float bands=pow(0.5+0.5*sin(vP.y*70.0+uTime*2.0+sin(vP.x*40.0+uTime)*2.0),10.0)*uField;
          vec3 c=mix(uColor,uAccent,0.5+0.5*rim)*(0.35+rim*1.6+bands*1.2)*(uCore+uVoice*0.8);
          gl_FragColor=vec4(c, 0.55+rim*0.45); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
    this.coreGlow = new THREE.Sprite(disposer.track(new THREE.SpriteMaterial({ map: glowTexture(), color: PALETTE.glow, transparent: true,
                                                                                opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false })));
    this.coreGlow.scale.setScalar(0.55);
    this.halo = new THREE.Sprite(disposer.track(new THREE.SpriteMaterial({ map: glowTexture(), color: PALETTE.cyan, transparent: true,
                                                                            opacity: 0.18, blending: THREE.AdditiveBlending, depthWrite: false })));
    this.halo.scale.setScalar(1.9);
    this.body.add(this.halo, this.nucleus, this.coreGlow);

    // ---------- rede: nós e ligações por proximidade
    const nodes = [], shellOf = [];
    SHELLS.forEach(([r, n], s) => fibonacci(n, r).forEach((p, i) => {
      p.applyAxisAngle(new THREE.Vector3(0, 1, 0), s * 0.7);       // cascas defasadas: ligações radiais não alinhadas
      nodes.push(p); shellOf.push(s);
    }));
    const edges = new Set(), pairs = [];
    const link = (a, b) => { const k = a < b ? `${a}-${b}` : `${b}-${a}`; if (!edges.has(k)) { edges.add(k); pairs.push([a, b]); } };
    nodes.forEach((p, i) => {
      const same = [], inner = [];
      nodes.forEach((q, j) => {
        if (i === j) return;
        if (shellOf[j] === shellOf[i]) same.push([p.distanceToSquared(q), j]);
        else if (shellOf[j] === shellOf[i] - 1) inner.push([p.distanceToSquared(q), j]);
      });
      same.sort((a, b) => a[0] - b[0]).slice(0, 3).forEach(([, j]) => link(i, j));
      if (inner.length) link(i, inner.sort((a, b) => a[0] - b[0])[0][1]);
    });
    const pos = [], along = [], seed = [];
    for (const [a, b] of pairs) {
      const s = Math.random();
      pos.push(nodes[a].x, nodes[a].y, nodes[a].z, nodes[b].x, nodes[b].y, nodes[b].z);
      along.push(0, 1); seed.push(s, s);
    }
    const eg = new THREE.BufferGeometry();
    eg.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    eg.setAttribute('along', new THREE.Float32BufferAttribute(along, 1));
    eg.setAttribute('seed', new THREE.Float32BufferAttribute(seed, 1));
    disposer.track(eg);
    this.netU = { uPulses: { value: 0.3 }, uPulseSpeed: { value: 0.6 }, uNet: { value: 0.5 } };
    this.edges = new THREE.LineSegments(eg, disposer.track(new THREE.ShaderMaterial({
      uniforms: { ...this.u, ...this.netU },
      vertexShader: 'attribute float along; attribute float seed; varying float vT; varying float vS; void main(){ vT=along; vS=seed; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: `uniform float uTime; uniform vec3 uColor; uniform vec3 uAccent; uniform float uPulses; uniform float uPulseSpeed; uniform float uNet;
        varying float vT; varying float vS;
        void main(){ float head=fract(vS*7.31+uTime*uPulseSpeed*(0.6+vS)); float on=step(1.0-uPulses, fract(vS*13.7+floor(vS*7.31+uTime*uPulseSpeed*(0.6+vS))*0.618));
          float pulse=exp(-pow((vT-head)*9.0,2.0))*on;
          gl_FragColor=vec4(mix(uColor,uAccent,pulse), 0.2*uNet+pulse*0.95); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
    const ng = new THREE.BufferGeometry();
    ng.setAttribute('position', new THREE.Float32BufferAttribute(nodes.flatMap((p) => [p.x, p.y, p.z]), 3));
    ng.setAttribute('shell', new THREE.Float32BufferAttribute(shellOf, 1));
    disposer.track(ng);
    this.nodes = new THREE.Points(ng, disposer.track(new THREE.ShaderMaterial({
      uniforms: { ...this.u, ...this.netU, map: { value: glowTexture() } },
      vertexShader: 'attribute float shell; uniform float uPixel; uniform float uTime; varying float vB; void main(){ vB=0.6+0.4*sin(uTime*1.3+position.x*20.0+position.y*13.0); vec4 mv=modelViewMatrix*vec4(position,1.0); gl_PointSize=uPixel*(4.5-shell*0.8)*(5.0/max(-mv.z,0.2)); gl_Position=projectionMatrix*mv; }',
      fragmentShader: 'uniform sampler2D map; uniform vec3 uAccent; uniform float uNet; varying float vB; void main(){ vec4 t=texture2D(map,gl_PointCoord); gl_FragColor=vec4(uAccent, t.a*(0.3+0.7*uNet)*vB); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
    this.network = new THREE.Group();
    this.network.add(this.edges, this.nodes);
    this.body.add(this.network);

    // ---------- filamentos: do núcleo aos nós-ponte da casca externa (os 8 mais distantes entre si)
    const outer = nodes.map((p, i) => [p, i]).filter(([, i]) => shellOf[i] === 2);
    const bridges = [outer[0]];
    while (bridges.length < 8) {
      let best = null, bestD = -1;
      for (const cand of outer) {
        const d = Math.min(...bridges.map((b) => b[0].distanceTo(cand[0])));
        if (d > bestD) { bestD = d; best = cand; }
      }
      bridges.push(best);
    }
    const fpos = [], ft = [], fseed = [];
    bridges.forEach(([p], k) => {
      const ax = p.clone().normalize(), side = new THREE.Vector3(0, 1, 0).cross(ax).normalize();
      const curve = new THREE.CubicBezierCurve3(ax.clone().multiplyScalar(0.14), ax.clone().multiplyScalar(0.25).addScaledVector(side, 0.12),
                                                p.clone().multiplyScalar(0.75).addScaledVector(side, -0.08), p);
      const pts = curve.getPoints(24);
      for (let i = 0; i < pts.length - 1; i++) {
        fpos.push(pts[i].x, pts[i].y, pts[i].z, pts[i + 1].x, pts[i + 1].y, pts[i + 1].z);
        ft.push(i / 24, (i + 1) / 24); fseed.push(k / 8, k / 8);
      }
    });
    const fg = new THREE.BufferGeometry();
    fg.setAttribute('position', new THREE.Float32BufferAttribute(fpos, 3));
    fg.setAttribute('along', new THREE.Float32BufferAttribute(ft, 1));
    fg.setAttribute('seed', new THREE.Float32BufferAttribute(fseed, 1));
    disposer.track(fg);
    this.filaments = new THREE.LineSegments(fg, disposer.track(new THREE.ShaderMaterial({
      uniforms: { ...this.u, ...this.netU },
      vertexShader: 'attribute float along; attribute float seed; varying float vT; varying float vS; void main(){ vT=along; vS=seed; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: `uniform float uTime; uniform vec3 uAccent; uniform float uField; uniform float uVoice; varying float vT; varying float vS;
        void main(){ float flow=pow(0.5+0.5*sin(vT*18.0-uTime*(2.0+uVoice*6.0)+vS*6.2831),4.0);
          gl_FragColor=vec4(uAccent,(0.08+0.55*flow)*(uField+uVoice)*(1.0-vT*0.5)); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
    this.body.add(this.filaments);

    // ---------- anéis orbitais
    this.rings = [];
    [[0.64, 0, [1.25, 0, 0.2], 0.18], [0.74, 1, [0.35, 0.4, 0], -0.11], [0.86, 2, [-0.5, 0.9, 0.3], 0.07], [0.97, 1, [1.57, 0, 0], -0.05]]
      .forEach(([r, style, tilt, speed]) => {
        const mat = glowMaterial(PALETTE.cyan, 0.55, { map: ringTexture(style) });
        const mesh = new THREE.Mesh(disposer.track(new THREE.RingGeometry(r * 0.9, r, 128, 1)), mat);
        const holder = new THREE.Group();
        holder.rotation.set(...tilt);
        holder.add(mesh);
        this.body.add(holder);
        this.rings.push({ mesh, speed, mat, base: 0.55 });
      });

    // ---------- partículas que entram, saem ou orbitam (GPU)
    this.maxParticles = 700;
    const ps = new Float32Array(this.maxParticles * 4);
    for (let i = 0; i < this.maxParticles; i++) ps.set([Math.random(), Math.random(), Math.random(), Math.random()], i * 4);
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.maxParticles * 3), 3));
    pg.setAttribute('seed', new THREE.BufferAttribute(ps, 4));
    disposer.track(pg);
    this.flowU = { uFlow: { value: 0 }, uFlowSpeed: { value: 0.3 } };
    this.particles = new THREE.Points(pg, disposer.track(new THREE.ShaderMaterial({
      uniforms: { ...this.u, ...this.flowU, map: { value: glowTexture() } },
      vertexShader: `attribute vec4 seed; uniform float uTime; uniform float uFlow; uniform float uFlowSpeed; uniform float uPixel; uniform float uVoice; varying float vA;
        void main(){ vec3 dir=normalize(vec3(seed.x-0.5, seed.y-0.5, seed.z-0.5)+1e-4);
          float f=fract(seed.w+uTime*uFlowSpeed*(0.5+seed.x));
          float rIn=mix(1.15,0.16,f), rOut=mix(0.16,1.15+uVoice*0.3,f), rOrb=0.3+seed.w*0.85;
          float r=uFlow<0.0? mix(rOrb,rIn,-uFlow) : mix(rOrb,rOut,uFlow);
          float a=uTime*0.25*(seed.z-0.5)*(1.0-abs(uFlow));
          vec3 p=dir*r; p.xz=mat2(cos(a),-sin(a),sin(a),cos(a))*p.xz;
          vA=(uFlow<0.0? f : (uFlow>0.0? 1.0-f : 0.6))*0.9+0.1;
          vec4 mv=modelViewMatrix*vec4(p,1.0); gl_PointSize=uPixel*(1.6+2.4*seed.y)*(4.0/max(-mv.z,0.2)); gl_Position=projectionMatrix*mv; }`,
      fragmentShader: 'uniform sampler2D map; uniform vec3 uAccent; varying float vA; void main(){ vec4 t=texture2D(map,gl_PointCoord); gl_FragColor=vec4(uAccent, t.a*vA*0.75); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
    this.particles.frustumCulled = false;
    this.body.add(this.particles);

    // ---------- ondas: esferas que convergem (escuta) ou se expandem (fala)
    this.waves = [0, 0.5].map((t) => {
      const mat = disposer.track(new THREE.ShaderMaterial({
        uniforms: { uColor: this.u.uAccent, uA: { value: 0 } },
        vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vN=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(position,1.0); vV=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }',
        fragmentShader: 'uniform vec3 uColor; uniform float uA; varying vec3 vN; varying vec3 vV; void main(){ float rim=pow(1.0-abs(dot(vN,vV)),3.0); gl_FragColor=vec4(uColor, rim*uA); }',
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      const mesh = new THREE.Mesh(disposer.track(new THREE.SphereGeometry(1, 40, 24)), mat);
      this.body.add(mesh);
      return { mesh, mat, t };
    });

    this.state = 'offline';
    this.p = {}; for (const k of KEYS) this.p[k] = LOOK.offline[k];
    this.color = new THREE.Color(PALETTE.cyan); this.targetColor = this.color.clone();
    this.accent = new THREE.Color(PALETTE.glow); this.targetAccent = this.accent.clone();
    this.voice = 0; this.mic = 0;
    this.expanded = 0; this.expandTarget = 0;
    this.spin = 0;
    this.setParticleScale(particleScale);
  }

  setParticleScale(s) { this.particles.geometry.setDrawRange(0, Math.round(this.maxParticles * Math.min(1, 0.45 * s + 0.15))); }

  /** Sinais reais do JARVIS (mesmos do holograma): estado resolvido, cores e níveis de áudio. */
  apply({ state, rgb, iris, out_level, mic_level, connected = true }) {
    this.state = connected ? (ORB_STATE[state] || 'idle') : 'offline';
    if (rgb) this.targetColor.setRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, THREE.SRGBColorSpace);
    if (iris) this.targetAccent.setRGB(iris[0] / 255, iris[1] / 255, iris[2] / 255, THREE.SRGBColorSpace);
    if (!connected) { this.targetColor.set(0x2a4058); this.targetAccent.set(0x4a6a88); }
    if (typeof out_level === 'number') this.voice = out_level;
    if (typeof mic_level === 'number') this.mic = mic_level;
  }

  setExpanded(on) { this.expandTarget = on ? 1 : 0; }
  get label() { return ORB_LABEL[this.state] || ''; }

  update(dt, time) {
    const target = LOOK[this.state] || LOOK.idle;
    const k = 1 - Math.exp(-dt * 2.6);
    for (const key of KEYS) this.p[key] += (target[key] - this.p[key]) * k;
    this.color.lerp(this.targetColor, k); this.accent.lerp(this.targetAccent, k);
    const p = this.p;
    const voice = this.state === 'speaking' ? this.voice : 0;
    const mic = this.state === 'listening' ? this.mic : 0;
    const t = time * p.slow;
    this.expanded += (this.expandTarget - this.expanded) * (1 - Math.exp(-dt * 3));
    const u = this.u;
    u.uTime.value = t;
    u.uColor.value.copy(this.color); u.uAccent.value.copy(this.accent);
    u.uField.value = p.field; u.uCore.value = p.core; u.uVoice.value = voice;
    this.netU.uPulses.value = p.pulses; this.netU.uPulseSpeed.value = p.pulseSpeed; this.netU.uNet.value = p.net;
    this.flowU.uFlow.value = p.flow; this.flowU.uFlowSpeed.value = 0.18 + 0.25 * Math.abs(p.flow) + voice * 0.4;
    // núcleo respira devagar; na fala, pulsa com a energia real da voz; na escuta, oscila com o microfone
    const breath = 1 + 0.03 * Math.sin(t * 1.3);
    const s = breath * (1 + voice * 0.28 + mic * 0.18);
    this.nucleus.scale.setScalar(s);
    this.coreGlow.scale.setScalar(0.45 + 0.25 * p.core + voice * 0.35 + mic * 0.2);
    this.coreGlow.material.color.copy(this.accent); this.coreGlow.material.opacity = 0.35 + 0.6 * p.core;
    this.halo.material.color.copy(this.color); this.halo.material.opacity = 0.06 + 0.14 * p.core + voice * 0.12;
    this.spin += dt * 0.08 * p.rings;
    this.network.rotation.y = this.spin;
    this.network.rotation.x = Math.sin(t * 0.07) * 0.2;
    this.filaments.rotation.copy(this.network.rotation);
    for (const [i, r] of this.rings.entries()) {
      r.mesh.rotation.z += dt * r.speed * p.rings * (i % 2 ? -1 : 1) * 2.2;
      r.mat.color.copy(this.color);
      r.mat.opacity = (0.18 + 0.42 * p.core) * (1 + 0.25 * Math.sin(t * (1.2 + i * 0.4) * p.pulseSpeed));
    }
    for (const w of this.waves) {
      if (p.waves === 0 && Math.abs(target.waves) < 0.01) { w.mat.uniforms.uA.value *= 0.92; continue; }
      w.t = (w.t + dt * 0.45 * (1 + voice + mic)) % 1;
      const radius = p.waves < 0 ? 1.15 - w.t * 0.95 : 0.2 + w.t * 1.0;
      w.mesh.scale.setScalar(radius);
      w.mat.uniforms.uA.value = Math.abs(p.waves) * 0.35 * Math.sin(w.t * Math.PI);
    }
    this.body.scale.setScalar(1 + this.expanded * 0.6);
  }
}
