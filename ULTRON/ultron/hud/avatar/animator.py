"""Relógio do avatar: leva o rosto suavemente até a expressão do estado atual.

* Movimento sutil da cabeça (respiração), atenção ao escutar, olhar que varre ao pensar, olhar para o
  lado ao consultar a TARDIS, expressão firme ao executar, sobrancelhas erguidas ao pedir confirmação,
  susto no alerta, "falha" de projeção no erro e viseira no modo privacidade.
* Piscadas naturais (intervalos irregulares, às vezes duplas), suspensas com a viseira e no boot.
* Boca: segue a trilha labial do áudio REAL (suavização curta, sem atraso perceptível); sem fala, volta
  ao repouso em poucos quadros — interromper a fala fecha a boca.
* Inicialização: o rosto se monta conforme o PROGRESSO REAL do boot (componentes iniciados); os olhos
  só abrem quando a montagem termina.
* Conexão/desconexão de componentes reais: pulso de luz / escurecimento breve.
"""
from __future__ import annotations

import math
import random

from .rig import Rig, approach, approach_rgb, mix
from .states import AMBER, Resolved

CLOSED_MOUTH = {"open": 0.0, "wide": 0.0, "round": 0.0, "press": 0.15, "teeth": 0.0, "energy": 0.0}


class Animator:
    def __init__(self, seed: int = 7):
        self.rig = Rig()
        self.t = 0.0
        self.key = ""
        self.since = 0.0
        self._rng = random.Random(seed)
        self._next_blink = 1.5
        self._blink_t = -1.0
        self._double = False
        self._nod = 0.0
        self._last_energy = 0.0

    # ------------------------------------------------------------ eventos reais
    def component_started(self) -> None:
        self.rig.pulse = 1.0

    def component_lost(self) -> None:
        self.rig.dim = 1.0

    # ------------------------------------------------------------ quadro
    def step(self, dt: float, resolved: Resolved, *, mouth: dict | None = None, mic_level: float = 0.0,
             out_level: float = 0.0, boot_progress: float = 1.0) -> Rig:
        dt = max(0.0, min(0.1, dt))
        self.t += dt
        t = self.t
        rig = self.rig
        style = resolved.style
        key = resolved.key
        if key != self.key:
            self.key, self.since = key, t
        age = t - self.since
        # --- cor e luz
        target_rgb = tuple(float(c) for c in style.rgb)
        if resolved.alert_tint:
            target_rgb = mix(target_rgb, AMBER, 0.35)
        rig.rgb = approach_rgb(rig.rgb, target_rgb, 5.0, dt)
        rig.iris = approach_rgb(rig.iris, tuple(float(c) for c in style.iris), 5.0, dt)
        rig.alert = approach(rig.alert, 1.0 if key == "alerta" or resolved.alert_tint else 0.0, 6.0, dt)
        rig.glow = approach(rig.glow, style.glow, 4.0, dt)
        rig.visor = approach(rig.visor, 1.0 if key == "privacidade" else 0.0, 5.0, dt)
        rig.glitch = approach(rig.glitch, 1.0 if key == "erro" else 0.0, 8.0, dt)
        rig.scan_speed = approach(rig.scan_speed, style.scan, 3.0, dt)
        rig.ring_speed = approach(rig.ring_speed, style.rings, 3.0, dt)
        rig.particles = approach(rig.particles, style.particles, 2.0, dt)
        rig.pulse = approach(rig.pulse, 0.0, 2.5, dt)
        rig.dim = approach(rig.dim, 0.0, 2.0, dt)
        rig.mic_level = approach(rig.mic_level, mic_level if key in ("escutando", "reconhecendo") else 0.0, 18.0, dt)
        rig.out_level = approach(rig.out_level, out_level if key == "falando" else 0.0, 18.0, dt)
        # --- montagem do boot (progresso REAL)
        target_assemble = max(0.0, min(1.0, boot_progress)) if key == "inicializando" else 1.0
        rig.assemble = approach(rig.assemble, target_assemble, 3.0, dt)
        # --- cabeça
        amp = style.head
        yaw = amp * (0.20 * math.sin(t * 0.35) + 0.05 * math.sin(t * 0.83))
        pitch = -0.12 + amp * 0.03 * math.sin(t * 0.27)
        roll = amp * 0.02 * math.sin(t * 0.5)
        gaze_x = gaze_y = 0.0
        brow = style.brow
        eye_open = style.eye_open
        if key == "escutando":
            roll += 0.06
            pitch -= 0.04
        elif key == "reconhecendo":
            gaze_x = 0.08 * math.sin(t * 7.0) * math.sin(t * 2.3)
            gaze_y = 0.05 * math.sin(t * 5.1)
        elif key == "pensando":
            gaze_x = 0.6 * math.sin(t * 0.9)
            gaze_y = 0.35 + 0.1 * math.sin(t * 1.7)
        elif key == "tardis":
            gaze_x, yaw = 0.75, yaw * 0.4 + 0.18
        elif key == "confirmacao":
            yaw *= 0.3
        elif key == "alerta":
            surprise = math.exp(-age * 2.5)
            eye_open += 0.25 * surprise
            brow += 0.2 * surprise
            pitch -= 0.05 * surprise
        elif key == "erro":
            jitter = math.sin(t * 37.0) * math.sin(t * 11.0)
            rig.offset_x = 0.03 * jitter if abs(jitter) > 0.55 else 0.0
        if key != "erro":
            rig.offset_x = approach(rig.offset_x, 0.0, 20.0, dt)
        # aceno nas sílabas fortes da fala (subida real de energia)
        energy = float((mouth or {}).get("energy", 0.0)) if key == "falando" else 0.0
        if energy - self._last_energy > 0.25:
            self._nod = min(1.0, self._nod + 0.6)
        self._last_energy = energy
        self._nod = approach(self._nod, 0.0, 6.0, dt)
        pitch += 0.035 * self._nod
        rig.yaw = approach(rig.yaw, yaw, 4.0, dt)
        rig.pitch = approach(rig.pitch, pitch, 4.0, dt)
        rig.roll = approach(rig.roll, roll, 4.0, dt)
        rig.gaze_x = approach(rig.gaze_x, gaze_x, 6.0, dt)
        rig.gaze_y = approach(rig.gaze_y, gaze_y, 6.0, dt)
        rig.brow = approach(rig.brow, brow, 5.0, dt)
        if key == "inicializando" and rig.assemble < 0.85:
            eye_open = 0.0                                   # os olhos abrem quando o rosto está montado
        rig.eye_open = approach(rig.eye_open, eye_open, 6.0, dt)
        # --- piscadas
        self._blink(dt, allowed=rig.visor < 0.5 and key not in ("inicializando", "alerta") and rig.eye_open > 0.3)
        # --- boca (trilha labial do áudio real)
        shape = mouth if (mouth and key == "falando") else CLOSED_MOUTH
        rate = 40.0 if key == "falando" else 25.0
        rig.jaw = approach(rig.jaw, float(shape["open"]), rate, dt)
        rig.wide = approach(rig.wide, float(shape["wide"]), rate, dt)
        rig.round = approach(rig.round, float(shape["round"]), rate, dt)
        rig.press = approach(rig.press, float(shape["press"]), rate, dt)
        rig.teeth = approach(rig.teeth, float(shape["teeth"]), rate, dt)
        rig.energy = approach(rig.energy, float(shape.get("energy", 0.0)), rate, dt)
        return rig

    def _blink(self, dt: float, *, allowed: bool) -> None:
        rig = self.rig
        if self._blink_t >= 0:
            self._blink_t += dt
            phase = self._blink_t
            if phase < 0.06:
                rig.blink = phase / 0.06
            elif phase < 0.16:
                rig.blink = 1.0 - (phase - 0.06) / 0.10
            else:
                rig.blink = 0.0
                self._blink_t = -1.0
                if self._double:
                    self._double = False
                    self._next_blink = 0.12
            return
        if not allowed:
            rig.blink = approach(rig.blink, 0.0, 10.0, dt)
            return
        rig.blink = approach(rig.blink, 0.0, 10.0, dt)
        self._next_blink -= dt
        if self._next_blink <= 0:
            self._blink_t = 0.0
            self._double = self._rng.random() < 0.15
            self._next_blink = self._rng.uniform(2.5, 6.0)

    def in_motion(self) -> bool:
        """Há movimento que pede quadros (fala, boot, transição de estado recente, alerta, erro, pulso)."""
        rig = self.rig
        return (self.key in ("falando", "inicializando", "reconhecendo", "erro", "alerta")
                or self.t - self.since < 1.2 or rig.pulse > 0.05 or rig.dim > 0.05 or rig.jaw > 0.01
                or self._blink_t >= 0)
