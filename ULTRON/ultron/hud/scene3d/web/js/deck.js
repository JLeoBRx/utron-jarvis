// O convés do JARVIS: piso metálico gravado, salão circular de nervuras com luz, feixes de luz volumétrica,
// poeira suspensa e um painel holográfico com dados REAIS do sistema (sem dado, o painel diz que não há).
import * as THREE from 'three';
import { disposer, canvasTexture, glowMaterial, glowTexture, PALETTE, physical, textPlate } from './materials.js';

const HALL_R = 11.5;

export class Deck {
  constructor({ particleScale = 1 } = {}) {
    this.group = new THREE.Group();
    this.group.name = 'convés';
    this.hall = new THREE.Group();                 // salão de fundo (sai de cena na vista do NÚCLEO)
    this.hall.name = 'salão';
    this.group.add(this.hall);
    this.focus = 0;
    const P = physical();

    // ---------- piso: metal escuro com gravação luminosa (anéis, raios, marcas de escala)
    const etch = canvasTexture(2048, 2048, (g, w, h) => {
      g.fillStyle = '#000'; g.fillRect(0, 0, w, h);
      g.translate(w / 2, h / 2);
      const k = w / 2 / 14;                                   // pixels por metro (raio 14 m)
      const ring = (r, width, a, dash = []) => {
        g.beginPath(); g.setLineDash(dash.map((d) => d * k)); g.lineWidth = width;
        g.strokeStyle = `rgba(90,200,255,${a})`; g.arc(0, 0, r * k, 0, Math.PI * 2); g.stroke();
      };
      ring(1.35, 3, 0.55); ring(1.6, 1.5, 0.25, [0.12, 0.08]); ring(2.4, 2, 0.32); ring(3.4, 1.2, 0.18, [0.6, 0.2]);
      ring(5.0, 2.5, 0.28); ring(5.15, 1, 0.16); ring(7.2, 3, 0.35); ring(7.45, 1, 0.18, [0.05, 0.12]); ring(10.5, 2, 0.2);
      g.setLineDash([]);
      for (let i = 0; i < 72; i++) {                          // raios entre 2,4 m e 5 m
        const a = (i / 72) * Math.PI * 2, major = i % 6 === 0;
        g.strokeStyle = `rgba(90,200,255,${major ? 0.32 : 0.12})`; g.lineWidth = major ? 2.5 : 1.2;
        g.beginPath(); g.moveTo(Math.cos(a) * 2.4 * k, Math.sin(a) * 2.4 * k);
        g.lineTo(Math.cos(a) * (major ? 5.0 : 3.4) * k, Math.sin(a) * (major ? 5.0 : 3.4) * k); g.stroke();
      }
      for (let i = 0; i < 240; i++) {                         // escala no anel de 7,2 m
        const a = (i / 240) * Math.PI * 2, r0 = i % 10 === 0 ? 6.85 : 7.0;
        g.strokeStyle = `rgba(90,200,255,${i % 10 === 0 ? 0.4 : 0.16})`; g.lineWidth = 1.5;
        g.beginPath(); g.moveTo(Math.cos(a) * r0 * k, Math.sin(a) * r0 * k); g.lineTo(Math.cos(a) * 7.2 * k, Math.sin(a) * 7.2 * k); g.stroke();
      }
      g.font = `${0.16 * k}px Consolas, monospace`; g.fillStyle = 'rgba(120,210,255,0.35)'; g.textAlign = 'center';
      for (let i = 0; i < 12; i++) {                          // azimutes gravados (como num instrumento)
        const a = (i / 12) * Math.PI * 2;
        g.save(); g.rotate(a + Math.PI / 2); g.fillText(String(i * 30).padStart(3, '0'), 0, -6.55 * k); g.restore();
      }
    }, { srgb: true });
    const plates = canvasTexture(1024, 1024, (g, w, h) => {
      g.fillStyle = '#7f8a96'; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 9000; i++) { const v = 100 + Math.random() * 80; g.fillStyle = `rgba(${v},${v},${v + 8},0.08)`; g.fillRect(Math.random() * w, Math.random() * h, 2, 2); }
      g.strokeStyle = 'rgba(20,26,34,0.6)'; g.lineWidth = 3;
      for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * w / 4, 0); g.lineTo(i * w / 4, h); g.stroke(); g.beginPath(); g.moveTo(0, i * h / 4); g.lineTo(w, i * h / 4); g.stroke(); }
    }, { repeat: [7, 7] });
    this.floorMat = disposer.track(new THREE.MeshStandardMaterial({
      color: 0x101b2a, map: plates, metalness: 0.82, roughness: 0.34, emissive: 0xffffff, emissiveMap: etch,
      emissiveIntensity: 0.55, envMapIntensity: 0.9 }));
    const floor = new THREE.Mesh(disposer.track(new THREE.CircleGeometry(14, 160)), this.floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.name = 'piso';
    this.group.add(floor);

    // ---------- anel externo elevado (passarela) com faixa de luz
    const walk = new THREE.Mesh(disposer.track(new THREE.RingGeometry(7.25, 8.4, 160, 1)), P.darkMetal);
    walk.rotation.x = -Math.PI / 2; walk.position.y = 0.16;
    const walkEdge = new THREE.Mesh(disposer.track(new THREE.CylinderGeometry(7.25, 7.25, 0.16, 160, 1, true)), P.metal);
    walkEdge.position.y = 0.08;
    this.strip = new THREE.Mesh(disposer.track(new THREE.TorusGeometry(7.27, 0.012, 6, 220)), glowMaterial(PALETTE.cyan, 0.75));
    this.strip.rotation.x = Math.PI / 2; this.strip.position.y = 0.165;
    this.group.add(walk, walkEdge, this.strip);

    // ---------- salão: nervuras que sobem e se curvam para o centro, com filetes de luz (instanciadas)
    const ribCurve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(HALL_R, 0, 0), new THREE.Vector3(HALL_R + 0.4, 6.5, 0),
                                                     new THREE.Vector3(HALL_R * 0.55, 9.8, 0));
    const ribGeo = disposer.track(new THREE.TubeGeometry(ribCurve, 40, 0.16, 8, false));
    const lightGeo = disposer.track(new THREE.TubeGeometry(ribCurve, 40, 0.025, 5, false));
    const N = 16;
    const ribs = new THREE.InstancedMesh(ribGeo, P.darkMetal, N);
    const lights = new THREE.InstancedMesh(lightGeo, glowMaterial(PALETTE.electric, 0.28), N);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
    for (let i = 0; i < N; i++) {
      const a = (i / N) * Math.PI * 2;
      q.setFromAxisAngle(up, a);
      m.compose(new THREE.Vector3(), q, new THREE.Vector3(1, 1, 1));
      ribs.setMatrixAt(i, m);
      m.compose(new THREE.Vector3(-0.19, 0, 0).applyQuaternion(q), q, new THREE.Vector3(1, 1, 1));
      lights.setMatrixAt(i, m);
    }
    this.hall.add(ribs, lights);
    this.ribLights = lights;
    // painéis de vidro escuro entre as nervuras (reflexos frios ao fundo)
    const wall = new THREE.Mesh(disposer.track(new THREE.CylinderGeometry(HALL_R + 0.1, HALL_R + 0.1, 6.2, 72, 1, true)),
      disposer.track(new THREE.MeshStandardMaterial({ color: 0x06101c, metalness: 0.9, roughness: 0.18, side: THREE.BackSide,
                                                     transparent: true, opacity: 0.9 })));
    wall.position.y = 3.1;
    this.hall.add(wall);
    // anel de teto
    const crown = new THREE.Mesh(disposer.track(new THREE.TorusGeometry(HALL_R * 0.55, 0.06, 8, 120)), glowMaterial(PALETTE.cyan, 0.35));
    crown.rotation.x = Math.PI / 2; crown.position.y = 9.8;
    this.hall.add(crown);

    // ---------- feixes de luz volumétrica (planos aditivos, quase imperceptíveis; mexem devagar)
    this.shaftMat = disposer.track(new THREE.ShaderMaterial({
      uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(0x4fb7ff) }, uPower: { value: 1 } },
      vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: `uniform float uTime; uniform vec3 uColor; uniform float uPower; varying vec2 vUv;
        void main(){ float edge=smoothstep(0.0,0.35,vUv.x)*smoothstep(1.0,0.65,vUv.x);
          float fall=pow(vUv.y,1.3)*smoothstep(0.0,0.25,vUv.y);
          float drift=0.75+0.25*sin(vUv.x*9.0+uTime*0.15)+0.1*sin(vUv.y*14.0-uTime*0.3);
          gl_FragColor=vec4(uColor, edge*fall*drift*0.055*uPower); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    const shaftGeo = disposer.track(new THREE.PlaneGeometry(2.2, 10, 1, 1));
    for (const [x, z, ry, tilt] of [[-4.5, -5, 0.5, 0.22], [3.8, -6, -0.4, -0.18], [0, -8.5, 0, 0.05], [6.5, -2, -1.1, -0.25]]) {
      const s = new THREE.Mesh(shaftGeo, this.shaftMat);
      s.position.set(x, 5, z); s.rotation.set(0, ry, tilt);
      this.hall.add(s);
    }

    // ---------- poeira suspensa (GPU)
    this.maxDust = 900;
    const seeds = new Float32Array(this.maxDust * 4);
    for (let i = 0; i < this.maxDust; i++) seeds.set([Math.random(), Math.random(), Math.random(), Math.random()], i * 4);
    const dg = new THREE.BufferGeometry();
    dg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.maxDust * 3), 3));
    dg.setAttribute('seed', new THREE.BufferAttribute(seeds, 4));
    disposer.track(dg);
    this.dustMat = disposer.track(new THREE.ShaderMaterial({
      uniforms: { uTime: { value: 0 }, map: { value: glowTexture() }, uPixel: { value: 1 }, uColor: { value: new THREE.Color(0x8fd8ff) } },
      vertexShader: `attribute vec4 seed; uniform float uTime; uniform float uPixel; varying float vA;
        void main(){ float a=seed.x*6.2831+uTime*0.01*(seed.w-0.5); float r=1.5+seed.y*9.0;
          float y=mod(seed.z*7.0+uTime*0.04*(0.3+seed.w),7.0);
          vec3 p=vec3(cos(a)*r, y, sin(a)*r);
          vec4 mv=modelViewMatrix*vec4(p,1.0); vA=(0.25+0.75*seed.w)*smoothstep(0.0,0.8,y)*smoothstep(7.0,5.5,y);
          gl_PointSize=uPixel*(1.5+2.5*seed.w)*(8.0/max(-mv.z,0.5)); gl_Position=projectionMatrix*mv; }`,
      fragmentShader: 'uniform sampler2D map; uniform vec3 uColor; varying float vA; void main(){ vec4 t=texture2D(map,gl_PointCoord); gl_FragColor=vec4(uColor, t.a*vA*0.35); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.dust = new THREE.Points(dg, this.dustMat);
    this.dust.frustumCulled = false;
    this.group.add(this.dust);
    this.setParticleScale(particleScale);

    // ---------- painel holográfico de sistema (dados reais; sem dado, diz que não há)
    this.sys = textPlate(768, 420, (g, w, h, rows, title) => {
      g.fillStyle = 'rgba(10,40,70,0.30)'; g.fillRect(0, 0, w, h);
      g.strokeStyle = 'rgba(120,220,255,0.55)'; g.lineWidth = 2; g.strokeRect(3, 3, w - 6, h - 6);
      g.fillStyle = 'rgba(120,220,255,0.9)'; g.fillRect(3, 3, 140, 4);
      g.font = '600 30px Segoe UI, Arial'; g.fillStyle = 'rgba(150,235,255,0.95)'; g.fillText(title, 28, 54);
      g.font = '26px Segoe UI, Arial';
      rows.forEach(([k, v, warn], i) => {
        const y = 112 + i * 52;
        g.fillStyle = 'rgba(120,170,210,0.8)'; g.fillText(k, 28, y);
        g.fillStyle = warn ? 'rgba(255,190,110,0.95)' : 'rgba(230,248,255,0.95)';
        g.fillText(v.length > 30 ? v.slice(0, 29) + '…' : v, 260, y);
        g.fillStyle = 'rgba(120,220,255,0.12)'; g.fillRect(28, y + 14, w - 56, 1);
      });
    });
    const sysMesh = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(1.7, 0.93)), glowMaterial(0xffffff, 0.85, { map: this.sys.texture }));
    sysMesh.position.set(3.7, 1.7, -1.6); sysMesh.rotation.y = -0.85;
    const stand = new THREE.Mesh(disposer.track(new THREE.CylinderGeometry(0.035, 0.07, 1.25, 12)), P.metal);
    stand.position.set(3.7, 0.6, -1.6);
    const foot = new THREE.Mesh(disposer.track(new THREE.CylinderGeometry(0.28, 0.32, 0.05, 32)), P.darkMetal);
    foot.position.set(3.7, 0.025, -1.6);
    this.hall.add(sysMesh, stand, foot);
    this.sysMesh = sysMesh;
    this.sys.draw([['estado', 'sem conexão com o JARVIS', true]], 'SISTEMA');

    // ---------- luzes do convés
    const hemi = new THREE.HemisphereLight(0x3a6ea8, 0x020409, 0.55);
    const key = new THREE.SpotLight(0xcfe6ff, 12, 22, 0.42, 0.8, 1.6);
    key.position.set(2.0, 7.5, 6.5); key.target.position.set(-0.2, 0.6, -0.4);
    const rim = new THREE.PointLight(0x2b8cff, 12, 14, 1.8);
    rim.position.set(0, 3.2, -4.5);
    this.avatarLight = new THREE.PointLight(0x38e1ff, 4, 6, 2);
    this.avatarLight.position.set(0, 0.6, 0.6);
    this.group.add(hemi, key, key.target, rim, this.avatarLight);
  }

  setParticleScale(s) { this.dust.geometry.setDrawRange(0, Math.round(this.maxDust * Math.min(1, 0.5 * s + 0.15))); }

  /** Dados reais do sistema (estado central + telemetria). */
  setSystem({ model = '', health = null, uptime = null, workers = null, connected = true } = {}) {
    if (!connected) { this.sys.draw([['estado', 'sem conexão com o JARVIS', true]], 'SISTEMA'); return; }
    const rows = [];
    rows.push(['modelo', model || 'nenhum modelo ativo', !model]);
    if (health && health.status) rows.push(['saúde', String(health.status).toLowerCase() + (health.detail ? ' · ' + health.detail : ''), health.status !== 'OK']);
    else rows.push(['saúde', 'sem verificação ainda', false]);
    if (typeof uptime === 'number' && uptime > 0) {
      const m = Math.floor(uptime / 60), hh = Math.floor(m / 60);
      rows.push(['ativo há', hh ? `${hh} h ${m % 60} min` : `${m} min`, false]);
    }
    if (workers && typeof workers === 'object') {
      const pending = Object.values(workers).reduce((s, n) => s + (Number(n) || 0), 0);
      rows.push(['filas', pending ? `${pending} tarefa(s) pendente(s)` : 'vazias', false]);
    }
    const key = JSON.stringify(rows);
    if (key !== this._sysKey) { this._sysKey = key; this.sys.draw(rows.slice(0, 5), 'SISTEMA'); }
  }

  update(dt, time, look) {
    this.shaftMat.uniforms.uTime.value = time;
    this.dustMat.uniforms.uTime.value = time;
    this.strip.material.color.copy(look.color);
    this.avatarLight.color.copy(look.color);
    this.avatarLight.intensity = 2.5 + 3.5 * look.glow;
    this.floorMat.emissiveIntensity = 0.42 + 0.18 * look.glow;
    // vista do núcleo: feixes e painel recuam (foco no ORBE)
    const f = 1 - Math.exp(-dt * 2.5);
    this.shaftMat.uniforms.uPower.value += ((look.focus ? 0 : 1) - this.shaftMat.uniforms.uPower.value) * f;
    this.sysMesh.material.opacity += ((look.focus ? 0.12 : 0.85) - this.sysMesh.material.opacity) * f;
    this.ribLights.material.opacity += ((look.focus ? 0.08 : 0.28) - this.ribLights.material.opacity) * f;
    this.focus += ((look.focus ? 1 : 0) - this.focus) * f;
    this.hall.visible = this.focus < 0.85;
  }
}
