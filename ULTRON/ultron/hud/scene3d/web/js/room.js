// A sala de controle da TARDIS por dentro: salão circular com paredes de roundels, colunas e galeria, piso de
// grade com o tablado do console, console hexagonal de seis painéis (botões, alavancas, mostradores, luzes
// indicadoras e uma tela por painel) e o rotor do tempo ao centro (coluna de vidro, anéis concêntricos e
// cilindros internos que sobem e descem, núcleo de luz).
//
// Nada aqui inventa atividade: o rotor segue o modo REAL do motor (repouso, processando, operação, consulta
// do JARVIS, falha), cada painel acende só enquanto uma tarefa real do seu tipo roda, pisca ao terminar
// (âmbar = concluiu, vermelho = falhou) e as telas mostram o texto que o motor informou. Sem motor, a sala
// fica apagada e diz isso.
import * as THREE from 'three';
import { ULTRON_RED } from './ultron.js';
import { Batch, disposer, canvasTexture, glowMaterial, glowTexture, physical, textPlate, PALETTE } from './materials.js';

export const PANEL_KEYS = ['analise', 'planejamento', 'arquivo', 'rotinas', 'telemetria', 'diagnostico'];
export const PANEL_LABELS = { analise: 'ANÁLISE', planejamento: 'PLANEJAMENTO', arquivo: 'ARQUIVO', rotinas: 'ROTINAS',
                              telemetria: 'TELEMETRIA', diagnostico: 'DIAGNÓSTICO' };
const ROOM_R = 9.0, ROOM_H = 6.6, DAIS_R = 3.4, DAIS_H = 0.3;
const R_IN = 0.44, R_OUT = 1.58, Y_IN = DAIS_H + 1.16, Y_OUT = DAIS_H + 0.93;
const SLOPE = Math.atan2(Y_IN - Y_OUT, R_OUT - R_IN);
const R_MID = (R_IN + R_OUT) / 2, Y_MID = (Y_IN + Y_OUT) / 2, L = (R_OUT - R_IN) / Math.cos(SLOPE);
const TAN30 = Math.tan(Math.PI / 6);
const ROTOR_Y0 = Y_IN + 0.04, ROTOR_H = 2.3;
export const panelAngle = (i) => -i * Math.PI / 3;                 // ANÁLISE de frente (+z), depois em sentido horário
// onde o holograma do JARVIS fica dentro da sala: sobre o tablado, à direita do console no enquadramento padrão,
// virado para os painéis (3/4 para quem olha) — a inteligência que opera a nave
const SPOT_A = 0.78, SPOT_R = 2.25;
export const JARVIS_SPOT = { x: Math.sin(SPOT_A) * SPOT_R, y: DAIS_H, z: Math.cos(SPOT_A) * SPOT_R,
                             rotY: SPOT_A + Math.PI - 0.95 };

const lerp = (a, b, t) => a + (b - a) * t;
const AMBER = new THREE.Color(0xffb347), RED = new THREE.Color(0xff4d5e), DIMC = new THREE.Color(0x1a2a3c);
const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _e = new THREE.Euler(), _v = new THREE.Vector3(),
      _s = new THREE.Vector3(1, 1, 1), _c = new THREE.Color();

function panelFrame(i) {
  const a = panelAngle(i);
  return new THREE.Matrix4().compose(new THREE.Vector3(Math.sin(a) * R_MID, Y_MID, Math.cos(a) * R_MID),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(SLOPE, a, 0, 'YXZ')), new THREE.Vector3(1, 1, 1));
}
const halfWidth = (z) => (R_MID + z * Math.cos(SLOPE)) * TAN30 * 0.985;

/** Instâncias de uma peça repetida (botões, luzes...) com matrizes locais a um quadro de painel. */
class Parts {
  constructor(geometry, material, count) {
    this.mesh = new THREE.InstancedMesh(disposer.track(geometry), material, count);
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.n = 0; this.frames = []; this.locals = [];
  }
  add(frame, local) {
    const i = this.n++;
    this.frames.push(frame); this.locals.push(local.clone());
    this.mesh.setMatrixAt(i, _m.multiplyMatrices(frame, local));
    return i;
  }
  set(i, local) { this.mesh.setMatrixAt(i, _m.multiplyMatrices(this.frames[i], local)); }
  color(i, c) { this.mesh.setColorAt(i, c); }
  done() { this.mesh.count = this.n; this.mesh.instanceMatrix.needsUpdate = true; if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true; }
}
/** Superfície vista por dentro: inverte a ordem dos triângulos e as normais (paredes, teto). */
function inside(geo) {
  const idx = geo.index;
  for (let i = 0; i < idx.count; i += 3) { const a = idx.getX(i + 1); idx.setX(i + 1, idx.getX(i + 2)); idx.setX(i + 2, a); }
  const n = geo.attributes.normal;
  for (let i = 0; i < n.count; i++) n.setXYZ(i, -n.getX(i), -n.getY(i), -n.getZ(i));
  return geo;
}
const local = (x, y, z, rx = 0, ry = 0, rz = 0, s = 1) =>
  new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)),
                              new THREE.Vector3(s, s, s));

export class TardisRoom {
  constructor({ particleScale = 1 } = {}) {
    const P = physical();
    this.P = P;
    this.group = new THREE.Group();
    this.group.name = 'sala-da-tardis';
    this._buildShell(P);
    this._buildConsole(P);
    this._buildRotor(P);
    this._buildScreens();
    this._buildLink(particleScale);
    this._buildDoors(P);
    this._buildFurniture(P);
    this._buildGyro(P);
    // luzes: rotor (cor do modo), luz de serviço sobre o console, ambiente quente e fria
    this.rotorLight = new THREE.PointLight(0xffb347, 6, 9, 1.6);
    this.rotorLight.position.set(0, ROTOR_Y0 + 1.0, 0);
    const key = new THREE.SpotLight(0xfff0dc, 18, 16, 0.6, 0.7, 1.4);
    key.position.set(0, 6.2, 3.4); key.target.position.set(0, 1.0, 0);
    const hemi = new THREE.HemisphereLight(0x6e7f99, 0x140c06, 0.55);
    const back = new THREE.PointLight(0x2b8cff, 10, 14, 1.8);
    back.position.set(0, 4.2, -6.5);
    this.group.add(this.rotorLight, key, key.target, hemi, back);
    // estado (alvos vindos do motor; tudo é amortecido)
    this.st = { speed: 0.12, amplitude: 0.3, brightness: 0.42, spin: 0.05, color: new THREE.Color().setRGB(214 / 255, 140 / 255, 52 / 255, THREE.SRGBColorSpace),
                beam: 0, fault: 0, available: true };
    this.target = { speed: 0.12, amplitude: 0.3, brightness: 0.42, spin: 0.05, color: this.st.color.clone(), beam: 0, fault: 0 };
    this.phase = 0; this.spinA = 0;
    this.panels = Object.fromEntries(PANEL_KEYS.map((k) => [k, { level: 0, flash: 0, fault: 0, running: 0, last: '', tl: 0, tf: 0, tx: 0 }]));
    this.selected = ''; this.hover = '';
    this.engine = { mode: 'repouso', label: 'REPOUSO', fault: false };
  }

  // ------------------------------------------------------------ casca: piso, tablado, paredes, teto
  _buildShell(P) {
    const b = new Batch();
    const roundelTex = canvasTexture(256, 256, (g, w, h) => {
      const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
      r.addColorStop(0, '#f6e3c0'); r.addColorStop(0.5, '#d9b47a'); r.addColorStop(0.85, '#6e5230'); r.addColorStop(1, '#2a1e12');
      g.fillStyle = r; g.fillRect(0, 0, w, h);
      g.strokeStyle = 'rgba(80,50,20,0.35)'; g.lineWidth = 3;
      for (const rr of [40, 70, 100]) { g.beginPath(); g.arc(w / 2, h / 2, rr, 0, Math.PI * 2); g.stroke(); }
    });
    this.roundelMat = disposer.track(new THREE.MeshStandardMaterial({ color: 0xd8c8a8, map: roundelTex, emissive: 0xffd9a0,
                                                                      emissiveMap: roundelTex, emissiveIntensity: 0.3, roughness: 0.6 }));
    this._roundelBase = this.roundelMat.emissive.clone();
    const wallMat = disposer.track(new THREE.MeshStandardMaterial({ color: 0x3a3f47, metalness: 0.55, roughness: 0.5,
      map: canvasTexture(512, 512, (g, w, h) => {
        g.fillStyle = '#9aa0a8'; g.fillRect(0, 0, w, h);
        for (let i = 0; i < 4000; i++) { const v = 120 + Math.random() * 60; g.fillStyle = `rgba(${v},${v},${v},0.08)`; g.fillRect(Math.random() * w, Math.random() * h, 2, 2); }
        g.strokeStyle = 'rgba(30,30,34,0.5)'; g.lineWidth = 4; g.strokeRect(0, 0, w, h);
      }, { repeat: [24, 3] }) }));
    const mats = { grate: P.grate, dark: P.darkMetal, metal: P.metal, brass: P.brass, wall: wallMat, copper: P.copper };
    // piso de grade e tablado do console (com degrau)
    b.put(new THREE.CircleGeometry(ROOM_R, 96).rotateX(-Math.PI / 2), 'grate', [0, 0, 0]);
    b.put(new THREE.CylinderGeometry(DAIS_R, DAIS_R, DAIS_H, 96, 1, true), 'dark', [0, DAIS_H / 2, 0]);
    b.put(new THREE.CircleGeometry(DAIS_R, 96).rotateX(-Math.PI / 2), 'grate', [0, DAIS_H, 0]);
    b.put(new THREE.RingGeometry(DAIS_R, DAIS_R + 0.45, 96, 1).rotateX(-Math.PI / 2), 'dark', [0, 0.15, 0]);
    b.put(new THREE.CylinderGeometry(DAIS_R + 0.45, DAIS_R + 0.45, 0.15, 96, 1, true), 'metal', [0, 0.075, 0]);
    // paredes e faixas
    b.put(inside(new THREE.CylinderGeometry(ROOM_R, ROOM_R, ROOM_H, 96, 1, true)), 'wall', [0, ROOM_H / 2, 0]);
    b.put(inside(new THREE.CylinderGeometry(ROOM_R - 0.05, ROOM_R - 0.05, 0.9, 96, 1, true)), 'dark', [0, 0.45, 0]);
    b.put(new THREE.TorusGeometry(ROOM_R - 0.08, 0.05, 8, 160).rotateX(Math.PI / 2), 'brass', [0, 0.92, 0]);
    // galeria superior: passarela em anel com guarda-corpo
    b.put(new THREE.RingGeometry(ROOM_R - 1.6, ROOM_R - 0.05, 96, 1).rotateX(-Math.PI / 2), 'grate', [0, 3.6, 0]);
    b.put(new THREE.RingGeometry(ROOM_R - 1.6, ROOM_R - 0.05, 96, 1).rotateX(Math.PI / 2), 'dark', [0, 3.58, 0]);
    b.put(new THREE.CylinderGeometry(ROOM_R - 1.6, ROOM_R - 1.6, 0.16, 96, 1, true), 'metal', [0, 3.52, 0]);
    b.put(new THREE.TorusGeometry(ROOM_R - 1.6, 0.025, 6, 160).rotateX(Math.PI / 2), 'brass', [0, 4.55, 0]);
    b.put(new THREE.TorusGeometry(ROOM_R - 1.6, 0.015, 6, 160).rotateX(Math.PI / 2), 'metal', [0, 4.1, 0]);
    for (let i = 0; i < 48; i++) {
      const a = (i / 48) * Math.PI * 2;
      b.put(new THREE.CylinderGeometry(0.018, 0.018, 0.95, 6), 'metal', [Math.sin(a) * (ROOM_R - 1.6), 4.07, Math.cos(a) * (ROOM_R - 1.6)]);
    }
    // teto: aro e nervuras que convergem para a coluna do rotor
    b.put(inside(new THREE.CylinderGeometry(ROOM_R, ROOM_R * 0.92, 0.5, 96, 1, true)), 'dark', [0, ROOM_H + 0.25, 0]);
    b.put(inside(new THREE.CylinderGeometry(0.01, ROOM_R * 0.92, 2.6, 96, 1, true)), 'wall', [0, ROOM_H + 1.8, 0]);
    const ribCurve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(ROOM_R - 0.15, 0, 0), new THREE.Vector3(ROOM_R - 0.2, ROOM_H + 1.0, 0),
                                                     new THREE.Vector3(0.75, ROOM_H + 1.7, 0));
    for (let i = 0; i < 12; i++) {
      const a = (i / 12) * Math.PI * 2 + Math.PI / 12;
      b.add(new THREE.TubeGeometry(ribCurve, 36, 0.17, 10, false), new THREE.Matrix4().makeRotationY(a), 'dark');
      b.add(new THREE.TubeGeometry(ribCurve, 36, 0.03, 6, false), new THREE.Matrix4().makeRotationY(a).multiply(new THREE.Matrix4().makeTranslation(-0.16, 0, 0)), 'brass');
    }
    b.build(mats, this.group);

    // roundels: discos recuados com aro (instanciados — duas chamadas de desenho para todos)
    const cols = 24, rows = 3, gaps = new Set([0, 12]);              // aberturas: porta (0) e fundo (12)
    const disc = new THREE.InstancedMesh(disposer.track(new THREE.CircleGeometry(0.42, 40)), this.roundelMat, cols * rows);
    const rim = new THREE.InstancedMesh(disposer.track(new THREE.TorusGeometry(0.44, 0.045, 8, 40)), P.metal, cols * rows);
    let n = 0;
    for (let c = 0; c < cols; c++) {
      if (gaps.has(c)) continue;
      const a = (c / cols) * Math.PI * 2;
      for (let r = 0; r < rows; r++) {
        const y = 1.45 + r * 1.05 + (r === 2 ? 0.95 : 0);
        _q.setFromEuler(_e.set(0, a + Math.PI, 0));
        _m.compose(_v.set(Math.sin(a) * (ROOM_R - 0.06), y, Math.cos(a) * (ROOM_R - 0.06)), _q, _s);
        disc.setMatrixAt(n, _m);
        _m.compose(_v.set(Math.sin(a) * (ROOM_R - 0.1), y, Math.cos(a) * (ROOM_R - 0.1)), _q, _s);
        rim.setMatrixAt(n, _m);
        n++;
      }
    }
    disc.count = rim.count = n;
    this.group.add(disc, rim);
    // colunas de luz entre os roundels
    const colGeo = disposer.track(new THREE.BoxGeometry(0.22, ROOM_H - 1.0, 0.22));
    const stripGeo = disposer.track(new THREE.BoxGeometry(0.03, ROOM_H - 1.6, 0.03));
    const columns = new THREE.InstancedMesh(colGeo, P.darkMetal, 12), strips = new THREE.InstancedMesh(stripGeo, glowMaterial(0x6fb8ff, 0.6), 12);
    for (let i = 0; i < 12; i++) {
      const a = (i / 12) * Math.PI * 2 + Math.PI / 12;
      _q.setFromEuler(_e.set(0, a, 0));
      columns.setMatrixAt(i, _m.compose(_v.set(Math.sin(a) * (ROOM_R - 0.18), 0.9 + (ROOM_H - 1.0) / 2, Math.cos(a) * (ROOM_R - 0.18)), _q, _s));
      strips.setMatrixAt(i, _m.compose(_v.set(Math.sin(a) * (ROOM_R - 0.31), 1.2 + (ROOM_H - 1.6) / 2, Math.cos(a) * (ROOM_R - 0.31)), _q, _s));
    }
    this.group.add(columns, strips);
    // luz sob o tablado (poço iluminado ao redor do console) e anel de falha
    this.wellMat = glowMaterial(0xffb347, 0.22);
    const well = new THREE.Mesh(disposer.track(new THREE.RingGeometry(1.9, 2.5, 96, 1)), this.wellMat);
    well.rotation.x = -Math.PI / 2; well.position.y = DAIS_H - 0.02;
    this.daisEdge = new THREE.Mesh(disposer.track(new THREE.TorusGeometry(DAIS_R, 0.015, 6, 200)), glowMaterial(0xffb347, 0.6));
    this.daisEdge.rotation.x = Math.PI / 2; this.daisEdge.position.y = DAIS_H + 0.005;
    this.faultRing = new THREE.Mesh(disposer.track(new THREE.RingGeometry(DAIS_R + 0.6, DAIS_R + 0.75, 160, 1)), glowMaterial(0xff4d5e, 0));
    this.faultRing.rotation.x = -Math.PI / 2; this.faultRing.position.y = 0.02;
    this.group.add(well, this.daisEdge, this.faultRing);
  }

  // ------------------------------------------------------------ console de seis painéis
  _buildConsole(P) {
    const b = new Batch();
    const mats = { panel: P.panel, dark: P.darkMetal, brass: P.brass, metal: P.metal, rubber: P.rubber };
    // pedestal hexagonal com respiros e base
    b.put(new THREE.CylinderGeometry(0.78, 0.98, Y_OUT - DAIS_H - 0.12, 6, 1).rotateY(Math.PI / 6), 'dark', [0, DAIS_H + (Y_OUT - DAIS_H - 0.12) / 2, 0]);
    b.put(new THREE.CylinderGeometry(1.05, 1.12, 0.08, 6, 1).rotateY(Math.PI / 6), 'metal', [0, DAIS_H + 0.04, 0]);
    for (let i = 0; i < 6; i++) {
      const a = panelAngle(i);
      for (let k = 0; k < 5; k++) b.put(new THREE.BoxGeometry(0.62, 0.02, 0.03), 'rubber',
        [Math.sin(a) * 0.86, DAIS_H + 0.25 + k * 0.1, Math.cos(a) * 0.86], [0.25, a, 0]);
    }
    // anel interno (em volta do rotor) e aro externo de latão
    b.put(new THREE.CylinderGeometry(R_IN, R_IN + 0.04, 0.12, 6, 1, true).rotateY(Math.PI / 6), 'brass', [0, Y_IN - 0.02, 0]);
    this.panelMeshes = [];
    const slabShape = (inset = 0, flip = 1) => {
      const s = new THREE.Shape(), z0 = -L / 2 + inset, z1 = L / 2 - inset;
      s.moveTo(-halfWidth(z0) + inset, flip * z0); s.lineTo(halfWidth(z0) - inset, flip * z0);
      s.lineTo(halfWidth(z1) - inset, flip * z1); s.lineTo(-halfWidth(z1) + inset, flip * z1); s.closePath();
      return s;
    };
    const slabGeo = disposer.track(new THREE.ExtrudeGeometry(slabShape(), { depth: 0.06, bevelEnabled: true, bevelThickness: 0.012,
                                                                             bevelSize: 0.012, bevelSegments: 2 }).rotateX(Math.PI / 2));
    const insetGeo = new THREE.ShapeGeometry(slabShape(0.07, -1)).rotateX(-Math.PI / 2);
    this.frames = PANEL_KEYS.map((_, i) => panelFrame(i));
    // peças instanciadas de todos os painéis
    const glowBasic = () => disposer.track(new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: true }));
    this.btnBase = new Parts(new THREE.CylinderGeometry(0.03, 0.032, 0.02, 16), P.metal, 72);
    this.btnCap = new Parts(new THREE.CylinderGeometry(0.021, 0.023, 0.02, 16), glowBasic(), 72);
    this.dialBody = new Parts(new THREE.CylinderGeometry(0.072, 0.078, 0.03, 32), P.brass, 12);
    const dialTex = canvasTexture(128, 128, (g, w, h) => {
      g.fillStyle = '#0b1622'; g.beginPath(); g.arc(w / 2, h / 2, w / 2, 0, Math.PI * 2); g.fill();
      g.strokeStyle = '#e8d6b0'; g.lineWidth = 3;
      for (let i = 0; i <= 10; i++) { const a = Math.PI * (0.75 + 1.5 * i / 10); g.beginPath();
        g.moveTo(w / 2 + Math.cos(a) * 44, h / 2 + Math.sin(a) * 44); g.lineTo(w / 2 + Math.cos(a) * 56, h / 2 + Math.sin(a) * 56); g.stroke(); }
    });
    this.dialFace = new Parts(new THREE.CircleGeometry(0.062, 32).rotateX(-Math.PI / 2), disposer.track(new THREE.MeshBasicMaterial({ map: dialTex })), 12);
    this.needle = new Parts(new THREE.BoxGeometry(0.006, 0.004, 0.05).translate(0, 0, -0.022), glowBasic(), 12);
    this.leverBase = new Parts(new THREE.BoxGeometry(0.05, 0.03, 0.08), P.darkMetal, 18);
    this.leverStick = new Parts(new THREE.CylinderGeometry(0.007, 0.008, 0.15, 8).translate(0, 0.075, 0), P.steel, 18);
    this.leverKnob = new Parts(new THREE.SphereGeometry(0.019, 12, 8).translate(0, 0.15, 0), glowBasic(), 18);
    this.lamps = new Parts(new THREE.SphereGeometry(0.016, 12, 8), glowBasic(), 48);
    this.layout = PANEL_KEYS.map(() => ({ buttons: [], dials: [], levers: [], lamps: [] }));
    PANEL_KEYS.forEach((key, i) => {
      const F = this.frames[i], lay = this.layout[i];
      const slab = new THREE.Mesh(slabGeo, P.panel);
      slab.applyMatrix4(F);
      slab.userData.panel = key;
      this.group.add(slab);
      this.panelMeshes.push(slab);
      b.add(insetGeo.clone(), F.clone().multiply(new THREE.Matrix4().makeTranslation(0, 0.002, 0)), 'dark');
      // avental vertical sob a borda externa
      const zo = L / 2;
      b.add(new THREE.BoxGeometry(halfWidth(zo) * 2 * 0.96, 0.24, 0.04), F.clone().multiply(local(0, -0.17, zo - 0.02, -SLOPE)), 'panel');
      b.add(new THREE.BoxGeometry(halfWidth(zo) * 2, 0.025, 0.05), F.clone().multiply(local(0, 0.01, zo, 0)), 'brass');
      // botões: duas fileiras
      for (let r = 0; r < 2; r++) for (let c = 0; c < 6; c++) {
        const z = -0.02 + r * 0.1, x = (c - 2.5) * 0.085;
        lay.buttons.push(this.btnBase.add(F, local(x, 0.01, z)));
        this.btnCap.add(F, local(x, 0.025, z));
      }
      // mostradores (o ponteiro marca a atividade real do painel)
      for (const x of [-0.36, 0.36]) {
        const d = this.dialBody.add(F, local(x, 0.015, 0.2));
        this.dialFace.add(F, local(x, 0.032, 0.2));
        this.needle.add(F, local(x, 0.036, 0.2));
        lay.dials.push(d);
      }
      // alavancas (ficam "ligadas" enquanto uma tarefa do painel roda)
      for (const x of [-0.12, 0, 0.12]) {
        const l = this.leverBase.add(F, local(x, 0.015, 0.24));
        this.leverStick.add(F, local(x, 0.03, 0.24, 0.55));
        this.leverKnob.add(F, local(x, 0.03, 0.24, 0.55));
        lay.levers.push(l);
      }
      // luzes indicadoras ao longo da borda externa
      for (let k = 0; k < 8; k++) lay.lamps.push(this.lamps.add(F, local((k - 3.5) * 0.12, 0.016, 0.42)));
      // tela do painel (em pé, voltada para quem está diante do console)
      b.add(new THREE.BoxGeometry(0.5, 0.31, 0.05), F.clone().multiply(local(0, 0.15, -0.3, -1.05)), 'dark');
    });
    for (const p of [this.btnBase, this.btnCap, this.dialBody, this.dialFace, this.needle, this.leverBase, this.leverStick, this.leverKnob, this.lamps]) {
      p.done();
      this.group.add(p.mesh);
    }
    for (let i = 0; i < this.btnCap.n; i++) this.btnCap.color(i, DIMC);
    for (let i = 0; i < this.lamps.n; i++) this.lamps.color(i, DIMC);
    for (let i = 0; i < this.leverKnob.n; i++) this.leverKnob.color(i, DIMC);
    for (let i = 0; i < this.needle.n; i++) this.needle.color(i, _c.set(0xffe2b0));
    b.build(mats, this.group);
    // telas e placas com o nome (textos reais por painel) + contorno de seleção
    this.panelScreens = PANEL_KEYS.map((key, i) => {
      const F = this.frames[i];
      const plate = textPlate(512, 320, (g, w, h, d) => this._paintPanelScreen(g, w, h, key, d));
      const screen = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(0.44, 0.26)), glowMaterial(0xffffff, 0.95, { map: plate.texture }));
      screen.applyMatrix4(F.clone().multiply(local(0, 0.15, -0.3, -1.05)).multiply(new THREE.Matrix4().makeTranslation(0, 0, 0.027)));
      const name = textPlate(512, 64, (g, w, h, lit) => {
        g.fillStyle = lit ? 'rgba(255,190,110,1)' : 'rgba(210,170,110,0.8)';
        g.font = '600 40px Segoe UI, Arial'; g.textAlign = 'center'; g.textBaseline = 'middle';
        g.fillText(PANEL_LABELS[key].split('').join(' '), w / 2, h / 2 + 2);
      });
      const zo = L / 2;
      const label = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(0.62, 0.078)), glowMaterial(0xffffff, 0.9, { map: name.texture }));
      label.applyMatrix4(F.clone().multiply(local(0, -0.12, zo + 0.003, -SLOPE)));
      const outline = this._outline(F);
      this.group.add(screen, label, outline);
      plate.draw({ state: 'idle' });
      name.draw(false);
      return { plate, name, outline, lit: false, key: '' };
    });
  }

  _outline(F) {
    const pts = [], zs = [-L / 2, L / 2];
    for (const [x, z] of [[-1, zs[0]], [1, zs[0]], [1, zs[1]], [-1, zs[1]], [-1, zs[0]]]) pts.push(new THREE.Vector3(x * halfWidth(z), 0.03, z));
    const g = disposer.track(new THREE.BufferGeometry().setFromPoints(pts));
    const line = new THREE.Line(g, disposer.track(new THREE.LineBasicMaterial({ color: 0xffc070, transparent: true, opacity: 0,
                                                                                 blending: THREE.AdditiveBlending, depthWrite: false })));
    line.applyMatrix4(F);
    return line;
  }

  _paintPanelScreen(g, w, h, key, d) {
    g.fillStyle = 'rgba(8,16,26,0.92)'; g.fillRect(0, 0, w, h);
    const color = d.state === 'fault' ? '#ff6b7d' : (d.state === 'running' ? '#ffc070' : (d.state === 'off' ? '#5d6f82' : '#9fd8ff'));
    g.strokeStyle = color; g.globalAlpha = 0.6; g.lineWidth = 3; g.strokeRect(6, 6, w - 12, h - 12); g.globalAlpha = 1;
    g.fillStyle = color; g.font = '600 34px Segoe UI, Arial'; g.fillText(PANEL_LABELS[key], 24, 54);
    g.font = '26px Segoe UI, Arial'; g.fillStyle = '#dcefff';
    const status = { running: `em execução${d.running > 1 ? ` (${d.running})` : ''}`, fault: 'a última tarefa falhou',
                     done: 'última tarefa concluída', idle: 'sem tarefa nesta sessão', off: 'TARDIS indisponível' }[d.state] || '';
    g.fillText(status, 24, 100);
    g.font = '22px Segoe UI, Arial'; g.fillStyle = 'rgba(200,225,245,0.85)';
    const words = String(d.last || '').split(/\s+/); let line = '', y = 148;
    for (const word of words) {
      if (g.measureText(line + word).width > w - 48) { g.fillText(line, 24, y); y += 32; line = ''; if (y > h - 30) break; }
      line += word + ' ';
    }
    if (line && y <= h - 30) g.fillText(line, 24, y);
  }

  // ------------------------------------------------------------ rotor do tempo
  _buildRotor(P) {
    const b = new Batch();
    const mats = { brass: P.brass, metal: P.metal, dark: P.darkMetal, copper: P.copper };
    const top = ROTOR_Y0 + ROTOR_H;
    b.put(new THREE.CylinderGeometry(0.42, 0.46, 0.1, 48), 'brass', [0, ROTOR_Y0 + 0.05, 0]);
    b.put(new THREE.TorusGeometry(0.4, 0.025, 8, 64).rotateX(Math.PI / 2), 'metal', [0, ROTOR_Y0 + 0.11, 0]);
    b.put(new THREE.CylinderGeometry(0.46, 0.42, 0.14, 48), 'brass', [0, top + 0.07, 0]);
    b.put(new THREE.TorusGeometry(0.4, 0.025, 8, 64).rotateX(Math.PI / 2), 'metal', [0, top - 0.01, 0]);
    // coluna até o teto, com anéis
    b.put(new THREE.CylinderGeometry(0.28, 0.36, ROOM_H + 1.7 - top, 24, 1, true), 'dark', [0, (top + ROOM_H + 1.7) / 2, 0]);
    for (let k = 0; k < 5; k++) b.put(new THREE.TorusGeometry(0.33 - k * 0.008, 0.03, 8, 40).rotateX(Math.PI / 2), 'copper', [0, top + 0.5 + k * 0.75, 0]);
    // estrutura vertical: quatro hastes de latão em volta do vidro
    for (let i = 0; i < 4; i++) {
      const a = i * Math.PI / 2 + Math.PI / 4;
      b.put(new THREE.CylinderGeometry(0.018, 0.018, ROTOR_H, 8), 'brass', [Math.cos(a) * 0.43, ROTOR_Y0 + ROTOR_H / 2, Math.sin(a) * 0.43]);
    }
    b.build(mats, this.group);
    // vidro com faixa de luz que percorre (pulso)
    this.glassMat = disposer.track(new THREE.ShaderMaterial({
      uniforms: { uColor: { value: new THREE.Color(0xffb347) }, uTime: { value: 0 }, uPulse: { value: 0 }, uBright: { value: 0.4 } },
      vertexShader: 'varying vec2 vUv; varying vec3 vN; varying vec3 vV; void main(){ vUv=uv; vN=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(position,1.0); vV=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }',
      fragmentShader: `uniform vec3 uColor; uniform float uTime; uniform float uPulse; uniform float uBright; varying vec2 vUv; varying vec3 vN; varying vec3 vV;
        void main(){ float rim=pow(1.0-abs(dot(vN,vV)),2.0); float band=exp(-pow((vUv.y-fract(uTime*0.35))*9.0,2.0))*uPulse;
          float lines=0.5+0.5*sin(vUv.x*6.2831*12.0); gl_FragColor=vec4(mix(vec3(0.75,0.9,1.0),uColor,0.6), (0.03+rim*0.22)*(0.6+0.4*lines)*(0.4+0.6*uBright) + band*0.28); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    const glass = new THREE.Mesh(disposer.track(new THREE.CylinderGeometry(0.36, 0.36, ROTOR_H - 0.12, 48, 1, true)), this.glassMat);
    glass.position.y = ROTOR_Y0 + ROTOR_H / 2;
    // núcleo de luz e tubos
    this.coreMat = glowMaterial(0xffb347, 0.9);
    this.core = new THREE.Mesh(disposer.track(new THREE.CylinderGeometry(0.045, 0.045, ROTOR_H - 0.2, 16, 1, true)), this.coreMat);
    this.core.position.y = ROTOR_Y0 + ROTOR_H / 2;
    this.coreGlow = new THREE.Sprite(disposer.track(new THREE.SpriteMaterial({ map: glowTexture(), color: 0xffb347, transparent: true,
                                                                                opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false })));
    this.coreGlow.scale.set(0.8, 2.3, 1); this.coreGlow.position.y = ROTOR_Y0 + ROTOR_H / 2;
    this.tubeMat = disposer.track(new THREE.ShaderMaterial({
      uniforms: { uColor: { value: new THREE.Color(0xffb347) }, uTime: { value: 0 }, uFlow: { value: 0.2 }, uBright: { value: 0.4 } },
      vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: 'uniform vec3 uColor; uniform float uTime; uniform float uFlow; uniform float uBright; varying vec2 vUv; void main(){ float s=pow(0.5+0.5*sin(vUv.y*40.0-uTime*uFlow*18.0),6.0); gl_FragColor=vec4(uColor,(0.08+0.4*s)*uBright); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    const tubeGeo = disposer.track(new THREE.CylinderGeometry(0.014, 0.014, ROTOR_H - 0.25, 8, 1, true));
    this.tubes = new THREE.Group();
    for (let i = 0; i < 6; i++) {
      const a = i * Math.PI / 3;
      const t = new THREE.Mesh(tubeGeo, this.tubeMat);
      t.position.set(Math.cos(a) * 0.2, ROTOR_Y0 + ROTOR_H / 2, Math.sin(a) * 0.2);
      this.tubes.add(t);
    }
    // conjuntos de anéis concêntricos: o de cima desce e o de baixo sobe (curso real do modo)
    const ringSet = (y, flip) => {
      const g = new THREE.Group();
      g.position.y = y;
      const parts = [];
      for (let k = 0; k < 4; k++) {
        const r = 0.29 - k * 0.055;
        const ring = new THREE.Mesh(disposer.track(new THREE.TorusGeometry(r, 0.012 + k * 0.002, 8, 48)), k % 2 ? P.brass : P.steel);
        ring.rotation.x = Math.PI / 2;
        ring.position.y = flip * k * 0.05;
        const plate = new THREE.Mesh(disposer.track(new THREE.CylinderGeometry(r - 0.01, r - 0.01, 0.012, 6, 1, true)), P.copper);
        plate.position.y = ring.position.y;
        g.add(ring, plate);
        parts.push(ring);
      }
      const cap = new THREE.Mesh(disposer.track(new THREE.CylinderGeometry(0.075, 0.09, 0.08, 6)), P.brass);
      cap.position.y = flip * 0.2;
      g.add(cap);
      return { g, parts, y };
    };
    // filamentos de energia azul em hélice em volta do núcleo âmbar: correm para cima com a atividade REAL
    const strands = [];
    for (let k = 0; k < 5; k++) {
      const pts = [], along = [];
      for (let i = 0; i <= 160; i++) {
        const f = i / 160, a = k * Math.PI * 2 / 5 + f * Math.PI * 2 * 5;
        const r = k % 2 ? 0.16 : 0.115;
        pts.push(Math.cos(a) * r, ROTOR_Y0 + 0.2 + f * (ROTOR_H - 0.45), Math.sin(a) * r);
        along.push(f);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
      g.setAttribute('along', new THREE.Float32BufferAttribute(along, 1));
      disposer.track(g);
      strands.push(g);
    }
    this.strandMat = disposer.track(new THREE.ShaderMaterial({
      uniforms: { uTime: { value: 0 }, uFlow: { value: 0.1 }, uBright: { value: 0.4 }, uColor: { value: new THREE.Color(0x3aa8ff) } },
      vertexShader: 'attribute float along; varying float vA; void main(){ vA=along; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: 'uniform float uTime; uniform float uFlow; uniform float uBright; uniform vec3 uColor; varying float vA; void main(){ float h=fract(vA*3.0-uTime*uFlow); float pulse=smoothstep(0.75,1.0,h); gl_FragColor=vec4(uColor*(1.4+pulse*2.2),(0.3+1.2*pulse)*uBright); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.strands = new THREE.Group();
    for (const g of strands) this.strands.add(new THREE.Line(g, this.strandMat));
    this.group.add(this.strands);
    this.ringLow = ringSet(ROTOR_Y0 + 0.45, 1);
    this.ringHigh = ringSet(ROTOR_Y0 + ROTOR_H - 0.45, -1);
    this.group.add(glass, this.core, this.coreGlow, this.tubes, this.ringLow.g, this.ringHigh.g);
  }

  // ------------------------------------------------------------ telas holográficas sobre o console
  _buildScreens() {
    this.screenGroup = new THREE.Group();
    this.screens = {};
    const paint = (g, w, h, data) => {
      if (!data) return;
      const [title, lines, rgb] = data;
      const col = `rgb(${rgb.map((v) => Math.round(v)).join(',')})`;
      g.fillStyle = 'rgba(6,18,30,0.55)'; g.fillRect(0, 0, w, h);
      g.strokeStyle = col; g.globalAlpha = 0.7; g.lineWidth = 2; g.strokeRect(2, 2, w - 4, h - 4); g.globalAlpha = 1;
      g.fillStyle = col; g.fillRect(2, 2, 120, 5);
      g.font = '600 30px Segoe UI, Arial'; g.fillText(String(title).slice(0, 34), 22, 50);
      g.font = '24px Segoe UI, Arial'; g.fillStyle = '#e6f3ff';
      let y = 96;
      for (const raw of lines || []) {
        let line = '';
        for (const word of String(raw).split(/\s+/)) {
          if (g.measureText(line + word).width > w - 44) { g.fillText(line, 22, y); y += 32; line = ''; }
          line += word + ' ';
          if (y > h - 20) break;
        }
        if (y <= h - 20 && line) { g.fillText(line, 22, y); y += 34; }
      }
    };
    for (const [slot, x] of [['left', -1.15], ['right', 1.15], ['center', 0]]) {
      const plate = textPlate(640, 300, paint);
      const mesh = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(1.15, 0.54)), glowMaterial(0xffffff, 0.92, { map: plate.texture }));
      mesh.position.set(x, 2.75 + (slot === 'center' ? 0.45 : 0), 0.9);
      mesh.rotation.y = -x * 0.35;
      mesh.visible = false;
      this.screenGroup.add(mesh);
      this.screens[slot] = { plate, mesh, key: '' };
    }
    this.group.add(this.screenGroup);
  }

  // ------------------------------------------------------------ elo JARVIS ⇄ TARDIS (só com tarefa do JARVIS rodando)
  _buildLink(particleScale) {
    this.maxLink = 220;
    const seeds = new Float32Array(this.maxLink * 2);
    for (let i = 0; i < this.maxLink; i++) { seeds[i * 2] = Math.random(); seeds[i * 2 + 1] = Math.random(); }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.maxLink * 3), 3));
    g.setAttribute('seed', new THREE.BufferAttribute(seeds, 2));
    disposer.track(g);
    this.linkMat = disposer.track(new THREE.ShaderMaterial({
      uniforms: { uTime: { value: 0 }, uA: { value: new THREE.Vector3(0, 1.6, ROOM_R - 0.6) }, uB: { value: new THREE.Vector3(0, ROTOR_Y0 + 1.0, 0) },
                  uPower: { value: 0 }, map: { value: glowTexture() }, uColor: { value: new THREE.Color(PALETTE.cyan) }, uPixel: { value: 1 } },
      vertexShader: `attribute vec2 seed; uniform float uTime; uniform vec3 uA; uniform vec3 uB; uniform float uPixel; varying float vA;
        void main(){ float t=fract(seed.x+uTime*(0.25+0.2*seed.y)); vec3 p=mix(uA,uB,t);
          p.y+=sin(t*3.1416)*1.2; float a=seed.y*6.2831+uTime*2.0; p.x+=cos(a)*0.08*sin(t*3.1416); p.z+=sin(a)*0.08*sin(t*3.1416);
          vA=sin(t*3.1416); vec4 mv=modelViewMatrix*vec4(p,1.0); gl_PointSize=uPixel*(4.0+5.0*seed.y)*(7.0/max(-mv.z,0.3)); gl_Position=projectionMatrix*mv; }`,
      fragmentShader: 'uniform sampler2D map; uniform vec3 uColor; uniform float uPower; varying float vA; void main(){ vec4 t=texture2D(map,gl_PointCoord); gl_FragColor=vec4(uColor, t.a*vA*uPower); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.link = new THREE.Points(g, this.linkMat);
    this.link.frustumCulled = false;
    this.group.add(this.link);
    this.setParticleScale(particleScale);
  }

  // ------------------------------------------------------------ portas internas (por onde se entra)
  _buildDoors(P) {
    const g = new THREE.Group();
    g.position.set(0, 0, ROOM_R - 0.12);
    g.rotation.y = Math.PI;
    // moldura atrás, portas à frente (o lado +z local olha para o centro da sala)
    const frame = new THREE.Mesh(disposer.track(new THREE.BoxGeometry(1.5, 2.5, 0.12)), P.darkMetal);
    frame.position.set(0, 1.25, -0.07);
    const glowDoor = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(1.08, 2.08)), disposer.track(new THREE.MeshStandardMaterial({
      color: 0x15336e, map: P.wood.map, roughness: 0.6, emissive: 0x0a1a3a, emissiveIntensity: 0.6 })));
    glowDoor.position.set(0, 1.14, 0.0);
    const seam = new THREE.Mesh(disposer.track(new THREE.BoxGeometry(0.02, 2.06, 0.02)), P.black);
    seam.position.set(0, 1.14, 0.012);
    const win = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(0.9, 0.36)), glowMaterial(0xcfe4ff, 0.5));
    win.position.set(0, 1.86, 0.008);
    g.add(frame, glowDoor, seam, win);
    this.group.add(g);
    this.doorPoint = new THREE.Vector3(0, 1.6, ROOM_R - 0.6);
  }

  setParticleScale(s) { this.link.geometry.setDrawRange(0, Math.round(this.maxLink * Math.min(1, 0.5 * s + 0.2))); }

  /** Fotografia do motor vinda do Python (RoomScene + motor): modo, estilo, painéis, telas. */
  setEngine(d) {
    this.engine = d;
    const t = this.target;
    t.speed = d.speed ?? t.speed; t.amplitude = d.amplitude ?? t.amplitude; t.brightness = d.brightness ?? t.brightness;
    t.spin = d.spin ?? t.spin;
    if (d.color) t.color.setRGB(d.color[0] / 255, d.color[1] / 255, d.color[2] / 255, THREE.SRGBColorSpace);
    t.beam = d.mode === 'jarvis' ? 1 : 0;
    t.fault = d.fault ? 1 : 0;
    this.st.available = d.available !== false;
    for (const key of PANEL_KEYS) {
      const src = (d.panels || {})[key];
      const p = this.panels[key];
      if (!src) continue;
      p.tl = src.level || 0; p.running = src.running || 0;
      if ((src.flash || 0) > p.flash + 0.05) p.flash = src.flash;
      if ((src.fault || 0) > p.fault + 0.05) p.fault = src.fault;
      p.last = src.last || '';
      const state = !this.st.available ? 'off' : (p.running ? 'running' : (p.last.startsWith('falhou') ? 'fault' : (p.last ? 'done' : 'idle')));
      const scr = this.panelScreens[PANEL_KEYS.indexOf(key)];
      const k = state + '|' + p.running + '|' + p.last;
      if (scr.key !== k) { scr.key = k; scr.plate.draw({ state, running: p.running, last: p.last }); }
    }
    if (d.screens) for (const [slot, s] of Object.entries(this.screens)) {          // atualização parcial: telas ficam
      const data = d.screens[slot];
      s.mesh.visible = !!data;
      const k = JSON.stringify(data || null);
      if (data && s.key !== k) { s.key = k; s.plate.draw(data); }
    }
  }

  select(key) { this.selected = PANEL_KEYS.includes(key) ? key : ''; }
  setHover(key) { this.hover = PANEL_KEYS.includes(key) ? key : ''; }

  /** Ponto de vista de um painel (câmera diante dele, olhando a tela e os controles). */
  panelView(key) {
    const i = Math.max(0, PANEL_KEYS.indexOf(key)), a = panelAngle(i);
    const pos = new THREE.Vector3(Math.sin(a) * 3.0, 2.25, Math.cos(a) * 3.0);
    const target = new THREE.Vector3(Math.sin(a) * 0.95, 1.3, Math.cos(a) * 0.95);
    return { pos: this.group.localToWorld(pos), target: this.group.localToWorld(target) };
  }

  // ------------------------------------------------------------ mobiliário integrado (a nave é habitada)
  _buildFurniture(P) {
    const b = new Batch();
    const leather = disposer.track(new THREE.MeshStandardMaterial({ color: 0x4a2618, roughness: 0.55, metalness: 0.05 }));
    const oak = disposer.track(new THREE.MeshStandardMaterial({ color: 0x5b3c22, roughness: 0.6, metalness: 0.05 }));
    const rubber = disposer.track(new THREE.MeshStandardMaterial({ color: 0x0c0e12, roughness: 0.85 }));
    const coat = disposer.track(new THREE.MeshStandardMaterial({ color: 0x3b2f2a, roughness: 0.8 }));
    const mats = { leather, oak, rubber, coat, brass: P.brass, dark: P.darkMetal, metal: P.metal, copper: P.copper,
                   b0: disposer.track(new THREE.MeshStandardMaterial({ color: 0x6b1f1f, roughness: 0.7 })),
                   b1: disposer.track(new THREE.MeshStandardMaterial({ color: 0x1f3b6b, roughness: 0.7 })),
                   b2: disposer.track(new THREE.MeshStandardMaterial({ color: 0x2f5a2a, roughness: 0.7 })),
                   b3: disposer.track(new THREE.MeshStandardMaterial({ color: 0x7a5a2a, roughness: 0.7 })),
                   b4: disposer.track(new THREE.MeshStandardMaterial({ color: 0x3a2a4a, roughness: 0.7 })) };
    const atWall = (ang, r) => [Math.sin(ang) * r, Math.cos(ang) * r];
    // bancos curvos de couro entre as colunas, encostados na parede (três segmentos acompanhando a curva)
    for (const center of [Math.PI - 0.62, Math.PI + 0.62]) {
      for (let k = -1; k <= 1; k++) {
        const a = center + k * 0.13, [x, z] = atWall(a, ROOM_R - 0.75);
        b.put(new THREE.BoxGeometry(1.14, 0.12, 0.55), 'leather', [x, 0.48, z], [0, a, 0]);
        const [bx, bz] = atWall(a, ROOM_R - 0.48);
        b.put(new THREE.BoxGeometry(1.14, 0.62, 0.12), 'leather', [bx, 0.82, bz], [-0.12, a, 0]);
        b.put(new THREE.BoxGeometry(1.16, 0.4, 0.5), 'dark', [x, 0.22, z], [0, a, 0]);
        b.put(new THREE.BoxGeometry(1.18, 0.03, 0.57), 'brass', [x, 0.42, z], [0, a, 0]);
      }
    }
    // estante embutida atrás do rotor: livros e instrumentos (a biblioteca da nave)
    {
      const a = Math.PI, [x, z] = atWall(a, ROOM_R - 0.32);
      const frame = new THREE.Matrix4().compose(new THREE.Vector3(x, 0, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, a, 0)),
                                                new THREE.Vector3(1, 1, 1));
      b.put(new THREE.BoxGeometry(2.2, 2.5, 0.08), 'oak', [0, 1.75, -0.18], [0, 0, 0], [1, 1, 1], frame);
      for (const sx of [-1.1, 1.1]) b.put(new THREE.BoxGeometry(0.08, 2.5, 0.42), 'oak', [sx, 1.75, 0], [0, 0, 0], [1, 1, 1], frame);
      let seed = 3;
      const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
      for (let shelf = 0; shelf < 5; shelf++) {
        const y = 0.55 + shelf * 0.5;
        b.put(new THREE.BoxGeometry(2.14, 0.04, 0.4), 'oak', [0, y, 0], [0, 0, 0], [1, 1, 1], frame);
        let cx = -1.02;
        while (cx < 1.0) {
          const w = 0.03 + rnd() * 0.035, h = 0.26 + rnd() * 0.16, lean = rnd() < 0.08 ? 0.18 : 0;
          if (rnd() < 0.07) { cx += 0.08; continue; }                  // um vão aqui e ali
          b.put(new THREE.BoxGeometry(w, h, 0.22 + rnd() * 0.08), `b${Math.floor(rnd() * 5)}`, [cx + w / 2, y + 0.02 + h / 2, 0.02],
                [0, 0, lean], [1, 1, 1], frame);
          cx += w + 0.004;
        }
      }
      b.put(new THREE.SphereGeometry(0.12, 20, 14), 'brass', [0.7, 2.94, 0.04], [0, 0, 0], [1, 1, 1], frame);   // globo/instrumento
      b.put(new THREE.TorusGeometry(0.15, 0.01, 6, 28), 'copper', [0.7, 2.94, 0.04], [0.3, 0, 0.4], [1, 1, 1], frame);
    }
    // bancada de trabalho à esquerda: tampo, gaveteiro, banqueta e dois monitores (telas com texto do sistema)
    {
      const a = -Math.PI / 2 - 0.42, [x, z] = atWall(a, ROOM_R - 1.0);
      const frame = new THREE.Matrix4().compose(new THREE.Vector3(x, 0, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(0, a, 0)),
                                                new THREE.Vector3(1, 1, 1));
      b.put(new THREE.BoxGeometry(1.8, 0.06, 0.75), 'oak', [0, 0.92, 0], [0, 0, 0], [1, 1, 1], frame);
      for (const sx of [-0.85, 0.85]) b.put(new THREE.BoxGeometry(0.06, 0.9, 0.7), 'dark', [sx, 0.45, 0], [0, 0, 0], [1, 1, 1], frame);
      b.put(new THREE.BoxGeometry(0.5, 0.7, 0.6), 'metal', [0.5, 0.45, 0], [0, 0, 0], [1, 1, 1], frame);
      b.put(new THREE.CylinderGeometry(0.2, 0.2, 0.06, 20), 'leather', [-0.2, 0.66, -0.7], [0, 0, 0], [1, 1, 1], frame);
      b.put(new THREE.CylinderGeometry(0.025, 0.025, 0.63, 8), 'brass', [-0.2, 0.32, -0.7], [0, 0, 0], [1, 1, 1], frame);
      b.put(new THREE.TorusGeometry(0.16, 0.012, 6, 24), 'brass', [-0.2, 0.18, -0.7], [Math.PI / 2, 0, 0], [1, 1, 1], frame);
      const screenTex = canvasTexture(256, 160, (g, w, h) => {
        g.fillStyle = '#04121c'; g.fillRect(0, 0, w, h);
        g.strokeStyle = 'rgba(103,243,255,0.8)'; g.lineWidth = 3; g.strokeRect(3, 3, w - 6, h - 6);
        g.fillStyle = 'rgba(103,243,255,0.9)'; g.font = '600 16px Segoe UI, Arial'; g.fillText('J.A.R.V.I.S.', 14, 28);
        g.fillStyle = 'rgba(160,220,240,0.7)';
        for (let i = 0; i < 6; i++) g.fillRect(14, 46 + i * 17, 40 + ((i * 53) % 170), 6);
      });
      const screenMat = glowMaterial(0xffffff, 0.85, { map: screenTex });
      for (const [sx, ry] of [[-0.35, 0.18], [0.25, -0.12]]) {
        b.put(new THREE.BoxGeometry(0.55, 0.36, 0.03), 'dark', [sx, 1.2, 0.2], [0, ry, 0], [1, 1, 1], frame);
        const screen = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(0.5, 0.31)), screenMat);
        screen.applyMatrix4(new THREE.Matrix4().multiplyMatrices(frame, local(sx, 1.2, 0.22, 0, ry, 0)));
        this.group.add(screen);
      }
    }
    // cabideiro junto à porta, com um casaco
    {
      const [x, z] = atWall(0.32, ROOM_R - 0.8);
      b.put(new THREE.CylinderGeometry(0.025, 0.035, 1.9, 10), 'oak', [x, 0.95, z]);
      b.put(new THREE.CylinderGeometry(0.22, 0.25, 0.04, 16), 'oak', [x, 0.02, z]);
      for (let k = 0; k < 4; k++) {
        const ha = k * Math.PI / 2;
        b.put(new THREE.CylinderGeometry(0.012, 0.012, 0.22, 6), 'brass', [x + Math.sin(ha) * 0.09, 1.82, z + Math.cos(ha) * 0.09],
              [Math.cos(ha) * 0.9, 0, -Math.sin(ha) * 0.9]);
      }
      b.put(new THREE.CylinderGeometry(0.16, 0.28, 1.0, 14, 1, true), 'coat', [x + 0.12, 1.3, z], [0, 0, 0.12]);
    }
    // feixes de cabos do tablado às paredes (a máquina por baixo do piso)
    for (const ang of [2.2, 2.75, 3.5, 4.05]) {
      const pts = [];
      for (let k = 0; k <= 10; k++) {
        const t = k / 10, r = lerp(DAIS_R + 0.5, ROOM_R - 0.3, t);
        pts.push(new THREE.Vector3(Math.sin(ang + 0.15 * Math.sin(t * 3)) * r, 0.05 + 0.04 * Math.sin(t * Math.PI), Math.cos(ang + 0.15 * Math.sin(t * 3)) * r));
      }
      b.add(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 40, 0.045, 8), new THREE.Matrix4(), 'rubber');
      b.add(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map((p) => p.clone().add(_v.set(0.1, 0.02, 0.06)))), 40, 0.028, 8),
            new THREE.Matrix4(), 'copper');
    }
    b.build(mats, this.group);
  }

  // ------------------------------------------------------------ giroscópio do rotor (gira com o modo real)
  _buildGyro(P) {
    this.gyro = new THREE.Group();
    this.gyro.position.y = ROTOR_Y0 + ROTOR_H * 0.52;
    this.gyroRings = [];
    [[0.24, P.brass], [0.205, P.steel], [0.17, P.copper]].forEach(([r, mat], i) => {
      const ring = new THREE.Mesh(disposer.track(new THREE.TorusGeometry(r, 0.008, 8, 64)), mat);
      ring.rotation.set(i === 0 ? Math.PI / 2 : 0, 0, i === 2 ? Math.PI / 2 : 0);
      const holder = new THREE.Group();
      holder.add(ring);
      this.gyro.add(holder);
      this.gyroRings.push(holder);
    });
    this.group.add(this.gyro);
  }

  /** Para onde o holograma olha: o painel escolhido; senão o painel com tarefa real em curso; senão o rotor. */
  focusPoint(target) {
    let key = this.selected;
    if (!key) {
      let best = 0.05;
      for (const k of PANEL_KEYS) {
        const p = this.panels[k];
        const level = Math.max(p.level, p.flash * 0.8, p.fault);
        if (level > best) { best = level; key = k; }
      }
    }
    if (key) {
      const a = panelAngle(Math.max(0, PANEL_KEYS.indexOf(key)));
      target.set(Math.sin(a) * R_MID, Y_MID + 0.05, Math.cos(a) * R_MID);
    } else {
      target.set(0, ROTOR_Y0 + 0.6, 0);
    }
    return this.group.localToWorld(target);
  }

  get busy() {
    return this.engine.mode && this.engine.mode !== 'repouso' || this.st.fault > 0.02 || this.st.beam > 0.02 ||
           Object.values(this.panels).some((p) => p.level > 0.02 || p.flash > 0.02 || p.fault > 0.02);
  }

  update(dt, time, facing) {
    const st = this.st, t = this.target;
    const k = 1 - Math.exp(-dt * 2.2);
    st.speed += (t.speed - st.speed) * k; st.amplitude += (t.amplitude - st.amplitude) * k;
    st.brightness += (t.brightness - st.brightness) * k; st.spin += (t.spin - st.spin) * k;
    st.color.lerp(t.color, k); st.beam += (t.beam - st.beam) * k; st.fault += (t.fault - st.fault) * k;
    const uk = this.ultron || 0;                             // Protocolo ULTRON: sala em alerta (só cor)
    if (uk > 0) st.color.lerp(ULTRON_RED, uk);
    this.roundelMat.emissive.copy(this._roundelBase).lerp(ULTRON_RED, uk * 0.8);
    const avail = st.available ? 1 : 0.25;
    this.phase = (this.phase + dt * st.speed * Math.PI * 2) % (Math.PI * 2);
    this.spinA = (this.spinA + dt * st.spin * Math.PI * 2) % (Math.PI * 2);
    const offset = 0.5 + 0.5 * Math.sin(this.phase) * st.amplitude;             // curso do rotor (0..1)
    // rotor: anéis sobem/descem em sentidos opostos e giram
    this.ringLow.g.position.y = this.ringLow.y + offset * 0.55;
    this.ringHigh.g.position.y = this.ringHigh.y - offset * 0.55;
    this.ringLow.g.rotation.y = this.spinA; this.ringHigh.g.rotation.y = -this.spinA * 0.8;
    this.ringLow.parts.forEach((r, i) => { r.rotation.z = this.spinA * (i % 2 ? -1.4 : 1.1); });
    this.ringHigh.parts.forEach((r, i) => { r.rotation.z = -this.spinA * (i % 2 ? -1.2 : 0.9); });
    this.tubes.rotation.y = this.spinA * 0.3;
    if (this.gyroRings) {                                  // giroscópio: cada anel num eixo, na velocidade real
      this.gyroRings[0].rotation.y = this.spinA * 1.3;
      this.gyroRings[1].rotation.x = this.spinA * 0.9 + 0.4;
      this.gyroRings[2].rotation.z = -this.spinA * 1.1;
    }
    this.strands.rotation.y = -this.spinA * 0.6;
    this.strandMat.uniforms.uTime.value = time;
    this.strandMat.uniforms.uFlow.value = 0.08 + st.speed * 1.4;
    this.strandMat.uniforms.uBright.value = (0.25 + 0.75 * st.brightness) * avail * (st.fault > 0.5 ? 0.3 : 1);
    const b = st.brightness * avail;
    this.coreMat.color.copy(st.color); this.coreMat.opacity = 0.25 + 0.45 * b;
    this.coreGlow.material.color.copy(st.color); this.coreGlow.material.opacity = 0.06 + 0.24 * b * (0.85 + 0.15 * Math.sin(this.phase));
    this.glassMat.uniforms.uColor.value.copy(st.color); this.glassMat.uniforms.uTime.value = time;
    this.glassMat.uniforms.uBright.value = b; this.glassMat.uniforms.uPulse.value = Math.max(0, st.speed - 0.15) * 1.6 * avail;
    this.tubeMat.uniforms.uColor.value.copy(st.color); this.tubeMat.uniforms.uTime.value = time;
    this.tubeMat.uniforms.uFlow.value = st.speed; this.tubeMat.uniforms.uBright.value = 0.3 + 0.7 * b;
    this.rotorLight.color.copy(st.color); this.rotorLight.intensity = (1.5 + 6.0 * b) * (0.9 + 0.1 * Math.sin(this.phase));
    this.wellMat.color.copy(st.color); this.wellMat.opacity = 0.08 + 0.22 * b;
    this.daisEdge.material.color.copy(st.color); this.daisEdge.material.opacity = 0.25 + 0.5 * b;
    this.roundelMat.emissiveIntensity = (0.14 + 0.16 * st.brightness) * (st.available ? 1 : 0.5);
    this.faultRing.material.opacity = st.fault * (0.45 + 0.25 * Math.sin(time * 3));
    this.linkMat.uniforms.uTime.value = time; this.linkMat.uniforms.uPower.value = st.beam * 0.9;
    this.link.visible = st.beam > 0.02;
    this.screenGroup.rotation.y += ((facing || 0) - this.screenGroup.rotation.y) * (1 - Math.exp(-dt * 2.5));
    // painéis: atividade real → botões, luzes, ponteiros, alavancas; seleção → contorno e placa acesa
    PANEL_KEYS.forEach((key, i) => {
      const p = this.panels[key], lay = this.layout[i];
      p.level += (p.tl - p.level) * (1 - Math.exp(-dt * (p.tl > p.level ? 3 : 0.8)));
      p.flash = Math.max(0, p.flash - dt * 0.9); p.fault = Math.max(0, p.fault - dt * 0.5);
      const lvl = p.level * avail;
      lay.lamps.forEach((idx, j) => {
        const chase = p.running ? Math.max(0, Math.sin(time * 6 - j * 0.8)) : 0;
        _c.copy(DIMC).lerp(AMBER, Math.min(1, 0.15 * avail + lvl * 0.5 + chase * lvl * 0.7 + p.flash * 0.9));
        if (p.fault > 0.02) _c.lerp(RED, p.fault);
        _c.multiplyScalar(1 + lvl * 1.6 + p.flash * 2);
        this.lamps.color(idx, _c);
      });
      lay.buttons.forEach((idx, j) => {
        const on = ((j * 7 + i * 3) % 5 === 0) ? 0.35 : 0;                      // padrão fixo; acende com a atividade
        _c.copy(DIMC).lerp(j % 3 ? AMBER : _tmp.set(0x7fd4ff), Math.min(1, on * avail + lvl * 0.8 + p.flash * 0.6));
        if (p.fault > 0.02) _c.lerp(RED, p.fault * 0.8);
        _c.multiplyScalar(1 + lvl);
        this.btnCap.color(idx, _c);
      });
      lay.dials.forEach((idx, j) => {
        const angle = -2.35 + 4.7 * Math.min(1, lvl * (j ? 0.8 : 1) + p.flash * 0.2);
        this.needle.set(idx, _l.compose(_v.set(j ? 0.36 : -0.36, 0.036, 0.2), _q.setFromEuler(_e.set(0, angle, 0)), _s));
      });
      lay.levers.forEach((idx, j) => {
        const on = p.running ? 1 : 0;
        const ang = 0.55 - 1.1 * Math.min(1, on * (j === 1 ? 1 : 0.85));
        const m = _l.compose(_v.set((j - 1) * 0.12, 0.03, 0.24), _q.setFromEuler(_e.set(ang, 0, 0)), _s);
        this.leverStick.set(idx, m); this.leverKnob.set(idx, m);
        this.leverKnob.color(idx, _c.copy(DIMC).lerp(p.fault > 0.02 ? RED : AMBER, 0.3 + 0.7 * on).multiplyScalar(1 + on));
      });
      const scr = this.panelScreens[i];
      const sel = this.selected === key ? 1 : (this.hover === key ? 0.45 : 0);
      scr.outline.material.opacity += (sel * 0.9 - scr.outline.material.opacity) * (1 - Math.exp(-dt * 6));
      if ((sel > 0.5) !== scr.lit) { scr.lit = sel > 0.5; scr.name.draw(scr.lit); }
    });
    for (const p of [this.lamps, this.btnCap, this.leverKnob]) p.mesh.instanceColor.needsUpdate = true;
    for (const p of [this.needle, this.leverStick, this.leverKnob]) p.mesh.instanceMatrix.needsUpdate = true;
  }
}
const _tmp = new THREE.Color(), _l = new THREE.Matrix4();
