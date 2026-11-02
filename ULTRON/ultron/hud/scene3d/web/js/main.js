// Montagem da central 3D: um motor, uma cena — convés do JARVIS (holograma, ORBE, cabine) e sala da TARDIS —
// ligados aos sinais REAIS que o Python envia. Fora do JARVIS (navegador comum), roda uma DEMONSTRAÇÃO
// rotulada como tal, para conferir o visual; nada dela chega ao JARVIS.
import * as THREE from 'three';
import { Engine, PROFILES } from './engine.js';
import { Avatar } from './avatar.js';
import { Deck } from './deck.js';
import { PoliceBox } from './exterior.js';
import { TardisRoom, PANEL_KEYS } from './room.js';
import { Orb } from './orb.js';
import { CameraRig, fitDistance } from './camera.js';
import { Hud } from './hud.js';
import { connectBridge, makeSender } from './bridge.js';

const params = new URLSearchParams(location.search);
const send = makeSender(await connectBridge());
const DEMO = !send.connected;
const V = (x, y, z) => new THREE.Vector3(x, y, z);

window.addEventListener('error', (e) => send.report({ type: 'error', message: String(e.message || e), where: `${e.filename || ''}:${e.lineno || ''}` }));
window.addEventListener('unhandledrejection', (e) => send.report({ type: 'error', message: String(e.reason && e.reason.message || e.reason) }));

function fail(reason) {
  const n = document.getElementById('notice');
  n.textContent = `Vista 3D indisponível: ${reason}`;
  n.classList.remove('hidden');
  send.report({ type: 'failed', reason: String(reason) });
}

let engine;
const state = { mode: 'jarvis', view: 'frente', jarvisView: 'frente', selected: '', transition: false, effects: true,
                sigAt: performance.now(), connected: true, sig: null, debug: params.has('perf') };
const hud = new Hud({ onView: (v) => onViewButton(v) });
let world;
try {
  engine = new Engine(document.getElementById('stage'), { profile: params.get('profile') || 'balanced', onReport });
  const scale = engine.profile.particles;
  world = { deck: new Deck({ particleScale: scale }), avatar: new Avatar({ particleScale: scale }), box: new PoliceBox(),
            orb: new Orb({ particleScale: scale }), room: new TardisRoom({ particleScale: scale }) };
} catch (e) {
  const msg = e && e.message ? e.message : String(e);
  fail(/webgl/i.test(msg) ? `o WebGL 2 não abriu nesta placa de vídeo (${msg})` : msg);
  throw e;
}
const { deck, avatar, box, orb, room } = world;
const scene = engine.scene, camera = engine.camera;
camera.far = 140; camera.updateProjectionMatrix();
box.group.position.set(-2.75, 0, -2.7); box.group.rotation.y = 0.42;
orb.group.position.set(1.95, 1.7, -0.95); orb.group.scale.setScalar(0.4);
room.group.position.set(0, 0, -60);
scene.add(deck.group, avatar.group, box.group, orb.group, room.group);
const DECK = [deck.group, avatar.group, box.group, orb.group];
const FOG = { jarvis: [new THREE.Color(0x020611), 0.045], tardis: [new THREE.Color(0x07070a), 0.028], nucleo: [new THREE.Color(0x01040b), 0.2] };

function showInterior(on) {
  room.group.visible = on;
  for (const g of DECK) g.visible = !on;
  scene.fog.color.copy(FOG[on ? 'tardis' : 'jarvis'][0]); scene.fog.density = FOG[on ? 'tardis' : 'jarvis'][1];
  engine.renderer.setClearColor(scene.fog.color, 1);
}
showInterior(false);

// ---------------------------------------------------------------- câmera
const rig = new CameraRig(camera, engine.renderer.domElement);
const boxDir = () => V(Math.sin(box.group.rotation.y), 0, Math.cos(box.group.rotation.y));
const orbPos = () => orb.group.getWorldPosition(new THREE.Vector3());
rig.define('frente', (aspect) => {
  const d = fitDistance(camera, 2.45, 2.7, aspect);
  return { pos: V(0.32, 1.3, d), target: V(0, 1.0, 0), min: 2.0, max: 10, minPolar: 0.85, maxPolar: 1.66 };
});
rig.define('nucleo', () => {
  const o = orbPos();
  return { pos: o.clone().add(V(-0.45, 0.12, 1.45)), target: o, min: 0.75, max: 4.5, minPolar: 0.2, maxPolar: 2.9 };
});
rig.define('exterior', () => {
  const b = box.group.position, f = boxDir(), side = V(f.z, 0, -f.x);
  return { pos: b.clone().addScaledVector(f, 4.9).addScaledVector(side, -1.1).add(V(0, 1.75, 0)), target: b.clone().add(V(0, 1.45, 0)),
           min: 1.8, max: 8, minPolar: 0.7, maxPolar: 1.62 };
});
rig.define('porta', () => {
  const b = box.group.position, f = boxDir();
  return { pos: b.clone().addScaledVector(f, 1.15).add(V(0, 1.3, 0)), target: b.clone().add(V(0, 1.2, 0)), rotate: false };
});
const I = room.group.position;
rig.define('tardis', () => ({ pos: I.clone().add(V(0.6, 3.05, 6.4)), target: I.clone().add(V(0, 1.35, 0)), min: 2.4, max: 8.0,
                               minPolar: 0.35, maxPolar: 1.5 }));
rig.define('entrada', () => ({ pos: I.clone().add(V(0, 1.65, 8.2)), target: I.clone().add(V(0, 1.55, 0)), rotate: false }));
rig.define('painel', () => {
  const v = room.panelView(state.selected || 'analise');
  return { pos: v.pos, target: v.target, min: 1.0, max: 5.0, minPolar: 0.35, maxPolar: 1.5 };
});

function go(view, opts = {}) {
  state.view = view;
  if (state.mode === 'jarvis') state.jarvisView = view;
  orb.setExpanded(view === 'nucleo');
  hud.setActive(view);
  rig.go(view, { instant: !state.effects, ...opts });
}

// ---------------------------------------------------------------- transições JARVIS ⇄ TARDIS (pela porta)
function setMode(mode, animate = true) {
  if (mode === state.mode && !state.transition) return;
  state.mode = mode;
  const anim = animate && state.effects;
  // a vista final é decidida no fim da passagem: um painel escolhido durante a viagem também vale
  const finalView = () => mode === 'tardis' ? (state.selected ? 'painel' : 'tardis') : (state.jarvisView === 'exterior' ? 'exterior' : 'frente');
  hud.setButtons(mode, finalView());
  if (!anim) {
    showInterior(mode === 'tardis');
    box.setOpen(0);
    go(finalView(), { instant: true });
    return;
  }
  state.transition = true;
  if (mode === 'tardis') {
    box.setOpen(1);
    rig.go('porta', { duration: 1.25, then: () => {
      hud.veil(true);
      setTimeout(() => {
        showInterior(true);
        rig.go('entrada', { instant: true });
        hud.veil(false);
        box.setOpen(0);
        const view = finalView();
        state.view = view; hud.setActive(view);
        rig.go(view, { duration: 1.7, then: () => { state.transition = false; if (finalView() !== state.view) go(finalView()); } });
      }, 360);
    } });
  } else {
    rig.go('entrada', { duration: 1.1, then: () => {
      hud.veil(true);
      setTimeout(() => {
        showInterior(false);
        box.open = 1; box.setOpen(1);
        rig.go('porta', { instant: true });
        hud.veil(false);
        const view = finalView();
        state.view = view; hud.setActive(view); orb.setExpanded(false);
        rig.go(view, { duration: 1.7, then: () => { state.transition = false; if (finalView() !== state.view) go(finalView()); } });
        setTimeout(() => box.setOpen(0), 900);
      }, 360);
    } });
  }
}

function onViewButton(v) {
  if (v === 'entrar') { DEMO ? setMode('tardis') : send.request('tardis'); return; }
  if (v === 'sair') { DEMO ? setMode('jarvis') : send.request('jarvis'); return; }
  if (v === 'painel' && !state.selected) state.selected = 'analise';
  if (state.transition) return;
  go(v);
}

function selectPanel(key) {
  state.selected = PANEL_KEYS.includes(key) ? key : '';
  room.select(state.selected);
  if (state.mode === 'tardis' && !state.transition) go(state.selected ? 'painel' : 'tardis');
}

// ---------------------------------------------------------------- cliques na cena
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
let down = null, hoverAt = 0;
const canvas = engine.renderer.domElement;
function pick(e) {
  const r = canvas.getBoundingClientRect();
  ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
}
canvas.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY]; });
canvas.addEventListener('pointerup', (e) => {
  if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5 || state.transition) return;
  pick(e);
  if (state.mode === 'tardis') {
    const hit = ray.intersectObjects(room.panelMeshes, false)[0];
    if (hit) { DEMO ? selectPanel(hit.object.userData.panel) : send.select(hit.object.userData.panel); }
    return;
  }
  const head = avatar.headPosition(new THREE.Vector3());
  if (ray.ray.distanceSqToPoint(head) < 0.17 * 0.17) { send.request('mic'); return; }      // como o clique no rosto 2D
  if (ray.ray.distanceSqToPoint(orbPos()) < 0.42 * 0.42) { go('nucleo'); return; }
  if (ray.intersectObject(box.group, true).length) { DEMO ? setMode('tardis') : send.request('tardis'); }
});
canvas.addEventListener('pointermove', (e) => {
  if (state.mode !== 'tardis' || performance.now() - hoverAt < 60) return;
  hoverAt = performance.now();
  pick(e);
  const hit = ray.intersectObjects(room.panelMeshes, false)[0];
  room.setHover(hit ? hit.object.userData.panel : '');
  canvas.style.cursor = hit ? 'pointer' : '';
});
// janela escondida e mostrada de novo: o relógio do sinal recomeça (sem "sem sinal" falso na volta)
document.addEventListener('visibilitychange', () => { if (!document.hidden) state.sigAt = performance.now(); });
canvas.addEventListener('dblclick', () => { if (!state.transition) go(state.mode === 'tardis' ? 'tardis' : 'frente'); });
window.addEventListener('keydown', (e) => {
  if (e.key === 'F3') { state.debug = !state.debug; if (!state.debug) hud.perf(''); }
  if (e.key === 'Escape' && state.view === 'nucleo') go('frente');
});

// ---------------------------------------------------------------- sinais do JARVIS
function applySig(s) {
  state.sig = s; state.sigAt = performance.now(); state.connected = true;
  avatar.apply(s);
  orb.apply({ ...s, connected: true });
  hud.setState({ label: s.label, detail: s.detail, rgb: s.rgb, alert: s.alert, error: s.state === 'erro', tardis: state.mode === 'tardis' });
  hud.setCaption(s.caption);
  if (s.system) deck.setSystem({ ...s.system, connected: true });
}

function projectionCards() {
  const s = state.sig;
  if (!s || state.transition) return [];
  if (state.mode === 'jarvis' && state.view === 'frente') {
    const head = avatar.headPosition(new THREE.Vector3());
    const pr = s.projections || {};
    return [
      { id: 'modelo', k: 'MODELO', v: pr.modelo, anchor: head.clone().add(V(0.32, 0.1, 0)), dx: 18, dy: -10 },
      { id: 'fase', k: 'FASE', v: pr.fase, anchor: head.clone().add(V(0.32, -0.12, 0)), dx: 18, dy: 0 },
      { id: 'tarefa', k: 'TAREFA', v: pr.tarefa, anchor: head.clone().add(V(-0.32, -0.25, 0)), dx: -250, dy: 0 },
    ];
  }
  if (state.mode === 'jarvis' && state.view === 'nucleo') {
    const o = orbPos();
    const pct = (x) => `${Math.round(Math.max(0, Math.min(1, x || 0)) * 100)}%`;
    return [
      { id: 'orb-state', k: 'NÚCLEO', v: orb.label, anchor: o.clone().add(V(0.5, 0.35, 0)), dx: 10 },
      { id: 'orb-mic', k: 'MICROFONE', v: s.mic_state ? `${s.mic_state} · ${pct(s.mic_level)}` : '', anchor: o.clone().add(V(0.5, 0.05, 0)), dx: 10 },
      { id: 'orb-out', k: 'VOZ', v: s.state === 'falando' ? pct(s.out_level) : 'em silêncio', anchor: o.clone().add(V(0.5, -0.25, 0)), dx: 10 },
      { id: 'orb-model', k: 'MODELO', v: (s.projections || {}).modelo, anchor: o.clone().add(V(-0.55, 0.25, 0)), dx: -250 },
    ];
  }
  return [];
}

const receivers = {
  init(m) {
    if (m.profile) engine.setProfile(m.profile, m.effects !== false);
    state.effects = m.effects !== false;
    state.debug = state.debug || !!m.debug;
    if (m.selected) selectPanel(m.selected);
    if (m.mode) { state.mode = m.mode === 'tardis' ? 'jarvis' : 'tardis'; setMode(m.mode, false); }
  },
  sig: applySig,
  mode(m) { setMode(m.mode, m.animate !== false); },
  view(m) { if (!state.transition) go(m.view); },
  room(m) { room.setEngine(m); box.setEngine(m.mode, m.fault); },
  select(m) { selectPanel(m.panel || ''); },
  profile(m) { state.effects = m.effects !== false; engine.setProfile(m.profile, state.effects); },
  visible(m) { engine.setVisible(m.visible !== false); },
};
window.JARVIS = {
  /** Só leitura: o que a cena está mostrando (testes e diagnóstico). */
  debugInfo() {
    const p = camera.position, t = rig.controls.target;
    return { mode: state.mode, view: state.view, transition: state.transition, selected: state.selected,
             camera: [p.x, p.y, p.z].map((v) => +v.toFixed(2)), target: [t.x, t.y, t.z].map((v) => +v.toFixed(2)),
             deck: deck.group.visible, room: room.group.visible, flight: rig.moving, doors: +box.open.toFixed(2),
             connected: state.connected, level: engine.level, fps: engine.stats ? engine.stats.fps : null };
  },
  receive(msg) {
    try { const f = receivers[msg && msg.type]; if (f) f(msg); }
    catch (e) { send.report({ type: 'error', message: `receive(${msg && msg.type}): ${e.message}` }); }
  },
};

// ---------------------------------------------------------------- relatórios do motor
let lostTimer = 0;
function onReport(r) {
  if (r.type === 'context') {
    if (r.state === 'perdido') {
      hud.notice('A placa de vídeo reiniciou o contexto 3D — aguardando a recuperação…');
      lostTimer = setTimeout(() => send.report({ type: 'failed', reason: 'o contexto WebGL foi perdido e não voltou em 6 s' }), 6000);
    } else { clearTimeout(lostTimer); hud.notice(''); }
  }
  if (r.type === 'stats' && state.debug) {
    hud.perf(`${r.fps} q/s (alvo ${r.target}) · perfil ${r.profile} · redução ${r.level} · ${r.drawCalls} desenhos · ${Math.round(r.triangles / 1000)} mil triângulos`);
  }
  send.report(r);
}

// ---------------------------------------------------------------- relógio da cena
const look = { color: new THREE.Color(), glow: 0.8 };
const pixelUniforms = [avatar.u.uPixel, orb.u.uPixel, deck.dustMat.uniforms.uPixel, avatar.projector.pMat.uniforms.uPixel,
                       room.linkMat.uniforms.uPixel];
engine.add({
  onResize(w, h) {
    const k = engine.renderer.getPixelRatio() * (h / 900);
    for (const u of pixelUniforms) u.value = k;
    rig.reframe();
  },
  setParticleScale(s) { for (const o of [deck, avatar, orb, room]) o.setParticleScale(s); },
  update(dt, time) {
    if (!DEMO && performance.now() - state.sigAt > 6000 && state.connected) {
      state.connected = false;
      orb.apply({ connected: false });
      deck.setSystem({ connected: false });
      hud.notice('Sem sinal do JARVIS há mais de 6 s — o orbe e o painel mostram "sem conexão".');
    } else if (state.connected && !DEMO && hud.el.notice.textContent.startsWith('Sem sinal')) hud.notice('');
    rig.update(dt, time, { drift: state.effects && !state.transition });
    // foco: na vista do NÚCLEO o fundo recua na névoa; na TARDIS, névoa quente e rala
    const [fogColor, fogDensity] = FOG[room.group.visible ? 'tardis' : (state.view === 'nucleo' && !state.transition ? 'nucleo' : 'jarvis')];
    const fk = 1 - Math.exp(-dt * 2.5);
    scene.fog.color.lerp(fogColor, fk); scene.fog.density += (fogDensity - scene.fog.density) * fk;
    engine.renderer.setClearColor(scene.fog.color, 1);
    if (deck.group.visible) {
      avatar.update(dt, time);
      orb.update(dt, time);
      box.update(dt, time);
      look.color.copy(avatar.color); look.glow = avatar.p.glow; look.focus = state.view === 'nucleo';
      deck.update(dt, time, look);
    }
    if (room.group.visible) {
      const az = Math.atan2(camera.position.x - I.x, camera.position.z - I.z);
      room.update(dt, time, az);
    }
    hud.setCards(projectionCards());
    hud.placeCards(camera, engine.container.clientWidth, engine.container.clientHeight);
    const s = state.sig ? state.sig.state : 'aguardando';
    engine.active = state.transition || rig.moving || rig.interacting ||
      ['falando', 'escutando', 'reconhecendo', 'pensando', 'executando', 'tardis', 'inicializando', 'alerta'].includes(s) ||
      (room.group.visible && room.busy);
  },
});
engine.resize();
go('frente', { instant: true });
engine.start();

// ---------------------------------------------------------------- pronto
const info = engine.info;
send.ready({ ...info, profiles: Object.keys(PROFILES), avatar: avatar.counts || null });
if (DEMO) { window.__debug = { scene, camera, rig, THREE }; startDemo(); }

// ---------------------------------------------------------------- demonstração (só fora do JARVIS)
function startDemo() {
  hud.notice('DEMONSTRAÇÃO fora do JARVIS — estados de exemplo, não são dados reais.', 'demo');
  const rgb = { aguardando: [0, 217, 255], escutando: [0, 217, 255], pensando: [22, 139, 255], falando: [0, 217, 255],
                executando: [22, 139, 255], erro: [255, 93, 115], alerta: [255, 179, 71], inicializando: [0, 217, 255] };
  const labels = { aguardando: 'EM ESPERA', escutando: 'ESCUTANDO', pensando: 'PENSANDO', falando: 'FALANDO', executando: 'EXECUTANDO',
                   erro: 'ERRO DE INTEGRAÇÃO', alerta: 'ALERTA', inicializando: 'INICIALIZANDO' };
  const fixed = params.get('demo');
  const order = ['inicializando', 'aguardando', 'escutando', 'pensando', 'falando', 'executando', 'aguardando', 'erro'];
  const text = 'Exemplo de legenda: as palavras acendem conforme a fala avança.';
  const t0 = performance.now();
  const tick = () => {
    const t = (performance.now() - t0) / 1000;
    const st = fixed || order[Math.floor(t / 6) % order.length];
    const speaking = st === 'falando';
    const out = speaking ? 0.35 + 0.35 * Math.abs(Math.sin(t * 7.3) * Math.sin(t * 2.1)) : 0;
    applySig({ state: st, label: labels[st] || st.toUpperCase(), detail: 'demonstração', rgb: rgb[st] || rgb.aguardando, iris: [103, 243, 255],
               out_level: out, mic_level: st === 'escutando' ? 0.3 + 0.2 * Math.sin(t * 5) : 0, mic_state: 'DEMO',
               boot: Math.min(1, (t % 6) / 5), task: st === 'executando' ? 'exemplo de tarefa' : '',
               mouth: speaking ? { open: out * 0.9, wide: 0.3, round: 0.2, energy: out } : { open: 0, wide: 0, round: 0, energy: 0 },
               projections: { modelo: 'exemplo', fase: st === 'pensando' ? 'planejamento' : '' },
               caption: speaking ? { text, progress: ((t % 6) / 6), active: true } : null,
               system: { model: 'exemplo (demonstração)', health: { status: 'OK', detail: 'demonstração' }, uptime: 600 + t, workers: { voz: 0 } } });
    const room = params.get('panel') || '';
    receivers.room({ mode: params.get('rotor') || 'processando', speed: 0.55, amplitude: 1, brightness: 0.92, spin: 0.35, color: [255, 179, 71],
                     fault: false, available: true,
                     panels: Object.fromEntries(PANEL_KEYS.map((k, i) => [k, { level: k === (room || 'telemetria') ? 1 : 0, running: k === (room || 'telemetria') ? 1 : 0,
                                                                                  flash: 0, fault: 0, last: i % 2 ? 'exemplo de resultado anterior' : '' }])),
                     screens: { left: ['FILA', ['0 na fila', 'executando: exemplo', 'demonstração'], [255, 179, 71]],
                                right: ['ÚLTIMA: EXEMPLO', ['concluída', 'texto de exemplo da demonstração'], [220, 238, 255]] } });
  };
  tick();
  setInterval(tick, 100);
  if (params.get('mode') === 'tardis') { if (params.get('panel')) selectPanel(params.get('panel')); setMode('tardis', false); }
  if (params.get('view')) go(params.get('view'), { instant: true });
  const cam = (params.get('cam') || '').split(',').map(Number);
  if (cam.length === 6 && cam.every(Number.isFinite)) {                    // enquadramento livre (capturas de tela)
    rig.userMoved = true;
    camera.position.set(cam[0], cam[1], cam[2]); rig.controls.target.set(cam[3], cam[4], cam[5]); rig.controls.update();
  }
}
