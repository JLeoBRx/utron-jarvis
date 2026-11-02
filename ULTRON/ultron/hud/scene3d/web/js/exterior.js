// A cabine azul por fora: proporções de uma cabine policial de madeira (≈ 1,30 × 1,30 × 2,9 m), modelada aqui
// peça por peça — postes com frisos, portas com quadros e almofadas, janelas de seis vidros, letreiro iluminado
// nas quatro faces, telhado em três degraus, lâmpada no topo, maçaneta e placa. Sem modelos de terceiros.
//
// A lâmpada e as janelas respondem ao estado REAL do motor da TARDIS (repouso, processando, consulta do
// JARVIS, falha); as portas só abrem na transição JARVIS ⇄ TARDIS que o usuário pediu.
import * as THREE from 'three';
import { Batch, disposer, canvasTexture, glowMaterial, glowTexture, physical, textPlate } from './materials.js';

const W = 1.30, POST = 0.15, INNER = W - 2 * POST, DOOR_W = INNER / 2, DOOR_H = 2.0, BASE = 0.10;
const DOOR_Y0 = 0.12, POST_TOP = 2.45, FACE = W / 2 - 0.035;     // plano das portas, recuado dos postes
const STILE = 0.065, RAIL = 0.065, BOTTOM_RAIL = 0.10, OPEN = (DOOR_H - BOTTOM_RAIL - 4 * RAIL) / 4;

const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);

/** Uma porta (ou falsa porta) com o canto inferior esquerdo em (0, 0); frente para +z. */
function doorParts(batch, parent, { window = true, plaque = false, handle = false } = {}) {
  const T = 0.045;
  const put = (geo, key, pos) => batch.put(geo, key, pos, [0, 0, 0], [1, 1, 1], parent);
  // quadro: montantes e travessas
  put(box(STILE, DOOR_H, T), 'wood', [STILE / 2, DOOR_H / 2, 0]);
  put(box(STILE, DOOR_H, T), 'wood', [DOOR_W - STILE / 2, DOOR_H / 2, 0]);
  put(box(DOOR_W, BOTTOM_RAIL, T), 'wood', [DOOR_W / 2, BOTTOM_RAIL / 2, 0]);
  let y = BOTTOM_RAIL;
  for (let i = 0; i < 4; i++) {
    const cy = y + OPEN / 2, iw = DOOR_W - 2 * STILE;
    const top = i === 3;
    if (top && window) {
      // janela: vidro fosco iluminado por dentro + divisões (3 × 2 vidros)
      put(box(iw, OPEN, 0.01), 'glass', [DOOR_W / 2, cy, -0.012]);
      for (const fx of [1 / 3, 2 / 3]) put(box(0.018, OPEN, 0.03), 'wood', [STILE + iw * fx, cy, -0.004]);
      put(box(iw, 0.018, 0.03), 'wood', [DOOR_W / 2, cy, -0.004]);
    } else {
      // almofada: fundo recuado e painel em relevo
      put(box(iw, OPEN, 0.02), 'woodDark', [DOOR_W / 2, cy, -0.014]);
      put(box(iw - 0.07, OPEN - 0.07, 0.016), 'wood', [DOOR_W / 2, cy, -0.002]);
      if (plaque && i === 2) put(box(iw - 0.10, OPEN - 0.12, 0.006), 'plaque', [DOOR_W / 2, cy, 0.009]);
    }
    y += OPEN;
    put(box(DOOR_W, RAIL, T), 'wood', [DOOR_W / 2, y + RAIL / 2, 0]);
    y += RAIL;
  }
  if (handle) {
    put(new THREE.CylinderGeometry(0.012, 0.012, 0.11, 12), 'brass', [DOOR_W - 0.035, 1.05, 0.04]);
    put(new THREE.CylinderGeometry(0.008, 0.008, 0.03, 8).rotateX(Math.PI / 2), 'brass', [DOOR_W - 0.035, 1.08, 0.025]);
    put(new THREE.CylinderGeometry(0.008, 0.008, 0.03, 8).rotateX(Math.PI / 2), 'brass', [DOOR_W - 0.035, 1.02, 0.025]);
    put(new THREE.CylinderGeometry(0.014, 0.014, 0.008, 16).rotateX(Math.PI / 2), 'brass', [DOOR_W - 0.035, 0.96, 0.026]);
  }
}

export class PoliceBox {
  constructor() {
    const P = physical();
    this.group = new THREE.Group();
    this.group.name = 'cabine';
    this.signTex = canvasTexture(1024, 192, (g, w, h) => {
      g.fillStyle = '#000'; g.fillRect(0, 0, w, h);
      g.fillStyle = '#fff'; g.textBaseline = 'middle';
      g.font = '700 92px Arial Narrow, Arial, sans-serif'; g.textAlign = 'left'; g.fillText('POLICE', 40, h / 2 + 4);
      g.textAlign = 'right'; g.fillText('BOX', w - 40, h / 2 + 4);
      g.textAlign = 'center'; g.font = '700 52px Arial Narrow, Arial, sans-serif';
      g.fillText('PUBLIC', w / 2 + 6, h / 2 - 30); g.fillText('CALL', w / 2 + 6, h / 2 + 34);
    });
    const plaqueTex = canvasTexture(256, 320, (g, w, h) => {
      g.fillStyle = '#b9c0c6'; g.fillRect(0, 0, w, h);
      g.strokeStyle = '#1b2633'; g.lineWidth = 6; g.strokeRect(10, 10, w - 20, h - 20);
      g.fillStyle = '#1b2633'; g.textAlign = 'center';
      g.font = '700 34px Arial'; g.fillText('T.A.R.D.I.S.', w / 2, 72);
      g.font = '22px Arial';
      ['SALA DE CONTROLE', 'ENTRADA PELO', 'PAINEL DO JARVIS', '—', 'PEDIDOS AVALIADOS', 'COM FONTES'].forEach((t, i) => g.fillText(t, w / 2, 120 + i * 32));
    });
    const frost = canvasTexture(128, 128, (g, w, h) => {
      const r = g.createRadialGradient(w / 2, h / 2, 4, w / 2, h / 2, w * 0.7);
      r.addColorStop(0, '#ffffff'); r.addColorStop(1, '#b8c8d8'); g.fillStyle = r; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 900; i++) { g.fillStyle = `rgba(255,255,255,${Math.random() * 0.25})`; g.fillRect(Math.random() * w, Math.random() * h, 1, 1); }
    });
    this.glassMat = disposer.track(new THREE.MeshStandardMaterial({ color: 0x6f8296, map: frost, emissive: 0xfff1d6,
                                                                    emissiveMap: frost, emissiveIntensity: 0.32, roughness: 0.35 }));
    this.signMat = disposer.track(new THREE.MeshStandardMaterial({ color: 0x050608, map: this.signTex, emissive: 0xffffff,
                                                                   emissiveMap: this.signTex, emissiveIntensity: 0.75, roughness: 0.4 }));
    const plaqueMat = disposer.track(new THREE.MeshStandardMaterial({ map: plaqueTex, roughness: 0.75, emissive: 0x6f7a86,
                                                                      emissiveMap: plaqueTex, emissiveIntensity: 0.06 }));
    this.lampMat = disposer.track(new THREE.MeshStandardMaterial({ color: 0xeaf6ff, emissive: 0xdff2ff, emissiveIntensity: 0.6,
                                                                   roughness: 0.15, transparent: true, opacity: 0.92 }));
    const mats = { wood: P.wood, woodDark: P.woodDark, glass: this.glassMat, plaque: plaqueMat, brass: P.brass,
                   sign: this.signMat, lamp: this.lampMat, black: P.black };

    const body = new Batch();
    const M = (x, y, z, ry = 0) => new THREE.Matrix4().compose(new THREE.Vector3(x, y, z),
      new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), ry), new THREE.Vector3(1, 1, 1));
    // base (soco) e assoalho
    body.put(box(W + 0.12, BASE, W + 0.12), 'woodDark', [0, BASE / 2, 0]);
    body.put(box(W + 0.06, 0.03, W + 0.06), 'wood', [0, BASE + 0.015, 0]);
    // postes de canto com frisos
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
      const x = sx * (W / 2 - POST / 2), z = sz * (W / 2 - POST / 2);
      body.put(box(POST, POST_TOP - BASE, POST), 'wood', [x, (POST_TOP + BASE) / 2, z]);
      body.put(box(0.02, POST_TOP - BASE - 0.3, 0.012), 'woodDark', [x, (POST_TOP + BASE) / 2, z + sz * (POST / 2 + 0.002)]);
      body.put(box(0.012, POST_TOP - BASE - 0.3, 0.02), 'woodDark', [x + sx * (POST / 2 + 0.002), (POST_TOP + BASE) / 2, z]);
    }
    // quatro faces: letreiro iluminado; frente com portas que abrem, as outras com falsas portas
    for (let f = 0; f < 4; f++) {
      const ry = f * Math.PI / 2;
      const face = M(0, 0, 0, ry);
      // letreiro: caixa saliente com a face preta iluminada
      body.put(box(INNER + 0.06, 0.27, 0.11), 'wood', [0, 2.275, FACE + 0.02], [0, 0, 0], [1, 1, 1], face);
      body.put(new THREE.PlaneGeometry(INNER - 0.02, 0.2), 'sign', [0, 2.275, FACE + 0.0765], [0, 0, 0], [1, 1, 1], face);
      // faixa entre o letreiro e as portas
      body.put(box(INNER, 0.05, 0.04), 'wood', [0, DOOR_Y0 + DOOR_H + 0.02, FACE], [0, 0, 0], [1, 1, 1], face);
      if (f === 0) continue;
      for (const side of [0, 1]) {
        const at = new THREE.Matrix4().multiplyMatrices(face, M(-INNER / 2 + side * DOOR_W, DOOR_Y0, FACE));
        doorParts(body, at, { window: true });
      }
      body.put(box(0.035, DOOR_H, 0.05), 'wood', [0, DOOR_Y0 + DOOR_H / 2, FACE + 0.01], [0, 0, 0], [1, 1, 1], face);
    }
    // telhado em degraus e lâmpada
    body.put(box(W + 0.14, 0.07, W + 0.14), 'wood', [0, POST_TOP + 0.035, 0]);
    body.put(box(W + 0.02, 0.09, W + 0.02), 'woodDark', [0, POST_TOP + 0.115, 0]);
    const roof = new THREE.CylinderGeometry(0.17 * Math.SQRT2, (W / 2) * Math.SQRT2, 0.17, 4, 1).toNonIndexed();
    roof.computeVertexNormals();
    body.put(roof, 'wood', [0, POST_TOP + 0.245, 0], [0, Math.PI / 4, 0]);
    const lampY = POST_TOP + 0.33;
    body.put(new THREE.CylinderGeometry(0.13, 0.15, 0.04, 24), 'woodDark', [0, lampY + 0.02, 0]);
    for (let i = 0; i < 4; i++) {
      const a = i * Math.PI / 2 + Math.PI / 4;
      body.put(box(0.018, 0.2, 0.018), 'black', [Math.cos(a) * 0.088, lampY + 0.14, Math.sin(a) * 0.088]);
    }
    body.put(new THREE.CylinderGeometry(0.075, 0.075, 0.19, 24), 'lamp', [0, lampY + 0.135, 0]);
    body.put(new THREE.ConeGeometry(0.12, 0.08, 24), 'black', [0, lampY + 0.28, 0]);
    body.put(new THREE.SphereGeometry(0.022, 12, 8), 'brass', [0, lampY + 0.33, 0]);
    body.build(mats, this.group);

    // portas da frente: dobradiças nas bordas externas, abrem para dentro
    this.doors = [];
    for (const side of [0, 1]) {
      const pivot = new THREE.Group();
      pivot.position.set(side === 0 ? -INNER / 2 : INNER / 2, DOOR_Y0, FACE);
      const b = new Batch();
      const offset = new THREE.Matrix4().makeTranslation(side === 0 ? 0 : -DOOR_W, 0, 0);
      doorParts(b, offset, { window: true, plaque: side === 0, handle: side === 1 });
      if (side === 1) b.put(box(0.035, DOOR_H, 0.05), 'wood', [-DOOR_W + 0.0175, DOOR_H / 2, 0.012]);
      b.build(mats, pivot);
      this.group.add(pivot);
      this.doors.push(pivot);
    }
    // luz de dentro (vista com as portas abertas): "maior por dentro"
    this.spillMat = disposer.track(new THREE.MeshBasicMaterial({ map: canvasTexture(128, 256, (g, w, h) => {
      const r = g.createLinearGradient(0, h, 0, 0);
      r.addColorStop(0, '#ffd9a0'); r.addColorStop(0.5, '#bfe9ff'); r.addColorStop(1, '#ffffff');
      g.fillStyle = r; g.fillRect(0, 0, w, h);
    }), transparent: true, opacity: 0, depthWrite: false }));
    const spill = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(INNER - 0.02, DOOR_H)), this.spillMat);
    spill.position.set(0, DOOR_Y0 + DOOR_H / 2, FACE - 0.08);
    this.group.add(spill);
    // halo da lâmpada, luz real (pontual) e sombra de contato no chão
    this.halo = new THREE.Sprite(disposer.track(new THREE.SpriteMaterial({ map: glowTexture(), color: 0xcfeaff, transparent: true,
      opacity: 0.2, depthWrite: false, blending: THREE.AdditiveBlending })));
    this.halo.scale.set(0.45, 0.45, 1); this.halo.position.set(0, lampY + 0.135, 0);
    this.lampLight = new THREE.PointLight(0xdff2ff, 0.6, 5, 2);
    this.lampLight.position.set(0, lampY + 0.135, 0);
    this.fill = new THREE.PointLight(0x9fc8ff, 2.2, 6, 2);
    this.fill.position.set(0.9, 1.6, 2.2);
    const shadow = new THREE.Mesh(disposer.track(new THREE.PlaneGeometry(2.6, 2.6)), disposer.track(new THREE.MeshBasicMaterial({
      map: canvasTexture(128, 128, (g, w, h) => {
        const r = g.createRadialGradient(w / 2, h / 2, w * 0.2, w / 2, h / 2, w / 2);
        r.addColorStop(0, 'rgba(0,0,0,0.75)'); r.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = r; g.fillRect(0, 0, w, h);
      }, { srgb: false }), transparent: true, depthWrite: false })));
    shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.003;
    this.group.add(this.halo, this.lampLight, this.fill, shadow);
    this.open = 0; this.openTarget = 0;
    this.mode = 'repouso';
    this.lampColor = new THREE.Color(0xdff2ff);
  }

  /** Abertura das portas (0..1), animada até o alvo. */
  setOpen(target) { this.openTarget = Math.max(0, Math.min(1, target)); }

  /** Estado real do motor da TARDIS: a lâmpada acompanha. */
  setEngine(mode, fault) { this.mode = fault ? 'falha' : (mode || 'repouso'); }

  get doorWorld() { return this.group.localToWorld(new THREE.Vector3(0, 1.1, FACE + 0.02)); }

  update(dt, time) {
    this.open += (this.openTarget - this.open) * (1 - Math.exp(-dt * 3.0));
    const a = this.open * 1.45;
    this.doors[0].rotation.y = a;
    this.doors[1].rotation.y = -a * 0.97;
    this.spillMat.opacity = Math.min(1, this.open * 1.6);
    const active = this.mode === 'processando' || this.mode === 'jarvis' || this.mode === 'operacao' || (this.ultron || 0) > 0.5;
    const pulse = active ? 0.5 + 0.5 * Math.sin(time * (this.mode === 'jarvis' ? 4.2 : 2.6)) : 0;
    const target = (this.ultron || 0) > 0.5 ? 0xff1f3d : this.mode === 'falha' ? 0xff6b5a : (this.mode === 'jarvis' ? 0x9fe8ff : 0xfff0d8);
    this.lampColor.lerp(_c.set(target), 1 - Math.exp(-dt * 3));
    this.lampMat.emissive.copy(this.lampColor);
    this.lampMat.emissiveIntensity = 0.45 + (active ? 1.4 * pulse : 0) + (this.mode === 'falha' ? 0.5 : 0);
    this.lampLight.color.copy(this.lampColor);
    this.lampLight.intensity = 0.4 + (active ? 3.0 * pulse : 0);
    this.halo.material.color.copy(this.lampColor);
    this.halo.material.opacity = 0.1 + (active ? 0.35 * pulse : 0);
    this.glassMat.emissiveIntensity = 0.3 + 0.5 * this.open + (active ? 0.08 : 0);
  }
}
const _c = new THREE.Color();
