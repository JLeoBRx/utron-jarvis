"""SECOND BRAIN — memória pessoal persistente e pesquisável do ULTRON.

* ``service``: camada única de serviços (interface, voz e texto usam a mesma);
* ``store``: SQLite do ULTRON (migração versionada), busca FTS5 sem acentos;
* ``reminders``: lembretes persistentes com fuso, recorrência, avisos antecipados e
  deduplicação após reinício;
* ``capture``: frases → registros (explícito = confirmado; automático = inferido);
* ``queries``: perguntas respondidas apenas com dados salvos;
* ``parsing``/``timeutil``: datas em português e fuso horário/horário de verão.
"""
from .capture import Capture, CaptureResult, confirmation_text
from .models import KINDS, Record, Reminder
from .queries import Answer, answer
from .reminders import ReminderScheduler
from .service import NeedsClarification, SecondBrainError, SecondBrainService, describe_record

__all__ = ["Answer", "Capture", "CaptureResult", "KINDS", "NeedsClarification", "Record", "Reminder",
           "ReminderScheduler", "SecondBrainError", "SecondBrainService", "answer", "confirmation_text",
           "describe_record"]
