"""Repertório de falas do JARVIS.

Falas curtas, por situação. A escolha evita repetir a mesma frase em sequência.
A lógica do sistema pede uma *situação* (``say("done")``); a personalidade decide a frase.
"""
from __future__ import annotations

import random
import threading

LINES: dict[str, tuple[str, ...]] = {
    "ack": ("Entendido.", "Certo, senhor.", "Às suas ordens."),
    "analyzing": ("Analisando.", "Um momento, estou verificando.", "Verificando o contexto."),
    "executing": ("Executando.", "Em andamento."),
    "verifying": ("Verificando o resultado.", "Conferindo."),
    "inconsistency": ("Há uma inconsistência.", "Algo não confere."),
    "correcting": ("Corrigindo.", "Ajustando a abordagem."),
    "done": ("Concluído.", "Feito e verificado.", "Pronto, senhor."),
    "done_unverified": ("Executado, mas não consegui confirmar o resultado.",),
    "failed_retry": ("Não funcionou. Vou tentar outra abordagem.", "Falhou. Testando uma alternativa."),
    "alternative": ("Encontrei uma alternativa.",),
    "testing": ("Vou testar.",),
    "deep": ("Isso pede uma análise mais cuidadosa.",),
    "not_a_problem": ("Isso não representa um problema.",),
    "unexpected": ("Curioso. O resultado não é o esperado.",),
    "failed": ("Não foi possível concluir.", "A tarefa falhou."),
    "cancelled": ("Cancelado.", "Operação cancelada."),
    "auth_request": ("Ação sensível: {action}. Autoriza?", "Isto requer sua autorização: {action}. Prossigo?"),
    "auth_denied": ("Não autorizado. Nada foi executado.",),
    "auth_expired": ("Sem autorização. A ação foi descartada.",),
    "ambiguous": ("Há mais de uma interpretação. {question}",),
    "unavailable": ("{module} indisponível.", "{module} não está disponível no momento."),
    "model_missing": ("O modelo {model} não está instalado.",),
    "wake": ("Sim, senhor?", "Pois não?", "Estou ouvindo."),
    "online": ("JARVIS online.", "Sistemas online, senhor."),
    "shutdown": ("Encerrando.", "Até breve, senhor."),
    "busy": ("Ainda estou concluindo a tarefa anterior.",),
    "imagining": ("Construindo o conceito.", "Imaginando."),
    "dream_found": ("Encontrei uma conexão interessante.",),
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
