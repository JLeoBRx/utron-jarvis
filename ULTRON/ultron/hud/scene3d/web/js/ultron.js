// Protocolo ULTRON na cena: transição cinematográfica de identidade (a parte visual; voz, tom e o perfil
// ULTRON_OPERATOR ficam no núcleo, em Python).
//
// Entra em ~2,5 s (interferência, cores migrando do vermelho SAFRA para violeta e cromo, postura do holograma
// mais dura, olhos violeta, ORBE violeta, TARDIS e convés em alerta) e sai em ~1,2 s. O violeta é exclusivo do
// ULTRON — o vermelho pertence ao SAFRA. As mensagens são de um personagem e vêm junto do rótulo honesto enviado
// pelo Python (identidade apenas, ou operador ativo); o botão RESTAURAR SAFRA (e Esc) pede ao Python o fim do
// evento. Nada aqui fala com o sistema operacional.
import * as THREE from 'three';

const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const ease = (t) => t * t * (3 - 2 * t);

export class UltronTheme {
  constructor({ avatar, orb, deck, room, box, hud, onRestore }) {
    Object.assign(this, { avatar, orb, deck, room, box, hud, onRestore });
    this.k = 0;
    this.target = 0;
    this.glitch = 0;
    this.messages = [];
    this.index = 0;
    this.nextMessage = 0;
    this.label = '';
  }

  get active() { return this.target > 0; }

  set(on, { messages = [], label = '' } = {}) {
    this.target = on ? 1 : 0;
    this.glitch = on ? 1.6 : 0.7;                      // rajada de interferência na troca de identidade
    if (on) {
      this.messages = messages.length ? messages : ['PROTOCOLO ULTRON INICIADO'];
      this.label = label;
      this.index = 0;
      this.nextMessage = 0;
      this.hud.ultron(true, { label, message: this.messages[0] });
    } else {
      this.hud.ultron(false);
    }
  }

  update(dt, time) {
    const rate = this.target ? 0.4 : 0.85;
    this.k = clamp(this.k + clamp(this.target - this.k, -dt * rate, dt * rate), 0, 1);
    this.glitch = Math.max(0, this.glitch - dt);
    const k = ease(this.k);
    for (const part of [this.avatar, this.orb, this.deck, this.room, this.box]) part.ultron = k;
    // interferência: quadros curtos e irregulares durante as trocas (e raros enquanto ativo)
    const burst = this.glitch > 0 ? (Math.sin(time * 61) * Math.sin(time * 23) > 0.25) :
                  (this.target && Math.sin(time * 3.1) * Math.sin(time * 7.7) > 0.985);
    this.hud.glitch(!!burst);
    if (this.target && this.messages.length && time > this.nextMessage) {
      this.hud.ultron(true, { label: this.label, message: this.messages[this.index % this.messages.length] });
      this.index += 1;
      this.nextMessage = time + 2.8;
    }
  }
}

export const ULTRON_COLOR = new THREE.Color(0x8b5cf6);       // violeta elétrico (tokens: ultron)
export const ULTRON_GLOW = new THREE.Color(0xb794ff);        // violeta claro (tokens: ultron_glow)
export const ULTRON_DEEP = new THREE.Color(0x1c0f33);        // (tokens: ultron_deep)
