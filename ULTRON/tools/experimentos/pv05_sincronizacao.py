"""PV-05 — Sincronização labial (lado do cálculo: a trilha da boca contra o áudio real).

Para cada frase, o SAFRA sintetiza a fala como no uso real (prosódia + Piper) e monta a trilha da boca
(``LipSyncTrack``). Mede:

* **método** usado pela trilha (alinhamento do modelo, fonemas sobre o áudio ou espectro);
* **defasagem forma × áudio** — atraso (em ms) que maximiza a correlação entre a abertura de boca PREVISTA PELOS
  VISEMAS (sem a energia) e o envelope de energia do áudio. Como as vogais concentram energia, uma trilha bem
  alinhada tem defasagem perto de zero. Resolução: 10 ms (um quadro);
* **fechamento no silêncio** — fração dos quadros silenciosos (energia < 5 %) em que a boca efetiva está fechada;
* **início das palavras × referência independente** — o Vosk (modelo grande, com tempos por palavra) reconhece o
  mesmo áudio; quando o número de palavras coincide, compara o início de cada palavra na trilha (base da
  legenda) com o início dado pelo reconhecedor.

O que este protocolo NÃO mede: o atraso de apresentação na tela (áudio no alto-falante × quadro desenhado),
que depende da placa de som, do monitor e do navegador embutido. Isso é a etapa B (PV-05B), feita no
computador de referência com gravação de vídeo — ver docs/research/PROTOCOLOS_DE_VALIDACAO.md.

Uso:  python tools/experimentos/pv05_sincronizacao.py [--rapido] [--rotulo NOME]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum as C  # noqa: E402

FRASES = (
    "São dezenove horas e trinta minutos.",
    "Anotei a sua ideia sobre a horta vertical.",
    "Abri o bloco de notas, senhor.",
    "Você tem três compromissos amanhã: reunião às nove, dentista às catorze e treino às dezoito.",
    "Não encontrei nenhum lembrete com esse nome.",
    "O sistema está estável: processador em doze por cento e memória em quarenta por cento.",
    "Preciso da sua autorização para apagar este arquivo.",
    "A tarefa de diagnóstico terminou sem falhas.",
    "Bom dia. A previsão é de chuva no fim da tarde.",
    "Protocolo concluído. Todas as verificações passaram.",
    "Isso eu não sei; não há registro na memória.",
    "Vou abrir a TARDIS para mostrar as tarefas em andamento.",
)


def _palavras_vosk(stt, pcm: bytes) -> list[dict]:
    from ultron.voice.calibrate import CHUNK
    stt.recognizer = stt._new()          # reconhecedor novo: os tempos por palavra recomeçam do zero nesta frase
    palavras: list[dict] = []
    for inicio in range(0, len(pcm), CHUNK * 2):
        final, _ = stt.accept(pcm[inicio:inicio + CHUNK * 2])
        if final:
            palavras += stt.last_words
    stt.finish()
    palavras += stt.last_words
    return [w for w in palavras if "start" in w]


def medir_frase(texto: str, piper, stt, prosody_style) -> dict:
    import numpy as np
    from ultron.voice import dsp, prosody
    from ultron.voice.lipsync import FRAME_S, LipSyncTrack
    audio, rate, segmentos = piper.synthesize_plan(prosody.plan(texto, prosody_style))
    trilha = LipSyncTrack(audio, rate, segmentos)
    energia = trilha.energy.astype(float)
    forma = trilha.params[:, 0].astype(float)                    # abertura prevista pelos visemas
    efetiva = forma * np.clip(energia, 0.0, 1.0)                 # o que a boca mostra (forma × energia real)

    def defasagem(a, b, maximo=30):
        a = (a - a.mean()) / (a.std() or 1.0)
        b = (b - b.mean()) / (b.std() or 1.0)
        melhor, corr = 0, -2.0
        for k in range(-maximo, maximo + 1):
            x, y = (a[k:], b[:len(b) - k]) if k >= 0 else (a[:k], b[-k:])
            if len(x) < 10:
                continue
            c = float(np.mean(x * y))
            if c > corr:
                melhor, corr = k, c
        return melhor, corr

    lag, corr = defasagem(forma, energia)
    silencio = energia < 0.05
    fechada = float(np.mean(efetiva[silencio] < 0.05)) if silencio.any() else None
    # início das palavras: trilha × reconhecedor
    inicios_trilha = [int(np.argmax(trilha.word == k)) * FRAME_S for k in range(trilha.total_words)
                      if (trilha.word == k).any()]
    pcm = dsp.to_int16(dsp.resample(audio, 16000 / rate))
    palavras = _palavras_vosk(stt, pcm) if stt is not None else []
    erros = None
    if palavras and len(palavras) == len(inicios_trilha):
        erros = [round(abs(t - float(w["start"])) * 1000, 1) for t, w in zip(inicios_trilha, palavras)]
    return {"frase": texto, "metodo": trilha.method, "duracao_s": round(trilha.duration, 2),
            "defasagem_forma_ms": lag * FRAME_S * 1000, "correlacao_forma_energia": round(corr, 3),
            "fechada_no_silencio": None if fechada is None else round(fechada, 4),
            "quadros_silenciosos": int(silencio.sum()), "palavras_trilha": len(inicios_trilha),
            "palavras_reconhecidas": len(palavras), "erro_inicio_palavra_ms": erros,
            "reconhecido": " ".join(str(w.get("word", "")) for w in palavras)}


def main() -> int:
    args = C.argumentos(__doc__.splitlines()[0])
    C.preparar()
    from ultron.voice.prosody import JARVIS_STYLE
    from ultron.voice.stt import LARGE, VoskSTT
    from ultron.voice.tts import PiperSynth
    piper = PiperSynth(str(C.RAIZ / "assets" / "voices" / "pt_BR-faber-medium.onnx"))
    grande = C.RAIZ / "assets" / "stt" / LARGE
    stt = VoskSTT(grande) if grande.is_dir() else None
    frases = FRASES[:3] if args.rapido else FRASES
    repeticoes = 1 if args.rapido else 3                       # síntese estocástica: cada frase 3×
    with C.Cronometro() as t:
        brutos = [dict(medir_frase(f, piper, stt, JARVIS_STYLE), rep=r) for r in range(repeticoes) for f in frases]
    erros = [e for b in brutos for e in (b["erro_inicio_palavra_ms"] or [])]
    metricas = {
        "metodos": {m: sum(b["metodo"] == m for b in brutos) for m in sorted({b["metodo"] for b in brutos})},
        "defasagem_forma_ms": C.resumo([b["defasagem_forma_ms"] for b in brutos]),
        "correlacao_forma_energia": C.resumo([b["correlacao_forma_energia"] for b in brutos]),
        "fechada_no_silencio": C.resumo([b["fechada_no_silencio"] for b in brutos if b["fechada_no_silencio"] is not None]),
        "frases_com_palavras_comparaveis": C.proporcao(sum(b["erro_inicio_palavra_ms"] is not None for b in brutos),
                                                       len(brutos)),
        "erro_inicio_palavra_ms": C.resumo(erros),
    }
    resultado = {"protocolo": "PV-05", "etapa": "A (cálculo da trilha)",
                 "real": ["síntese Piper com a prosódia do SAFRA", "LipSyncTrack", "Vosk grande como referência"],
                 "simulado": [], "nao_medido": ["atraso de apresentação áudio × tela (etapa B, hardware real)"],
                 "ambiente": C.ambiente(), "duracao_s": round(t.s, 1), "rapido": args.rapido,
                 "metricas": metricas, "amostras": brutos}
    caminho = C.gravar("pv05_sincronizacao", resultado, rotulo=args.rotulo)
    print(json.dumps(metricas, ensure_ascii=False)[:900])
    print(f"resultado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
