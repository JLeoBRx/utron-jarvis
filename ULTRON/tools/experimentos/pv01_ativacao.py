"""PV-01 — Palavra de ativação e reconhecimento de comandos.

Mede, com o MESMO código do SAFRA (``VoskSTT``, ``calibrate.transcribe``, ``WakeWordDetector``):

* **taxa de ativação correta** — frases "<palavra>, <comando>" que ativam o assistente;
* **taxa de erro de palavras (WER) do comando** — o que sobra depois da palavra de ativação, comparado ao texto;
* **ativações indevidas** — frases sem a palavra de ativação no início que ativam (inclui "safra" no meio da
  frase, que nunca deve ativar);
* **palavra sozinha** — só "Safra." ou "Jarvis." (o fluxo em que o assistente confirma e espera o comando);
* **palavra comum no início** — frases que começam com "safra" sem intenção de comando (limitação conhecida).

Dois modos:

* ``sintetico`` (padrão): a voz Piper do SAFRA fala as frases, em três velocidades e três níveis de ruído
  branco (sem ruído, 20 dB e 10 dB de relação sinal-ruído), e o Vosk reconhece o áudio. Mede o canal
  reconhecedor ↔ detector com UMA voz sintética: **não substitui voz humana nem microfone**.
* ``--gravacoes PASTA``: arquivos WAV (16 kHz, mono, 16 bits) gravados por pessoas. O texto falado vem de
  ``PASTA/roteiro.csv`` (``arquivo;texto;tipo`` com tipo = ativacao | negativa). É o modo da etapa B do protocolo.

Uso:  python tools/experimentos/pv01_ativacao.py [--rapido] [--modelos pequeno,grande] [--rotulo NOME]
"""
from __future__ import annotations

import csv
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum as C  # noqa: E402

PALAVRAS = ("Safra", "Jarvis")
COMANDOS = (
    "que horas são", "abra o bloco de notas", "anote uma ideia comprar sementes", "aumente o volume",
    "status do sistema", "abra a tardis", "o que eu tenho amanhã", "me lembre de ligar para a escola amanhã",
    "qual é a previsão do tempo", "liste os meus compromissos",
)
NEGATIVAS = (
    "a safra de café deste ano foi boa", "o caminhão levou a safra inteira", "a melhor safra de uvas foi a passada",
    "vamos jantar mais cedo hoje", "o jogo começa às oito", "você viu o aviso da escola",
    "as aves voltaram para o jardim", "ele disse que a vez dele já passou", "preciso comprar pão e leite",
    "a reunião foi adiada para quinta", "minha irmã chega amanhã de manhã", "o filme de ontem foi muito bom",
    "esqueci o guarda-chuva no carro", "o cachorro latiu a noite toda", "a conta de luz veio alta",
    "amanhã tem prova de matemática", "o ônibus atrasou de novo", "liga a televisão para mim",
    "o mercado fecha às dez", "a professora mandou um recado", "ele trabalha no centro da cidade",
    "estou com fome", "vamos sair no fim de semana", "o computador está lento hoje",
)
INICIO_COMUM = ("safra boa este ano", "safra de soja bate recorde", "safra recorde no paraná")
VELOCIDADES = (0.85, 1.0, 1.2)            # length_scale do Piper (menor = mais rápido)
RUIDOS_DB = (None, 20.0, 10.0)            # relação sinal-ruído; None = sem ruído
REPETICOES = 2                            # o Piper (VITS) sorteia variações a cada síntese: cada frase é falada 2×


def _modelos(nomes: str) -> dict[str, Path]:
    from ultron.voice.stt import LARGE, SMALL
    base = C.RAIZ / "assets" / "stt"
    disponiveis = {"pequeno": base / SMALL, "grande": base / LARGE}
    return {n: disponiveis[n] for n in nomes.split(",") if n in disponiveis and disponiveis[n].is_dir()}


def _pcm(samples, rate: int, snr_db: float | None, seed: int) -> bytes:
    import numpy as np
    from ultron.voice import dsp
    x = dsp.resample(np.asarray(samples, dtype=np.float32), 16000 / rate)
    if snr_db is not None:
        potencia = float(np.mean(x ** 2)) or 1e-9
        ruido = np.random.default_rng(seed).normal(0.0, (potencia / 10 ** (snr_db / 10)) ** 0.5, len(x))
        x = (x + ruido).astype(np.float32)
    pausa = np.zeros(4000, np.float32)                 # 0,25 s de silêncio antes e depois (como no microfone)
    return dsp.to_int16(np.concatenate([pausa, x, pausa]))


def _semente(i: int, j: int, escala: float, snr: float | None) -> int:
    """Semente fixa por amostra: o mesmo ruído em toda execução (reprodutível)."""
    return i * 100000 + j * 1000 + int(escala * 100) * 10 + (0 if snr is None else int(snr))


def _avaliar(detector, ref_comando: str | None, texto: str) -> dict:
    r = detector.detect(texto)
    item = {"transcricao": texto, "ativou": bool(r.detected), "forma": r.matched, "forca": r.strength}
    if ref_comando is not None:
        item["comando"] = r.command
        item["wer_comando"] = round(C.wer(ref_comando, r.command if r.detected else texto), 4)
    return item


def sintetico(args) -> dict:
    from ultron.voice.calibrate import transcribe
    from ultron.voice.stt import VoskSTT
    from ultron.voice.tts import PiperSynth
    from ultron.voice.wake_word import WakeWordDetector
    from ultron.config.settings import Settings
    voz = C.RAIZ / "assets" / "voices" / "pt_BR-faber-medium.onnx"
    piper = PiperSynth(str(voz))
    s = Settings()
    detector = WakeWordDetector(tuple(s.wake_words), tuple(s.wake_variants), weak=tuple(s.wake_weak_variants),
                                names=tuple(s.wake_names))
    comandos = COMANDOS[:3] if args.rapido else COMANDOS
    negativas = NEGATIVAS[:6] if args.rapido else NEGATIVAS
    velocidades = (1.0,) if args.rapido else VELOCIDADES
    repeticoes = 1 if args.rapido else REPETICOES
    ruidos = (None,) if args.rapido else RUIDOS_DB
    cache: dict[tuple, tuple] = {}

    def falar(texto: str, escala: float, rep: int = 0):
        chave = (texto, escala, rep)
        if chave not in cache:
            audio, rate = piper.synthesize(texto, length_scale=escala)
            cache[chave] = (audio, rate)
        return cache[chave]

    saida = {"modelos": {}}
    for nome, caminho in _modelos(args.modelos).items():
        stt = VoskSTT(caminho)
        brutos = []
        for rep, escala in [(r, e) for r in range(repeticoes) for e in velocidades]:
            for snr in ruidos:
                for i, palavra in enumerate(PALAVRAS):
                    for j, cmd in enumerate(comandos):
                        audio, rate = falar(f"{palavra}, {cmd}.", escala, rep)
                        texto = transcribe(stt, _pcm(audio, rate, snr, seed=_semente(i, j, escala, snr) + rep))
                        brutos.append({"tipo": "ativacao", "palavra": palavra, "comando_ref": cmd, "escala": escala, "rep": rep,
                                       "snr_db": snr, **_avaliar(detector, cmd, texto)})
                    audio, rate = falar(f"{palavra}.", escala, rep)       # a palavra sozinha (fluxo "Safra." → confirmação)
                    texto = transcribe(stt, _pcm(audio, rate, snr, seed=_semente(i, 99, escala, snr) + rep))
                    brutos.append({"tipo": "so_palavra", "palavra": palavra, "escala": escala, "snr_db": snr,
                                   **_avaliar(detector, None, texto)})
                for j, frase in enumerate(negativas + INICIO_COMUM):
                    audio, rate = falar(f"{frase}.", escala, rep)
                    texto = transcribe(stt, _pcm(audio, rate, snr, seed=_semente(9, j, escala, snr) + rep))
                    tipo = "inicio_comum" if frase in INICIO_COMUM else "negativa"
                    brutos.append({"tipo": tipo, "frase": frase, "escala": escala, "snr_db": snr,
                                   **_avaliar(detector, None, texto)})
        saida["modelos"][nome] = {"amostras": brutos, "metricas": _metricas(brutos)}
        print(f"[{nome}] " + "; ".join(f"{k}: {v.get('taxa')}" for k, v in saida["modelos"][nome]["metricas"].items()
                                       if isinstance(v, dict) and "taxa" in v), flush=True)
    return saida


def _metricas(brutos: list[dict]) -> dict:
    m: dict = {}
    for palavra in PALAVRAS:
        amostras = [b for b in brutos if b["tipo"] == "ativacao" and b["palavra"] == palavra]
        m[f"ativacao_{palavra.lower()}"] = C.proporcao(sum(b["ativou"] for b in amostras), len(amostras))
        m[f"wer_comando_{palavra.lower()}"] = C.resumo([b["wer_comando"] for b in amostras])
        for snr in sorted({b["snr_db"] for b in amostras}, key=lambda v: -1 if v is None else v):
            sub = [b for b in amostras if b["snr_db"] == snr]
            rotulo = "limpo" if snr is None else f"snr{int(snr)}"
            m[f"ativacao_{palavra.lower()}_{rotulo}"] = C.proporcao(sum(b["ativou"] for b in sub), len(sub))
        so = [b for b in brutos if b["tipo"] == "so_palavra" and b["palavra"] == palavra]
        m[f"palavra_sozinha_{palavra.lower()}"] = C.proporcao(sum(b["ativou"] for b in so), len(so))
    neg = [b for b in brutos if b["tipo"] == "negativa"]
    m["ativacao_indevida"] = C.proporcao(sum(b["ativou"] for b in neg), len(neg))
    ini = [b for b in brutos if b["tipo"] == "inicio_comum"]
    m["ativacao_palavra_comum_no_inicio"] = C.proporcao(sum(b["ativou"] for b in ini), len(ini))
    transcricoes = {}
    for b in brutos:
        if b["tipo"] == "ativacao":
            primeira = (b["transcricao"].split() or ["(nada)"])[0]
            transcricoes.setdefault(b["palavra"], {}).setdefault(primeira, 0)
            transcricoes[b["palavra"]][primeira] += 1
    m["primeira_palavra_ouvida"] = transcricoes
    return m


def gravacoes(args) -> dict:
    """Etapa B: WAVs de pessoas reais com o roteiro em roteiro.csv (arquivo;texto;tipo)."""
    from ultron.voice.calibrate import transcribe
    from ultron.voice.stt import VoskSTT
    from ultron.voice.wake_word import WakeWordDetector
    from ultron.config.settings import Settings
    pasta = Path(args.gravacoes)
    s = Settings()
    detector = WakeWordDetector(tuple(s.wake_words), tuple(s.wake_variants), weak=tuple(s.wake_weak_variants),
                                names=tuple(s.wake_names))
    linhas = list(csv.reader((pasta / "roteiro.csv").read_text(encoding="utf-8").splitlines(), delimiter=";"))
    saida = {"modelos": {}}
    for nome, caminho in _modelos(args.modelos).items():
        stt = VoskSTT(caminho)
        brutos = []
        for arquivo, texto, tipo in linhas:
            with wave.open(str(pasta / arquivo), "rb") as w:
                if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
                    raise SystemExit(f"{arquivo}: precisa ser WAV 16 kHz, mono, 16 bits")
                pcm = w.readframes(w.getnframes())
            ouvido = transcribe(stt, pcm)
            palavra = next((p for p in PALAVRAS if texto.lower().startswith(p.lower())), None)
            comando = texto.split(",", 1)[1].strip(" .") if (tipo == "ativacao" and "," in texto) else None
            brutos.append({"tipo": tipo, "palavra": palavra or "", "arquivo": arquivo, "snr_db": None,
                           "comando_ref": comando, **_avaliar(detector, comando if tipo == "ativacao" else None, ouvido)})
        saida["modelos"][nome] = {"amostras": brutos, "metricas": _metricas(brutos)}
    return saida


def main() -> int:
    args = C.argumentos(__doc__.splitlines()[0], extra=lambda p: (
        p.add_argument("--modelos", default="pequeno,grande", help="pequeno, grande ou os dois"),
        p.add_argument("--gravacoes", default="", help="pasta com WAVs humanos e roteiro.csv (etapa B)")))
    C.preparar()
    modo = "gravacoes" if args.gravacoes else "sintetico"
    with C.Cronometro() as t:
        dados = gravacoes(args) if args.gravacoes else sintetico(args)
    resultado = {
        "protocolo": "PV-01", "modo": modo,
        "real": ["reconhecedor Vosk e modelos do repositório", "detector de ativação e configurações padrão do SAFRA",
                 "síntese Piper (modo sintético)"] + (["gravações humanas"] if args.gravacoes else []),
        "simulado": [] if args.gravacoes else ["voz humana (substituída por uma voz sintética)", "microfone",
                                               "ruído de ambiente (ruído branco somado ao sinal)"],
        "ambiente": C.ambiente(), "duracao_s": round(t.s, 1), "rapido": args.rapido, **dados}
    caminho = C.gravar("pv01_ativacao", resultado, rotulo=args.rotulo)
    print(f"resultado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
