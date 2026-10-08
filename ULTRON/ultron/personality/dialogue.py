"""Repertório de falas do ULTRON.

Falas curtas, por situação. A escolha evita repetir a mesma frase em sequência.
A lógica do sistema pede uma *situação* (``say("done")``); a personalidade decide a frase.
"""
from __future__ import annotations

import random
import threading

LINES: dict[str, tuple[str, ...]] = {
    "ack": ("Entendido.", "Entendido, senhor.", "Certo."),
    "analyzing": ("Analisando.", "Vou verificar.", "Analisando o contexto."),
    "executing": ("Executando.", "Em execução."),
    "verifying": ("Verificando.", "Verificando o resultado."),
    "inconsistency": ("Há uma inconsistência.", "Detectei uma inconsistência."),
    "correcting": ("Corrigindo.", "Estou corrigindo."),
    "done": ("Concluído.", "Resultado confirmado.", "A análise foi concluída."),
    "done_unverified": ("Executado, mas não consegui confirmar o resultado.",),
    "failed_retry": ("Não funcionou. Tentando outra abordagem.", "Falhou. Vou testar outra abordagem."),
    "alternative": ("Encontrei uma alternativa.",),
    "testing": ("Vou testar.",),
    "deep": ("Isso exige uma análise mais profunda.",),
    "not_a_problem": ("Isso não representa um problema.",),
    "unexpected": ("Interessante. O resultado não corresponde ao esperado.",),
    "failed": ("Não foi possível concluir.", "A tarefa falhou."),
    "cancelled": ("Cancelado.", "Operação cancelada."),
    "auth_request": ("Ação sensível: {action}. Autoriza?", "Isto requer autorização: {action}. Confirma?"),
    "auth_denied": ("Não autorizado. Nada foi executado.",),
    "auth_expired": ("Sem autorização. A ação foi descartada.",),
    "ambiguous": ("Há mais de uma interpretação. {question}",),
    "unavailable": ("{module} indisponível.", "{module} não está disponível neste momento."),
    "model_missing": ("O modelo {model} não está instalado.",),
    "wake": ("Sim.", "Estou ouvindo.", "Prossiga."),
    "online": ("ULTRON online.", "Sistemas online."),
    "shutdown": ("Encerrando.",),
    "busy": ("Ainda estou processando a tarefa anterior.",),
    "imagining": ("Construindo o conceito.", "Imaginando."),
    "dream_found": ("Encontrei uma nova conexão.",),
    "nothing": ("Não há nada a fazer.",),
}


class Dialogue:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self._last: dict[str, str] = {}
        self._lock = threading.Lock()

    def say(self, situation: str, **fields: str) -> str:
        options = LINES.get(situation)
        if not options:
            raise KeyError(f"situação de diálogo desconhecida: {situation}")
        with self._lock:
            pool = [o for o in options if o != self._last.get(situation)] or list(options)
            line = self._rng.choice(pool)
            self._last[situation] = line
        try:
            return line.format(**fields)
        except KeyError:
            return line


_default = Dialogue()


def say(situation: str, **fields: str) -> str:
    return _default.say(situation, **fields)
