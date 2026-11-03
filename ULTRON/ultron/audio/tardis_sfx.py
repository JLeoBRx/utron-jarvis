"""Sons da TARDIS — efeitos ORIGINAIS sintetizados (numpy), substituíveis por arquivos autorizados do usuário.

O som característico da série é obra protegida: o JARVIS não o inclui nem o distribui. Os efeitos abaixo são
criações próprias de ficção científica (ondas de fase, ressonâncias metálicas, mecânica da cabine). Se você tiver
um arquivo com licença para uso, coloque-o na pasta de sons do usuário (``sons_tardis`` na pasta de dados do
JARVIS) com um destes nomes — ele substitui o efeito original e nunca vai para o repositório:

    materializacao.wav · desmaterializacao.wav · porta_abrir.wav · porta_fechar.wav · rotor.wav · alerta.wav ·
    ambiente.wav

Disparo por eventos REAIS (``NeuralAudio``): tarefa da TARDIS começando (desmaterialização curta + rotor),
terminando com resultado (materialização), falhando (alerta); entrar e sair da sala (portas); ambiente da sala
(laço discreto) só com a página TARDIS à frente e ``ambient_sound`` ligado. Volume próprio
(``tardis_sfx_volume``), liga/desliga (``tardis_sfx``) e o liga/desliga geral dos efeitos (``sound_effects``).
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger("ultron.tardis_sfx")

RATE = 22050
FILES = {"materializacao": "materializacao.wav", "desmaterializacao": "desmaterializacao.wav",
         "porta_abrir": "porta_abrir.wav", "porta_fechar": "porta_fechar.wav", "rotor": "rotor.wav",
         "alerta": "alerta.wav", "ambiente": "ambiente.wav"}
def _noise(n: int, seed: int) -> np.ndarray:
    """Ruído determinístico: o mesmo som a cada execução (cada efeito com a sua semente)."""
    return np.random.default_rng(1963 + seed).standard_normal(n).astype(np.float32)


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(RATE * seconds), dtype=np.float32) / RATE


def _lowpass(x: np.ndarray, cutoff) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    return np.fft.irfft(spec / np.sqrt(1 + (freqs / cutoff) ** 4), n=len(x)).astype(np.float32)


def _bandpass(x: np.ndarray, low: float, high: float) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    gain = 1 / np.sqrt(1 + (low / np.maximum(freqs, 1e-3)) ** 4) / np.sqrt(1 + (freqs / high) ** 4)
    return np.fft.irfft(spec * gain, n=len(x)).astype(np.float32)


def _fade(x: np.ndarray, attack: float = 0.01, release: float = 0.05) -> np.ndarray:
    a, r = max(1, int(RATE * attack)), max(1, int(RATE * release))
    x = x.copy()
    x[:a] *= np.linspace(0, 1, min(a, len(x)), dtype=np.float32)[: min(a, len(x))]
    if r < len(x):
        x[-r:] *= np.linspace(1, 0, r, dtype=np.float32) ** 2
    return x


def _norm(x: np.ndarray, peak: float = 0.85) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


def _swell(seconds: float, center: float, *, rising: bool) -> np.ndarray:
    """Uma "onda de fase": ruído filtrado com ressonância que varre a frequência e cresce/decai."""
    t = _t(seconds)
    noise = _noise(len(t), 1)
    band = _bandpass(noise, center * 0.6, center * 1.6)
    sweep = np.sin(2 * np.pi * np.cumsum(center * (0.8 + 0.4 * (t / seconds if rising else 1 - t / seconds))) / RATE)
    env = np.sin(np.pi * t / seconds) ** 2
    return (band * 0.6 + 0.4 * sweep * band.std() * 3) * env


def materialize(seconds: float = 6.0) -> np.ndarray:
    """Chegada: ondas de fase que se repetem cada vez mais firmes, sobre um ronco mecânico e um acorde metálico
    que se fixa; termina num baque grave (a nave "assentando")."""
    t = _t(seconds)
    out = np.zeros(len(t), dtype=np.float32)
    starts = np.linspace(0.0, seconds * 0.62, 5)
    for k, start in enumerate(starts):
        swell = _swell(1.25, 380 + 40 * k, rising=k % 2 == 0) * (0.45 + 0.13 * k)
        i = int(start * RATE)
        out[i:i + len(swell)] += swell[: len(out) - i]
    grind = np.sin(2 * np.pi * 58 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 1.6 * t)) * 0.25
    chord = sum(np.sin(2 * np.pi * f * t + p) for f, p in ((220, 0), (277.2, 1.1), (329.6, 2.3), (440.7, 0.4)))
    chord = chord * np.clip((t - seconds * 0.35) / (seconds * 0.4), 0, 1) * 0.08
    thud_t = t - seconds * 0.86
    thud = np.where(thud_t > 0, np.sin(2 * np.pi * 46 * thud_t) * np.exp(-thud_t * 9), 0) * 0.9
    out += _lowpass(grind, 400) + chord + thud
    return _norm(_fade(out, 0.2, 0.6))


def dematerialize(seconds: float = 5.0) -> np.ndarray:
    """Partida: as mesmas ondas de fase, cada vez mais fracas e graves, até sumir."""
    t = _t(seconds)
    out = np.zeros(len(t), dtype=np.float32)
    for k, start in enumerate(np.linspace(0.0, seconds * 0.6, 4)):
        swell = _swell(1.3, 420 - 50 * k, rising=k % 2 == 1) * (0.9 - 0.18 * k)
        i = int(start * RATE)
        out[i:i + len(swell)] += swell[: len(out) - i]
    hum = np.sin(2 * np.pi * (70 - 25 * t / seconds) * t) * np.exp(-t * 0.6) * 0.3
    out += _lowpass(hum, 300)
    return _norm(_fade(out, 0.05, 1.2))


def door_open() -> np.ndarray:
    """Trinco metálico + rangido de madeira (ressonância que sobe) + ar entrando."""
    t = _t(0.95)
    click = np.where(t < 0.03, _noise(len(t), 2) * np.exp(-t * 180), 0)
    creak_f = 180 + 260 * np.clip((t - 0.08) / 0.6, 0, 1)
    creak = np.sin(2 * np.pi * np.cumsum(creak_f) / RATE) * np.sign(np.sin(2 * np.pi * 31 * t)) * 0.18
    creak *= np.clip((t - 0.06) / 0.1, 0, 1) * np.clip((0.75 - t) / 0.2, 0, 1)
    air = _bandpass(_noise(len(t), 3), 900, 4000) * np.sin(np.pi * t / 0.95) * 0.12
    return _norm(_fade(_lowpass(click + creak + air, 5000), 0.002, 0.15), 0.7)


def door_close() -> np.ndarray:
    """Batida abafada + trinco fechando."""
    t = _t(0.7)
    thump = np.sin(2 * np.pi * 72 * t) * np.exp(-t * 16) * 0.9
    knock = _lowpass(_noise(len(t), 4), 900) * np.exp(-t * 40) * 0.6
    latch_t = t - 0.18
    latch = np.where(latch_t > 0, _noise(len(t), 5) * np.exp(-np.maximum(latch_t, 0) * 220), 0) * 0.35
    return _norm(_fade(thump + knock + latch, 0.001, 0.2), 0.75)


def rotor_start(seconds: float = 2.2) -> np.ndarray:
    """O rotor ganhando energia: zumbido que sobe com brilho harmônico e pulsação acelerando."""
    t = _t(seconds)
    f0 = 55 + 55 * (t / seconds) ** 0.7
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    tone = np.sin(phase) * 0.5 + np.sin(2 * phase) * 0.25 + np.sin(3.01 * phase) * 0.12 + np.sin(5.02 * phase) * 0.05
    pulse = 0.65 + 0.35 * np.sin(2 * np.pi * np.cumsum(2 + 6 * t / seconds) / RATE)
    return _norm(_fade(tone * pulse * np.clip(t / 0.4, 0, 1), 0.05, 0.5), 0.7)


def alert() -> np.ndarray:
    """Alerta próprio: dois toques de sino grave inarmônico (sem imitar sinos de obras conhecidas)."""
    def bell(seconds=0.9):
        t = _t(seconds)
        partials = ((98, 1.0), (196.9, 0.55), (268.3, 0.4), (391.1, 0.25), (530.7, 0.15))
        return sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * (2.2 + f / 300)) for f, a in partials)
    gap = np.zeros(int(RATE * 0.25), dtype=np.float32)
    return _norm(_fade(np.concatenate([bell(), gap, bell() * 0.8]), 0.003, 0.3), 0.75)


def ambient(seconds: float = 8.0) -> np.ndarray:
    """Laço da sala: zumbido de máquina grave, respiração lenta e tique mecânico distante (emenda sem estalo)."""
    t = _t(seconds)
    hum = (np.sin(2 * np.pi * 50 * t) * 0.5 + np.sin(2 * np.pi * 100.5 * t) * 0.2
           + np.sin(2 * np.pi * 150.2 * t) * 0.08) * (0.8 + 0.2 * np.sin(2 * np.pi * t / seconds))
    breath = _bandpass(_noise(len(t), 6), 200, 900) * \
        (0.5 + 0.5 * np.sin(2 * np.pi * 2 * t / seconds)) * 0.08
    ticks = np.zeros(len(t), dtype=np.float32)
    for start in np.arange(0.4, seconds, 1.3):
        i = int(start * RATE)
        n = min(int(RATE * 0.02), len(t) - i)
        ticks[i:i + n] += np.exp(-np.arange(n) / RATE * 300) * 0.25
    loop = hum * 0.4 + breath + _lowpass(ticks, 2500)
    edge = int(RATE * 0.25)                                   # emenda: cruzamento das pontas
    loop[:edge] = loop[:edge] * np.linspace(0, 1, edge) + loop[-edge:] * np.linspace(1, 0, edge)
    return _norm(loop[:-edge], 0.5)


BUILDERS = {"materializacao": materialize, "desmaterializacao": dematerialize, "porta_abrir": door_open,
            "porta_fechar": door_close, "rotor": rotor_start, "alerta": alert, "ambiente": ambient}


def read_wav(path: Path) -> np.ndarray:
    """WAV PCM de 8/16/32 bits, mono ou estéreo, em qualquer taxa → mono float32 a ``RATE``."""
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(width)
    if dtype is None:
        raise ValueError(f"WAV de {width * 8} bits não suportado")
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if width == 1:
        data = (data - 128.0) / 128.0
    else:
        data /= float(np.iinfo(dtype).max)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != RATE and len(data):
        positions = np.arange(0, len(data), rate / RATE)
        data = np.interp(positions, np.arange(len(data)), data).astype(np.float32)
    return data.astype(np.float32)


def load(user_dir: Path | None) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """(sons, origem de cada um: "original" ou o arquivo do usuário). Arquivo ilegível → efeito original + aviso."""
    sounds: dict[str, np.ndarray] = {}
    origin: dict[str, str] = {}
    for key, build in BUILDERS.items():
        path = Path(user_dir) / FILES[key] if user_dir else None
        if path is not None and path.is_file():
            try:
                sounds[key] = read_wav(path)
                origin[key] = path.name
                continue
            except (OSError, ValueError, wave.Error) as exc:
                log.warning("som da TARDIS do usuário ignorado (%s): %s", path.name, exc)
        sounds[key] = build()
        origin[key] = "original"
    return sounds, origin
