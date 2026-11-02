// Camada de interface sobre a cena: estado (rótulo e motivo REAIS), legenda sincronizada com a fala, cartões
// de dados presos a pontos da cena, avisos (contexto WebGL, sem conexão) e botões de vista.
import * as THREE from 'three';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export class Hud {
  constructor({ onView }) {
    this.el = { state: $('state'), label: $('state-label'), detail: $('state-detail'), cards: $('cards'), caption: $('caption'),
                views: $('views'), notice: $('notice'), perf: $('perf'), veil: $('veil') };
    this.cards = new Map();
    this.onView = onView;
    this.mode = 'jarvis';
    this.el.views.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (b) this.onView(b.dataset.view);
    });
    this.setButtons('jarvis', 'frente');
  }

  /** Botões de vista conforme o modo (JARVIS: frente, núcleo, cabine, entrar; TARDIS: console, painel, sair). */
  setButtons(mode, active) {
    this.mode = mode;
    const sets = {
      jarvis: [['frente', 'FRENTE', 'Enquadramento frontal do corpo inteiro (duplo clique na cena também volta)'],
               ['nucleo', 'NÚCLEO', 'O ORBE — núcleo de inteligência — ampliado: gire e aproxime com o mouse'],
               ['exterior', 'CABINE', 'A cabine da TARDIS por fora'],
               ['entrar', 'ENTRAR NA TARDIS', 'Abre a sala de controle (página TARDIS)']],
      tardis: [['tardis', 'CONSOLE', 'Visão geral da sala de controle'],
               ['painel', 'PAINEL', 'Diante do painel escolhido à direita'],
               ['sair', 'VOLTAR AO JARVIS', 'Sai pela porta e volta ao convés do JARVIS']],
    };
    this.el.views.innerHTML = sets[mode].map(([k, t, tip]) => `<button data-view="${k}" title="${esc(tip)}">${t}</button>`).join('');
    this.setActive(active);
  }

  setActive(view) {
    for (const b of this.el.views.querySelectorAll('button')) b.classList.toggle('on', b.dataset.view === view);
  }

  setState({ label, detail, rgb, alert, error, tardis }) {
    this.el.label.textContent = label || '';
    this.el.detail.textContent = detail || '';
    const c = rgb ? `rgb(${rgb.join(',')})` : '';
    const dot = this.el.state.querySelector('.dot');
    dot.style.background = c; dot.style.boxShadow = c ? `0 0 10px ${c}` : '';
    this.el.label.style.color = c ? `rgb(${rgb.map((v) => Math.round(v * 0.55 + 255 * 0.45)).join(',')})` : '';
    document.body.classList.toggle('alert', !!alert);
    document.body.classList.toggle('error', !!error);
    document.body.classList.toggle('tardis', !!tardis);
  }

  /** Legenda: as palavras já ditas acesas (progresso real da reprodução). */
  setCaption(caption) {
    const text = (caption && caption.text) || '';
    if (!text) { this.el.caption.classList.add('hidden'); this._cap = ''; return; }
    const words = text.split(/\s+/);
    const spoken = Math.round((caption.progress || 0) * words.length);
    const key = text + '|' + spoken + '|' + (caption.active ? 1 : 0);
    if (key === this._cap) return;
    this._cap = key;
    this.el.caption.querySelector('.said').textContent = words.slice(0, spoken).join(' ') + (spoken ? ' ' : '');
    this.el.caption.querySelector('.rest').textContent = words.slice(spoken).join(' ');
    this.el.caption.classList.remove('hidden');
    this.el.caption.style.opacity = caption.active ? '1' : '0.75';
  }

  /** Cartões presos a pontos 3D: [{ id, k, v, anchor: Vector3, dx, dy }]. Sem valor, sem cartão. */
  setCards(list) {
    const seen = new Set();
    for (const c of list) {
      if (!c.v) continue;
      seen.add(c.id);
      let item = this.cards.get(c.id);
      if (!item) {
        const el = document.createElement('div');
        el.className = 'card glass hidden';
        el.innerHTML = '<div class="k"></div><div class="v"></div>';
        this.el.cards.appendChild(el);
        item = { el };
        this.cards.set(c.id, item);
        requestAnimationFrame(() => el.classList.remove('hidden'));
      }
      Object.assign(item, c);
      item.el.querySelector('.k').textContent = c.k;
      const v = item.el.querySelector('.v');
      if (v.textContent !== c.v) v.textContent = c.v;
      item.el.title = c.v;
    }
    for (const [id, item] of this.cards) if (!seen.has(id)) { item.el.remove(); this.cards.delete(id); }
  }

  placeCards(camera, w, h) {
    for (const item of this.cards.values()) {
      _p.copy(item.anchor).project(camera);
      const visible = _p.z < 1 && Math.abs(_p.x) < 1.2 && Math.abs(_p.y) < 1.2;
      item.el.style.display = visible ? '' : 'none';
      if (!visible) continue;
      const x = (_p.x * 0.5 + 0.5) * w + (item.dx || 0), y = (-_p.y * 0.5 + 0.5) * h + (item.dy || 0);
      item.el.style.transform = `translate(${Math.round(Math.min(w - 260, Math.max(8, x)))}px, ${Math.round(Math.min(h - 60, Math.max(70, y)))}px)`;
    }
  }

  notice(text, kind = 'warn') {
    this.el.notice.textContent = text || '';
    this.el.notice.classList.toggle('hidden', !text);
    this.el.notice.dataset.kind = kind;
  }

  perf(text) { this.el.perf.textContent = text || ''; this.el.perf.classList.toggle('hidden', !text); }

  veil(on) { this.el.veil.classList.toggle('on', !!on); }
}
const _p = new THREE.Vector3();
