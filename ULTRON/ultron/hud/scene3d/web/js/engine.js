// Motor da cena: renderizador WebGL2, pós-processamento (bloom), ritmo de quadros, qualidade adaptativa,
// perda/recuperação do contexto WebGL e pausa quando a vista não está à mostra.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { disposer } from './materials.js';

// Perfis do SAFRA (os mesmos nomes de CONFIGURAÇÕES > APARÊNCIA). "particles" multiplica as contagens.
export const PROFILES = {
  economy:   { pixel: 0.75, bloom: 0,    antialias: false, particles: 0.35, fps: 30, idleFps: 20 },
  balanced:  { pixel: 1.0,  bloom: 0.75, antialias: true,  particles: 0.7,  fps: 45, idleFps: 30 },
  high:      { pixel: 1.25, bloom: 0.9,  antialias: true,  particles: 1.0,  fps: 60, idleFps: 40 },
  cinematic: { pixel: 2.0,  bloom: 1.05, antialias: true,  particles: 1.3,  fps: 60, idleFps: 50 },
};

export class Engine {
  constructor(container, { profile = 'balanced', onReport = () => {} } = {}) {
    this.container = container;
    this.onReport = onReport;
    this.profileName = PROFILES[profile] ? profile : 'balanced';
    this.profile = { ...PROFILES[this.profileName] };
    this.level = 0;                      // degraus de redução adaptativa (0 = perfil completo)
    this.updaters = [];
    this.visible = true;
    this.lost = false;
    this.effects = true;
    this.bloomScale = 1;                 // ORBE minimizado: brilho contido (sobrevive à reconstrução)
    this.active = false;                 // há movimento real (fala, escuta, operação): usa o teto de fps
    this.frames = [];
    this.lastFrame = 0;
    this.clock = new THREE.Clock();
    this.time = 0;
    this._raf = 0;

    // Sem MSAA no contexto: a suavização fica no alvo do compositor (que é por onde tudo é desenhado).
    const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: 'high-performance',
                                               alpha: false, stencil: false });
    if (!renderer.capabilities.isWebGL2) throw new Error('WebGL 2 indisponível neste computador');
    renderer.setClearColor(0x050507, 1);
    renderer.info.autoReset = false;               // conta todas as passagens do quadro (estatísticas reais)
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);
    this.renderer = renderer;
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x050507, 0.045);
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.05, 220);
    const pmrem = new THREE.PMREMGenerator(renderer);
    this.environment = disposer.track(pmrem.fromScene(new RoomEnvironment(), 0.04).texture);
    pmrem.dispose();
    this.scene.environment = this.environment;
    this.scene.environmentIntensity = 0.35;
    this._buildComposer();

    const canvas = renderer.domElement;
    canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();                // pede ao navegador que devolva o contexto
      this.lost = true;
      this.lostAt = performance.now();
      this.stop();
      this.onReport({ type: 'context', state: 'perdido' });
    });
    canvas.addEventListener('webglcontextrestored', () => {
      this.lost = false;                 // o three reenvia geometrias e texturas no próximo quadro
      this._buildComposer();
      this.resize();
      this.onReport({ type: 'context', state: 'restaurado' });
      this.start();
    });
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(container);
    document.addEventListener('visibilitychange', () => (document.hidden ? this.stop() : this.start()));
    this.resize();
  }

  get info() {
    const gl = this.renderer.getContext();
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    return { webgl2: true, renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
             maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE), three: THREE.REVISION };
  }

  _buildComposer() {
    // Sempre pelo compositor: os materiais próprios (holograma) saem lineares e o OutputPass aplica o mesmo
    // mapeamento de tons e sRGB para tudo — com ou sem brilho. O alvo tem MSAA quando o perfil pede.
    this._disposeComposer();
    const size = this.renderer.getSize(new THREE.Vector2());
    const pr = this.renderer.getPixelRatio();
    const target = new THREE.WebGLRenderTarget(Math.max(1, size.x * pr), Math.max(1, size.y * pr),
      { type: THREE.HalfFloatType, samples: this.profile.antialias ? 4 : 0 });
    const composer = new EffectComposer(this.renderer, target);
    composer.addPass(new RenderPass(this.scene, this.camera));
    const strength = (this.effects ? this.profile.bloom : 0) * this.bloomScale;
    this.bloom = null;
    if (strength > 0.02) {
      this.bloom = new UnrealBloomPass(new THREE.Vector2(Math.max(1, size.x) / 2, Math.max(1, size.y) / 2), strength, 0.5, 0.42);
      composer.addPass(this.bloom);
    }
    composer.addPass(new OutputPass());
    this.composer = composer;
  }

  setBloomScale(k) {
    if (k === this.bloomScale) return;
    this.bloomScale = k;
    this._buildComposer();
    this.resize();
  }

  _disposeComposer() {
    if (!this.composer) return;
    for (const pass of this.composer.passes) if (pass.dispose) pass.dispose();
    this.composer.dispose();
    this.composer = null;
  }

  setProfile(name, effects = true) {
    const changed = name !== this.profileName || effects !== this.effects;
    if (!changed || !PROFILES[name]) return;
    this.profileName = name;
    this.effects = !!effects;
    this.level = 0;
    this.profile = { ...PROFILES[name] };
    this._buildComposer();
    this.resize();
    this._holdUntil = performance.now() + 4000;
    this.onReport({ type: 'quality', profile: name, level: 0 });
  }

  /** Reduz um degrau: resolução, depois bloom, depois partículas. Volta a subir quando sobra folga. */
  _adapt(down) {
    const base = PROFILES[this.profileName];
    const next = Math.max(0, Math.min(4, this.level + (down ? 1 : -1)));
    if (next === this.level) return;
    this.level = next;
    this.profile.pixel = Math.max(0.5, base.pixel * (1 - 0.18 * Math.min(next, 2)));
    this.profile.bloom = next >= 3 ? 0 : base.bloom * (next >= 2 ? 0.7 : 1);
    this.profile.particles = base.particles * (next >= 4 ? 0.5 : 1);
    this._buildComposer();
    this.resize();
    for (const u of this.updaters) if (u.setParticleScale) u.setParticleScale(this.profile.particles);
    this._holdUntil = performance.now() + 3000;      // o compositor novo recompila: espera antes de medir de novo
    this.onReport({ type: 'quality', profile: this.profileName, level: next });
  }

  resize() {
    const w = Math.max(1, this.container.clientWidth), h = Math.max(1, this.container.clientHeight);
    const ratio = Math.min(window.devicePixelRatio || 1, 2) * this.profile.pixel;
    this.renderer.setPixelRatio(Math.max(0.5, Math.min(ratio, 2)));
    this.renderer.setSize(w, h, false);
    if (this.composer) { this.composer.setPixelRatio(this.renderer.getPixelRatio()); this.composer.setSize(w, h); }
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    for (const u of this.updaters) if (u.onResize) u.onResize(w, h);
  }

  add(updater) { this.updaters.push(updater); return updater; }

  setVisible(v) { this.visible = !!v; v ? this.start() : this.stop(); }

  start() {
    if (this._raf || this.lost || !this.visible || document.hidden) return;
    this.clock.getDelta();
    this._lastCheck = 0; this.frames.length = 0; this._slow = this._fast = 0;   // pausa não conta como lentidão
    this._holdUntil = performance.now() + 5000;      // aquecimento: compilação de shaders não é lentidão
    const loop = (now) => {
      this._raf = requestAnimationFrame(loop);
      const fps = this.active ? this.profile.fps : this.profile.idleFps;
      if (now - this.lastFrame < 1000 / fps - 2) return;          // teto de quadros por segundo
      const dt = Math.min(0.1, this.clock.getDelta());
      this.lastFrame = now;
      this.frame(dt, now);
    };
    this._raf = requestAnimationFrame(loop);
  }

  stop() { if (this._raf) cancelAnimationFrame(this._raf); this._raf = 0; }

  frame(dt, now = performance.now()) {
    this.time += dt;
    for (const u of this.updaters) u.update(dt, this.time);
    const t0 = performance.now();
    this.renderer.info.reset();
    this.composer.render(dt);
    const cost = performance.now() - t0;
    this.frames.push({ at: now, dt, cost });
    if (this.frames.length > 240) this.frames.shift();
    this._checkBudget(now);
  }

  _checkBudget(now) {
    if (this._holdUntil && now < this._holdUntil) { this._lastCheck = now; return; }   // aquecimento / após ajuste
    if (!this._lastCheck) this._lastCheck = now;
    if (now - this._lastCheck < 2000) return;
    const span = (now - this._lastCheck) / 1000;
    this._lastCheck = now;
    // quadros DESENHADOS na janela (não o intervalo de cada quadro, que tem teto): numa máquina muito lenta
    // há poucos quadros — e é justamente aí que a qualidade precisa descer
    const recent = this.frames.filter((f) => now - f.at < span * 1000 + 1);
    const fps = recent.length / span;
    const target = this.active ? this.profile.fps : this.profile.idleFps;
    this.stats = { fps: Math.round(fps * 10) / 10, target, level: this.level, profile: this.profileName,
                   drawCalls: this.renderer.info.render.calls, triangles: this.renderer.info.render.triangles };
    if (fps < target * 0.72) { this._slow = (this._slow || 0) + 1; this._fast = 0; }
    else if (fps > target * 0.92) { this._fast = (this._fast || 0) + 1; this._slow = 0; }
    if (this._slow >= 2) { this._slow = 0; this._adapt(true); }
    else if (this._fast >= 6 && this.level > 0) { this._fast = 0; this._adapt(false); }
    this.onReport({ type: 'stats', ...this.stats });
  }

  dispose() {
    this.stop();
    this._ro.disconnect();
    this._disposeComposer();
    disposer.dispose();
    this.renderer.dispose();
  }
}
