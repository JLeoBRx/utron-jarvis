"""Sincronização labial: a boca do avatar acompanha o ÁUDIO REAL da fala.

Três fontes, da mais precisa para a menos:

1. **alinhamento do modelo** — quando a voz Piper exporta a duração de cada fonema
   (``include_alignments``), cada visema cai exatamente no seu trecho de áudio;
2. **fonemas sobre o áudio real** — a voz informa os fonemas (IPA do espeak) de cada frase, mas não o
   tempo de cada um: os visemas são distribuídos APENAS pelos quadros sonoros daquela frase (as pausas
   caem nos silêncios reais), com peso maior para vogais tônicas e longas;
3. **espectro do áudio real** — sem fonemas (voz SAPI do Windows): a forma da boca vem do espectro de
   cada quadro (sibilantes, vogais abertas, arredondadas).

Em todos os casos a ABERTURA é multiplicada pela energia real do áudio: no silêncio a boca fecha;
nunca há abre-e-fecha aleatório. Interrompida a fala, o ``Speaker`` descarta a trilha e a boca volta ao
repouso no mesmo quadro.

Visema = (abertura, largura, arredondamento, pressão dos lábios, dentes), todos em 0..1 (largura e
arredondamento podem ser negativos: lábios estreitos).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import numpy as np

FRAME_S = 0.010
VOICED_THRESHOLD = 0.10

VISEMES: dict[str, tuple[float, float, float, float, float]] = {
    "SIL": (0.00, 0.00, 0.00, 0.15, 0.0),
    "PBM": (0.00, 0.00, 0.10, 1.00, 0.0),
    "FV": (0.10, 0.10, 0.00, 0.55, 1.0),
    "TDN": (0.24, 0.20, 0.00, 0.00, 1.0),
    "SZ": (0.14, 0.35, 0.00, 0.00, 1.0),
    "SH": (0.20, -0.25, 0.60, 0.00, 1.0),
    "KG": (0.34, 0.05, 0.00, 0.00, 0.3),
    "R": (0.28, 0.10, 0.10, 0.00, 0.5),
    "L": (0.26, 0.15, 0.00, 0.00, 0.8),
    "AA": (0.88, 0.30, 0.00, 0.00, 0.2),
    "EE": (0.52, 0.60, 0.00, 0.00, 0.5),
    "II": (0.30, 0.90, 0.00, 0.00, 0.9),
    "OO": (0.58, -0.40, 0.80, 0.00, 0.1),
    "UU": (0.30, -0.60, 1.00, 0.00, 0.0),
}
REST = np.array(VISEMES["SIL"], dtype=np.float32)

_CONS = {
    "p": "PBM", "b": "PBM", "m": "PBM",
    "f": "FV", "v": "FV",
    "t": "TDN", "d": "TDN", "n": "TDN", "ɲ": "TDN", "ŋ": "KG",
    "s": "SZ", "z": "SZ", "ʃ": "SH", "ʒ": "SH",
    "k": "KG", "g": "KG", "ɡ": "KG", "x": "KG", "ɣ": "KG", "h": "KG", "ʁ": "R", "χ": "KG",
    "ɾ": "R", "r": "R", "ɹ": "R",
    "l": "L", "ʎ": "L", "ɫ": "L",
    "j": "II", "w": "UU",
}
_VOW = {
    "a": "AA", "ɐ": "AA", "æ": "AA", "ɑ": "AA",
    "e": "EE", "ɛ": "EE", "ə": "EE",
    "i": "II", "ɪ": "II", "y": "II",
    "o": "OO", "ɔ": "OO",
    "u": "UU", "ʊ": "UU",
}
_PAUSE = set(",;:.!?…")
_MODIFIERS = {"ː", "ʲ", "ʷ", "͡", "̃"}

METHOD_LABELS = {"alignment": "alinhamento do modelo de voz", "phonemes": "fonemas sobre o áudio real",
                 "spectral": "espectro do áudio real", "none": "sem fala"}


@dataclass
class Token:
    viseme: str
    weight: float
    word: int                 # índice da palavra dentro do trecho (para a legenda)


def viseme_of(phoneme: str) -> str | None:
    """Visema de um fonema IPA (None = sem efeito na boca: acento, diacrítico)."""
    for ch in unicodedata.normalize("NFD", str(phoneme or "")):
        if ch in _VOW:
            return _VOW[ch]
        if ch in _CONS:
            return _CONS[ch]
        if ch in _PAUSE:
            return "SIL"
    return None


def tokens(phonemes: list[str] | str) -> list[Token]:
    """Fonemas do espeak (caracteres IPA) → tokens de visema com peso e palavra."""
    text = unicodedata.normalize("NFD", "".join(phonemes))
    out: list[Token] = []
    word = 0
    stress = False
    after_pause = False                                 # "a, b": a vírgula já separou as palavras
    for ch in text:
        if ch in ("ˈ", "ˌ"):
            stress = ch == "ˈ"
            continue
        if unicodedata.combining(ch) or ch in _MODIFIERS:
            if out and ch == "ː":
                out[-1].weight *= 1.5
            continue
        if ch == " ":
            if not after_pause:
                word += 1
            after_pause = False
            continue
        if ch in _PAUSE:
            out.append(Token("SIL", 0.0, word))       # pausa: sem tempo próprio (cai num silêncio real)
            word += 1
            after_pause = True
            continue
        after_pause = False
        if ch in _VOW:
            out.append(Token(_VOW[ch], 1.6 if stress else 1.0, word))
            stress = False
        elif ch in _CONS:
            out.append(Token(_CONS[ch], 0.62, word))
    return out


@dataclass
class Segment:
    """Um trecho (frase) do áudio final: amostras [start, end), fonemas e, se houver, o alinhamento."""

    start: int
    end: int
    phonemes: list[str] | None = None
    alignment: list[tuple[str, int]] | None = None      # (fonema, nº de amostras), na taxa ORIGINAL
    scale: float = 1.0                                  # amostras finais por amostra original


class LipSyncTrack:
    """Trilha da boca para UMA fala, em quadros de 10 ms: forma (5 parâmetros), energia real e o
    progresso das palavras (legenda)."""

    def __init__(self, samples: np.ndarray, rate: int, segments: list[Segment] | None = None):
        self.rate = int(rate)
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        hop = max(1, int(self.rate * FRAME_S))
        self.hop = hop
        n = max(1, len(samples) // hop)
        self.n = n
        frames = samples[: n * hop].reshape(n, hop) if len(samples) >= hop else np.zeros((1, hop), np.float32)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        loud = rms[rms > 1e-5]
        ref = float(np.percentile(loud, 95)) if loud.size else 1.0
        self.energy = np.clip(rms / max(ref, 1e-4), 0.0, 1.2).astype(np.float32)
        self.voiced = self.energy > VOICED_THRESHOLD
        self.params = np.zeros((n, 5), dtype=np.float32)
        self.params[:] = REST
        self.word = np.full(n, -1, dtype=np.int32)
        self.methods: set[str] = set()
        self.total_words = 0
        if not segments:
            segments = [Segment(0, len(samples))]
        for seg in segments:
            a = max(0, seg.start // hop)
            b = min(n, max(a + 1, seg.end // hop))
            if b <= a:
                continue
            if seg.alignment:
                words = self._place_alignment(seg, a, b)
                self.methods.add("alignment")
            elif seg.phonemes:
                words = self._place_tokens(tokens(seg.phonemes), a, b)
                self.methods.add("phonemes")
            else:
                self._spectral(samples, a, b)
                words = self._place_energy_words(a, b)
                self.methods.add("spectral")
            self.total_words += words
        # coarticulação: suaviza a FORMA (não a energia) em ~30 ms
        kernel = np.array([0.25, 0.5, 0.25], dtype=np.float32)
        for column in range(1, 5):
            self.params[:, column] = np.convolve(self.params[:, column], kernel, mode="same")
        # a energia REAL governa a abertura; no silêncio a boca fecha
        opening = self.params[:, 0] * (0.30 + 0.70 * np.clip(self.energy, 0.0, 1.0))
        self.params[:, 0] = np.where(self.voiced, opening, 0.0)
        silent = ~self.voiced
        self.params[silent, 3] = np.maximum(self.params[silent, 3], REST[3])
        # palavras: o índice segue valendo nas pausas (legenda não "volta")
        filled = self.word.copy()
        last = -1
        for i in range(n):
            if filled[i] >= 0:
                last = filled[i]
            else:
                filled[i] = last
        self.word_ffill = filled

    # ------------------------------------------------------------ distribuição
    def _place_tokens(self, toks: list[Token], a: int, b: int) -> int:
        """Distribui os visemas só pelo tempo SONORO do trecho. Devolve o nº de palavras do trecho."""
        base = self.total_words
        words = (max((t.word for t in toks), default=-1) + 1) if toks else 0
        idx = np.arange(a, b)
        voiced = idx[self.voiced[a:b]]
        if not voiced.size or not toks:
            return words
        weights = np.array([t.weight for t in toks], dtype=np.float64)
        total = weights.sum()
        if total <= 0:
            return words
        edges = np.concatenate([[0.0], np.cumsum(weights)]) / total * len(voiced)
        for i, tok in enumerate(toks):
            if tok.weight <= 0:
                continue
            lo, hi = int(edges[i]), max(int(edges[i]) + 1, int(edges[i + 1]))
            frames = voiced[lo:min(hi, len(voiced))]
            self.params[frames] = VISEMES[tok.viseme]
            self.word[frames] = base + tok.word
        return words

    def _place_alignment(self, seg: Segment, a: int, b: int) -> int:
        """Alinhamento real (duração de cada fonema informada pelo modelo)."""
        base = self.total_words
        word = 0
        position = seg.start
        for phoneme, count in seg.alignment or ():
            length = int(round(count * seg.scale))
            if phoneme == " ":
                word += 1
            viseme = viseme_of(phoneme)
            lo, hi = max(a, position // self.hop), min(b, max(position // self.hop + 1, (position + length) // self.hop))
            if viseme is not None and hi > lo:
                self.params[lo:hi] = VISEMES[viseme]
                self.word[lo:hi] = base + word
            position += length
        return word + 1

    def _place_energy_words(self, a: int, b: int) -> int:
        """Sem fonemas: cada trecho sonoro contínuo conta como uma "palavra" para a legenda."""
        base = self.total_words
        count = 0
        inside = False
        for f in range(a, b):
            if self.voiced[f]:
                if not inside:
                    inside = True
                    count += 1
                self.word[f] = base + count - 1
            else:
                inside = False
        return count

    def _spectral(self, samples: np.ndarray, a: int, b: int) -> None:
        """Forma estimada pelo espectro de cada quadro do áudio real (voz sem fonemas)."""
        hop = self.hop
        window = np.hanning(hop * 2).astype(np.float32)
        freqs = np.fft.rfftfreq(hop * 2, 1.0 / self.rate)
        low = (freqs >= 250) & (freqs < 1000)
        mid = (freqs >= 1000) & (freqs < 3000)
        high = freqs >= 4000
        for f in range(a, b):
            if not self.voiced[f]:
                continue
            chunk = samples[f * hop: f * hop + hop * 2]
            if len(chunk) < hop * 2:
                break
            spectrum = np.abs(np.fft.rfft(chunk * window)) ** 2
            e_low, e_mid, e_high = spectrum[low].sum(), spectrum[mid].sum(), spectrum[high].sum()
            total = e_low + e_mid + e_high + 1e-12
            if e_high / total > 0.45:
                self.params[f] = VISEMES["SZ"]
            elif e_low / (e_mid + 1e-12) > 2.5:
                self.params[f] = VISEMES["OO"]
            elif e_mid / total > 0.5:
                self.params[f] = VISEMES["EE"]
            else:
                self.params[f] = VISEMES["AA"]

    # ------------------------------------------------------------ leitura
    @property
    def duration(self) -> float:
        return self.n * FRAME_S

    @property
    def method(self) -> str:
        for key in ("alignment", "phonemes", "spectral"):
            if key in self.methods:
                return key
        return "none"

    def at(self, seconds: float) -> tuple[np.ndarray, float, int]:
        """(forma da boca, energia real, palavra em curso) no instante ``seconds`` da reprodução."""
        if seconds < 0 or seconds >= self.duration:
            return REST.copy(), 0.0, -1
        position = seconds / FRAME_S
        i = int(position)
        j = min(self.n - 1, i + 1)
        w = position - i
        params = self.params[i] * (1 - w) + self.params[j] * w
        return params, float(self.energy[i] * (1 - w) + self.energy[j] * w), int(self.word_ffill[i])

    def word_progress(self, seconds: float) -> float:
        """Fração das palavras já ditas (0..1) — base da legenda sincronizada."""
        if self.total_words <= 0 or seconds <= 0:
            return 0.0
        if seconds >= self.duration:
            return 1.0
        word = int(self.word_ffill[min(self.n - 1, int(seconds / FRAME_S))])
        return max(0.0, min(1.0, (word + 1) / self.total_words))


def mouth_dict(params: np.ndarray, energy: float) -> dict:
    return {"open": float(params[0]), "wide": float(params[1]), "round": float(params[2]),
            "press": float(params[3]), "teeth": float(params[4]), "energy": float(energy)}


CLOSED = mouth_dict(REST, 0.0)
