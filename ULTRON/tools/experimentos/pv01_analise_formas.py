"""PV-01 (análise exploratória) — e se uma confusão medida virasse forma fraca da palavra de ativação?

Reaproveita as TRANSCRIÇÕES já gravadas por ``pv01_ativacao.py`` (nenhum reconhecimento novo) e reavalia a
ativação com formas fracas extras (ex.: "faca", a forma em que o Vosk grande ouviu o "Safra" sintetizado).
Aproximação declarada: uma forma fraca só ativa seguida de um comando RECONHECIDO; aqui conta como comando
qualquer texto depois da forma (limite superior da taxa de ativação e das ativações indevidas).

ATENÇÃO: é análise exploratória sobre UMA voz sintética. Adotar uma forma por causa dela seria ajustar o
sistema ao teste; a decisão depende da calibração com a voz do usuário (protocolo PV-01, etapa B).

Uso:  python tools/experimentos/pv01_analise_formas.py docs/research/resultados/pv01_ativacao_<rotulo>.json faca
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum as C  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    C.preparar()
    from ultron.config.settings import Settings
    from ultron.voice.wake_word import WakeWordDetector
    origem = Path(sys.argv[1])
    extras = tuple(sys.argv[2:])
    dados = json.loads(origem.read_text(encoding="utf-8"))
    s = Settings()
    saida = {"protocolo": "PV-01 (análise exploratória)", "origem": origem.name, "formas_fracas_extras": extras,
             "aproximacao": "forma fraca conta como ativação quando há qualquer texto depois dela", "modelos": {}}
    for variante, fracas in (("padrao", ()), ("com_extras", extras)):
        det = WakeWordDetector(tuple(s.wake_words), tuple(s.wake_variants), weak=tuple(s.wake_weak_variants) + fracas,
                               names=tuple(s.wake_names))
        for modelo, m in dados["modelos"].items():
            def ativa(texto: str) -> bool:
                r = det.detect(texto)
                return bool(r.detected and (r.strength == "strong" or r.command))
            res = saida["modelos"].setdefault(modelo, {})
            for palavra in ("Safra", "Jarvis"):
                a = [b for b in m["amostras"] if b["tipo"] == "ativacao" and b["palavra"] == palavra]
                res[f"{variante}_ativacao_{palavra.lower()}"] = C.proporcao(sum(ativa(b["transcricao"]) for b in a), len(a))
            neg = [b for b in m["amostras"] if b["tipo"] == "negativa"]
            res[f"{variante}_ativacao_indevida"] = C.proporcao(sum(ativa(b["transcricao"]) for b in neg), len(neg))
            res[f"{variante}_indevidas_exemplos"] = [b["transcricao"] for b in neg if ativa(b["transcricao"])][:10]
    caminho = C.gravar("pv01_analise_formas", saida, rotulo=origem.stem.replace("pv01_ativacao_", ""))
    print(json.dumps(saida["modelos"], ensure_ascii=False, indent=1)[:2000])
    print(f"resultado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
