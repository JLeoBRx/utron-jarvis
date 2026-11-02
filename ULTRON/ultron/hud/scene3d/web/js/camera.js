// Câmera: vistas nomeadas, voo suave entre elas (com pontos de passagem), órbita e zoom do usuário dentro de
// limites, e enquadramento automático do corpo inteiro (a distância se ajusta à proporção da janela).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export class CameraRig {
  constructor(camera, dom) {
    this.camera = camera;
    this.controls = new OrbitControls(camera, dom);
    Object.assign(this.controls, { enableDamping: true, dampingFactor: 0.08, enablePan: false, rotateSpeed: 0.55,
                                   zoomSpeed: 0.7 });
    this.controls.addEventListener('start', () => { this.userMoved = true; this.interacting = true; this.flight = null; });
    this.controls.addEventListener('end', () => { this.interacting = false; });
    this.interacting = false;
    this.views = {};
    this.view = '';
    this.flight = null;
    this.userMoved = false;
    this.drift = 0;
  }

  /** Registra uma vista: fn(aspect) → { pos, target, min, max, minPolar, maxPolar, minAz, maxAz }. */
  define(name, fn) { this.views[name] = fn; }

  spec(name) { return this.views[name](this.camera.aspect); }

  /** Vai para a vista; com waypoints, passa por eles. instant = sem animação (efeitos desligados). */
  go(name, { duration = 1.4, instant = false, waypoints = [], then = null } = {}) {
    const s = this.spec(name);
    this.view = name;
    this.userMoved = false;
    this._limits(s);
    if (instant) {
      this.flight = null;
      this.camera.position.copy(s.pos);
      this.controls.target.copy(s.target);
      this.camera.lookAt(s.target);
      this.controls.update();
      if (then) then();
      return;
    }
    const path = [{ pos: this.camera.position.clone(), target: this.controls.target.clone() }, ...waypoints, { pos: s.pos, target: s.target }];
    this.flight = { path, t: 0, duration: Math.max(0.2, duration), then };
    this.controls.enabled = false;
  }

  _limits(s) {
    const c = this.controls;
    c.minDistance = s.min ?? 0.5; c.maxDistance = s.max ?? 30;
    c.minPolarAngle = s.minPolar ?? 0.25; c.maxPolarAngle = s.maxPolar ?? 1.62;
    c.minAzimuthAngle = s.minAz ?? -Infinity; c.maxAzimuthAngle = s.maxAz ?? Infinity;
    c.enableRotate = s.rotate !== false; c.enableZoom = s.zoom !== false;
  }

  /** Reenquadra a vista atual (ex.: janela mudou de tamanho) se o usuário não mexeu na câmera. */
  reframe() {
    if (!this.view || this.flight || this.userMoved) return;
    const s = this.spec(this.view);
    this.camera.position.copy(s.pos);
    this.controls.target.copy(s.target);
    this.controls.update();
  }

  get moving() { return !!this.flight; }

  update(dt, time, { drift = true } = {}) {
    const f = this.flight;
    if (f) {
      f.t = Math.min(1, f.t + dt / f.duration);
      const n = f.path.length - 1, x = ease(f.t) * n, i = Math.min(n - 1, Math.floor(x)), u = x - i;
      // interpolação Catmull-Rom entre os pontos de passagem (curva suave, sem quinas)
      const P = (k) => f.path[Math.max(0, Math.min(n, k))];
      const cr = (a, b, c, d, t, key) => _v.set(0, 0, 0)
        .addScaledVector(b[key], 2).addScaledVector(c[key], t).addScaledVector(a[key], -t)
        .addScaledVector(a[key], 2 * t * t).addScaledVector(b[key], -5 * t * t).addScaledVector(c[key], 4 * t * t).addScaledVector(d[key], -t * t)
        .addScaledVector(a[key], -t * t * t).addScaledVector(b[key], 3 * t * t * t).addScaledVector(c[key], -3 * t * t * t).addScaledVector(d[key], t * t * t)
        .multiplyScalar(0.5);
      this.camera.position.copy(cr(P(i - 1), P(i), P(i + 1), P(i + 2), u, 'pos'));
      this.controls.target.copy(cr(P(i - 1), P(i), P(i + 1), P(i + 2), u, 'target'));
      this.camera.lookAt(this.controls.target);
      if (f.t >= 1) {
        this.flight = null;
        this.controls.enabled = true;
        this.controls.update();
        if (f.then) f.then();
      }
      return;
    }
    this.controls.update();
    // respiração da câmera: quase imperceptível, só com efeitos e sem o usuário segurando a vista
    if (drift && !this.userMoved) {
      this.drift = time;
      this.camera.position.y += Math.sin(time * 0.21) * 0.0008;
      this.camera.position.x += Math.sin(time * 0.13) * 0.0006;
    }
  }
}
const _v = new THREE.Vector3();

/** Distância para caber uma altura (m) e uma largura (m) no quadro, dado o campo de visão vertical. */
export function fitDistance(camera, height, width, aspect = camera.aspect) {
  const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
  return Math.max((height / 2) / tanV, (width / 2) / (tanV * aspect));
}
