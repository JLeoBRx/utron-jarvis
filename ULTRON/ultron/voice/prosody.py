"""Prosódia da fala — o que transforma texto correto em fala NATURAL (lógica pura, sem áudio).

O Piper lê bem uma frase isolada, mas fala tudo no mesmo ritmo e com as pausas que o modelo decidir. Esta camada:

1. **normaliza** o texto para a fala em português do Brasil (abreviações, símbolos, moedas, horas, endereços,
   parênteses, marcadores de lista) — sem inventar conteúdo;
2. **planeja** a fala em frases e respirações: pausas por pontuação (vírgula curta, ponto mais longo, parágrafo
   maior), quebra de frases longas nas vírgulas, alongamento no fim da frase, perguntas um pouco mais lentas,
   variação pequena e determinística de velocidade entre frases (nada de "metrônomo");
3. dá a cada trecho a **expressividade** do perfil (``noise_scale``/``noise_w_scale`` do Piper: o SAFRA varia a
   entonação e o ritmo; o ULTRON é mais plano e deliberado).

O sintetizador (``tts.py``) gera cada trecho, remove o silêncio que o modelo coloca nas pontas e insere as pausas
planejadas; a boca do holograma segue o áudio final (silêncio = boca fechada).
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Style:
    """Expressividade de uma identidade vocal."""

    noise_scale: float = 0.72        # variação de entonação (Piper; padrão do modelo 0,667)
    noise_w_scale: float = 0.85      # variação de duração dos fonemas (ritmo)
    pause_scale: float = 1.0         # multiplica todas as pausas
    jitter: float = 0.025            # variação máxima de velocidade entre frases (±)
    final_lengthening: float = 1.05  # a última frase de um parágrafo um pouco mais lenta


JARVIS_STYLE = Style()
ULTRON_STYLE = Style(noise_scale=0.5, noise_w_scale=0.55, pause_scale=1.3, jitter=0.01, final_lengthening=1.09)

PAUSES = {",": 0.15, ";": 0.24, ":": 0.22, "—": 0.2, ".": 0.36, "!": 0.36, "?": 0.42, "…": 0.48, "¶": 0.55}
LONG_PHRASE_WORDS = 14            # frases maiores que isso respiram nas vírgulas


@dataclass
class Phrase:
    text: str
    length_mult: float = 1.0         # multiplica o length_scale do perfil (> 1 = mais lento)
    pause_after: float = 0.0         # silêncio depois do trecho (s)
    noise_scale: float = 0.72
    noise_w_scale: float = 0.85
    question: bool = False


# ------------------------------------------------------------------ normalização
_ABBREV = (
    (r"\bSr\.", "senhor"), (r"\bSra\.", "senhora"), (r"\bSrta\.", "senhorita"), (r"\bDr\.", "doutor"),
    (r"\bDra\.", "doutora"), (r"\bProf\.", "professor"), (r"\bex\.:?", "por exemplo,"), (r"\bp\.\s?ex\.", "por exemplo"),
    (r"\betc\.", "etcétera."), (r"\bobs\.:?", "observação:"), (r"\bn[ºo°]\s?(?=\d)", "número "),
    (r"\bvs\.?", "versus"), (r"\bapprox\.|\baprox\.", "aproximadamente"), (r"\bmin\.(?=\s|$)", "minutos"),
    (r"\bseg\.(?=\s|$)", "segundos"),
)
_UNITS = (("km/h", "quilômetros por hora"), ("km", "quilômetros"), ("kg", "quilos"), ("GB", "gigabytes"),
          ("MB", "megabytes"), ("KB", "quilobytes"), ("TB", "terabytes"), ("ms", "milissegundos"),
          ("GHz", "gigahertz"), ("MHz", "megahertz"), ("°C", "graus"), ("cm", "centímetros"), ("mm", "milímetros"))


def _money(match: re.Match, word_singular: str, word_plural: str) -> str:
    value = match.group(1)
    integer = value.replace(".", "").split(",")[0]
    word = word_singular if integer == "1" else word_plural
    cents = value.split(",")[1] if "," in value else ""
    if cents and cents.strip("0"):
        return f"{integer} {word} e {int(cents)} centavos"
    return f"{integer} {word}"


def normalize(text: str) -> str:
    """Texto escrito → texto falável (só forma; o conteúdo não muda)."""
    t = str(text or "")
    t = re.sub(r"https?://(?:www\.)?([^/\s?#]+)\S*?(?=[.,;!?]?(?:\s|$))",
               lambda m: m.group(1).replace(".", " ponto "), t)                 # só o domínio, falado
    t = re.sub(r"`{1,3}[^`]*`{1,3}", " ", t)                                # trechos de código não são lidos
    t = re.sub(r"[*_#>]{1,3}", "", t)                                       # marcação
    t = re.sub(r"^\s*[-•▸]\s+", "", t, flags=re.MULTILINE)                  # marcadores de lista
    t = re.sub(r"\n{2,}", " ¶ ", t)
    t = re.sub(r"\s*\n\s*", ". ", t)
    for pattern, spoken in _ABBREV:
        t = re.sub(pattern, spoken, t, flags=re.IGNORECASE)
    t = re.sub(r"R\$\s?(\d[\d.]*(?:,\d+)?)", lambda m: _money(m, "real", "reais"), t)
    t = re.sub(r"US\$\s?(\d[\d.]*(?:,\d+)?)", lambda m: _money(m, "dólar", "dólares"), t)
    t = re.sub(r"€\s?(\d[\d.]*(?:,\d+)?)", lambda m: _money(m, "euro", "euros"), t)
    t = re.sub(r"\b(\d{1,2})h(\d{2})\b", r"\1 e \2", t)                     # 15h30 → 15 e 30
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b(?!:)", lambda m: f"{m.group(1)} e {m.group(2)}"
               if m.group(2) != "00" else f"{m.group(1)} horas", t)
    t = re.sub(r"\b(\d{1,2})h\b", r"\1 horas", t)
    t = re.sub(r"(\d)\s?%", r"\1 por cento", t)
    for unit, spoken in _UNITS:
        t = re.sub(rf"(\d)\s?{re.escape(unit)}\b", rf"\1 {spoken}", t)
    t = re.sub(r"(\d)\s?[x×]\b", r"\1 vezes", t)
    t = t.replace("→", ", para ").replace("·", ", ").replace("—", " — ").replace("–", " — ")
    t = re.sub(r"\s*\(([^)]{1,120})\)\s*", r", \1, ", t)                    # parênteses viram uma inserção falada
    t = re.sub(r"(?<=\w)/(?=\w)", " ou ", t)
    t = re.sub(r"\.{3,}", "…", t)
    t = re.sub(r"[\"“”«»]", "", t)
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    t = re.sub(r",\s*([.;:!?…])", r"\1", t)
    t = re.sub(r"([,;:])(?=[^\s\d])", r"\1 ", t)                         # 2,5 continua número
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" ,")


# ------------------------------------------------------------------ planejamento
_SENTENCE = re.compile(r"[^.!?…¶]+(?:[.!?…]+|¶|$)")


def _jitter(text: str, amount: float) -> float:
    if amount <= 0:
        return 1.0
    h = zlib.crc32(text.encode("utf-8")) % 1000 / 1000.0          # determinístico: o mesmo texto, o mesmo ritmo
    return 1.0 + (h * 2 - 1) * amount


def plan(text: str, style: Style = JARVIS_STYLE) -> list[Phrase]:
    """Texto → trechos com velocidade, pausa e expressividade."""
    clean = normalize(text)
    sentences = [s.strip() for s in _SENTENCE.findall(clean) if s.strip()]
    phrases: list[Phrase] = []
    for index, sentence in enumerate(sentences):
        paragraph_end = sentence.endswith("¶")
        sentence = sentence.rstrip("¶ ").strip()
        if not sentence or not re.search(r"\w", sentence):
            if phrases and paragraph_end:
                phrases[-1].pause_after = max(phrases[-1].pause_after, PAUSES["¶"] * style.pause_scale)
            continue
        end = sentence[-1] if sentence[-1] in ".!?…" else "."
        question = end == "?"
        parts = [sentence]
        if len(sentence.split()) > LONG_PHRASE_WORDS:                 # frase longa: respira nas pausas internas
            parts = [p.strip() for p in re.findall(r"[^,;:—]+[,;:—]?", sentence) if p.strip(" ,;:—")]
            merged: list[str] = []
            for part in parts:                                          # nunca trechos de 1–2 palavras soltos
                if merged and len(merged[-1].split()) < 4:
                    merged[-1] = f"{merged[-1]} {part}"
                else:
                    merged.append(part)
            parts = merged
        for k, part in enumerate(parts):
            last_of_sentence = k == len(parts) - 1
            mark = part[-1] if part[-1] in PAUSES else (end if last_of_sentence else ",")
            pause = PAUSES.get(mark, 0.15) * style.pause_scale
            mult = _jitter(part, style.jitter)
            if last_of_sentence and (index == len(sentences) - 1 or paragraph_end):
                mult *= style.final_lengthening                         # alongamento de fim de enunciado
            if question:
                mult *= 1.03
            words = len(part.split())
            if words >= 18:
                mult *= 0.97                                            # trechos longos fluem um pouco mais rápido
            elif words <= 3:
                mult *= 1.04                                            # trechos curtos com mais peso
            phrases.append(Phrase(part.strip(" —"), round(mult, 3), round(pause, 3), style.noise_scale,
                                  style.noise_w_scale, question))
        if paragraph_end:
            phrases[-1].pause_after = max(phrases[-1].pause_after, PAUSES["¶"] * style.pause_scale)
    if phrases:
        phrases[-1].pause_after = 0.0                                   # sem silêncio depois da última palavra
    return phrases
