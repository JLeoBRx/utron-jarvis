"""HISTÓRICO DE ATIVIDADES — um só registro do que o JARVIS recebeu, decidiu e fez.

Cada atividade segue o protocolo comum do JARVIS ULTIMATE (o mesmo que a TARDIS e o Noctário usam):
``id``, ``kind`` (tipo), ``origin`` (origem), ``input`` (entrada), ``state`` (estado), ``result``
(resultado), ``error`` (erros), ``started_at``/``finished_at``/``seconds`` (tempo) e ``parent``/``ref``
(o pedido que originou uma ação; a ação, a consulta ou o comando a que o registro se refere).

Quem escreve:

* o núcleo — cada pedido (voz, texto, sugestão aceita) e a resposta que encerrou o pedido;
* o ExecutionEngine — cada ação, de forma síncrona na thread que a executa (o pedido em curso nessa
  thread vira o ``parent``): aguardando confirmação → executando → concluído/falhou/negado...;
* os eventos do barramento — verificação das ações, lembretes, falhas de componentes e de modelo;
* TARDIS e Noctário (fases seguintes) — ``begin``/``update`` com o próprio ciclo.

Nada é inventado: um registro só muda de estado quando o módulo responsável informa o resultado.
Privacidade: textos que parecem segredo são redigidos antes de gravar; com ``activity_history``
desligado nada é gravado. Retenção: ``activity_keep`` registros (os mais antigos saem primeiro).
A tabela fica no mesmo banco SQLite do JARVIS (migração v4); não há banco paralelo.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from ..memory.store import looks_secret
from .events import EventType

log = logging.getLogger("ultron.activity")

KINDS = {"pedido": "Pedido", "acao": "Ação", "aviso": "Aviso", "lembrete": "Lembrete", "erro": "Erro",
         "sistema": "Sistema", "tardis": "TARDIS", "noctario": "Noctário"}
STATES = {"recebido": "recebido", "executando": "executando", "aguardando_confirmacao": "aguardando confirmação",
          "concluido": "concluído", "verificado": "verificado", "nao_confirmado": "não confirmado",
          "pergunta": "pediu esclarecimento", "falhou": "falhou", "negado": "negado", "cancelado": "cancelado",
          "recusado": "recusado", "aviso": "aviso"}
FINAL_STATES = frozenset({"concluido", "verificado", "nao_confirmado", "pergunta", "falhou", "negado",
                          "cancelado", "recusado", "aviso"})
ORIGINS = {"voice": "voz", "text": "texto", "hud": "interface", "user": "usuário", "plan": "plano",
           "agent": "agente", "recovery": "recuperação", "proactive": "proatividade", "automation": "automação",
           "reminders": "lembretes", "core": "JARVIS", "system": "sistema", "tardis": "TARDIS",
           "noctario": "Noctário"}
_EXECUTION_STATES = {"executed": "concluido", "skipped": "concluido", "failed": "falhou", "refused": "recusado",
                     "denied": "negado", "cancelled": "cancelado", "unavailable": "falhou"}
_VERIFICATION_STATES = {"VERIFIED": "verificado", "UNCONFIRMED": "nao_confirmado", "FAILED": "falhou"}
TRIM_EVERY = 100


def _clean(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if looks_secret(text):
        return "[redigido: possível dado sensível]"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _safe_detail(detail: dict | None) -> dict:
    out: dict[str, Any] = {}
    for key, value in list((detail or {}).items())[:30]:
        if isinstance(value, (int, float, bool)) or value is None:
            out[str(key)] = value
        else:
            out[str(key)] = _clean(value if isinstance(value, str) else json.dumps(value, default=str,
                                                                                   ensure_ascii=False), 400)
    return out


class ActivityLog:
    def __init__(self, db, *, bus=None, settings_getter: Callable[[], Any] | None = None,
                 clock: Callable[[], float] = time.time):
        self._db = db
        self._bus = bus
        self._settings = settings_getter or (lambda: None)
        self._clock = clock
        self._lock = threading.RLock()
        self._local = threading.local()
        self._actions: dict[int, str] = {}           # id da ação → id da atividade (para a verificação)
        self._subs: list = []
        self._writes = 0

    # ------------------------------------------------------------ configuração e ciclo
    def enabled(self) -> bool:
        settings = self._settings()
        return bool(getattr(settings, "activity_history", True)) if settings is not None else True

    def _keep(self) -> int:
        return int(getattr(self._settings(), "activity_keep", 5000) or 5000)

    def attach(self) -> None:
        """Assina os eventos que o histórico registra (verificações, lembretes, falhas)."""
        if self._bus is None or self._subs:
            return
        self._subs = [
            self._bus.subscribe((EventType.VERIFICATION_SUCCESS, EventType.VERIFICATION_FAILED,
                                 EventType.VERIFICATION_UNCONFIRMED), self._on_verification, name="activity.verify"),
            self._bus.subscribe(EventType.REMINDER_DUE, self._on_reminder, name="activity.reminder"),
            self._bus.subscribe((EventType.COMPONENT_FAILED, EventType.MODEL_UNAVAILABLE, EventType.ERROR_DETECTED),
                                self._on_failure, name="activity.failure"),
            self._bus.subscribe((EventType.SYSTEM_READY, EventType.SHUTDOWN_REQUESTED), self._on_system,
                                name="activity.system"),
        ]

    def detach(self) -> None:
        for sub in self._subs:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        self._subs = []

    # ------------------------------------------------------------ escopo do pedido (por thread)
    @contextmanager
    def scope(self, activity_id: str) -> Iterator[None]:
        """Durante um pedido, as ações executadas NESTA thread ficam ligadas a ele."""
        previous = getattr(self._local, "parent", "")
        self._local.parent = activity_id or ""
        try:
            yield
        finally:
            self._local.parent = previous

    def current(self) -> str:
        return getattr(self._local, "parent", "")

    # ------------------------------------------------------------ escrita
    def begin(self, kind: str, title: str, *, origin: str, input: str = "", parent: str = "", ref: str = "",
              state: str = "recebido", detail: dict | None = None, result: str = "", error: str = "") -> str:
        if not self.enabled():
            return ""
        now = self._clock()
        activity_id = uuid.uuid4().hex[:16]
        final = now if state in FINAL_STATES else None
        row = (activity_id, kind if kind in KINDS else "sistema", _clean(ORIGINS.get(origin, origin), 40),
               _clean(title, 200) or KINDS.get(kind, kind), _clean(input, 1000), state, _clean(result, 1000),
               _clean(error, 600), parent or "", _clean(ref, 80), json.dumps(_safe_detail(detail), ensure_ascii=False),
               now, now, final)
        try:
            self._db.execute("INSERT INTO activity(id,kind,origin,title,input,state,result,error,parent,ref,detail,"
                             "started_at,updated_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
        except Exception as exc:                 # o histórico nunca derruba quem o chama
            log.warning("histórico de atividades indisponível: %s", exc)
            return ""
        self._after_write(activity_id)
        return activity_id

    def update(self, activity_id: str, *, state: str | None = None, result: str | None = None,
               error: str | None = None, detail: dict | None = None, title: str | None = None) -> None:
        if not activity_id:
            return
        now = self._clock()
        sets, params = ["updated_at=?"], [now]
        if state is not None:
            sets.append("state=?")
            params.append(state)
            if state in FINAL_STATES:
                sets.append("finished_at=COALESCE(finished_at, ?)")
                params.append(now)
        if result is not None:
            sets.append("result=?")
            params.append(_clean(result, 1000))
        if error is not None:
            sets.append("error=?")
            params.append(_clean(error, 600))
        if title is not None:
            sets.append("title=?")
            params.append(_clean(title, 200))
        try:
            with self._lock:
                if detail:
                    row = self._db.one("SELECT detail FROM activity WHERE id=?", (activity_id,))
                    merged = json.loads(row["detail"]) if row else {}
                    merged.update(_safe_detail(detail))
                    sets.append("detail=?")
                    params.append(json.dumps(merged, ensure_ascii=False))
                self._db.execute(f"UPDATE activity SET {', '.join(sets)} WHERE id=?", (*params, activity_id))
        except Exception as exc:
            log.warning("histórico de atividades: atualização falhou: %s", exc)
            return
        self._after_write(activity_id, trim=False)

    def record(self, kind: str, title: str, *, origin: str, state: str = "concluido", input: str = "",
               result: str = "", error: str = "", parent: str = "", ref: str = "", detail: dict | None = None) -> str:
        """Registro de uma vez só (o fato já terminou)."""
        return self.begin(kind, title, origin=origin, input=input, parent=parent, ref=ref, state=state,
                          detail=detail, result=result, error=error)

    def _after_write(self, activity_id: str, *, trim: bool = True) -> None:
        with self._lock:
            self._writes += 1
            due = trim and self._writes % TRIM_EVERY == 0
        if due:
            self.trim()
        if self._bus is not None:
            item = self.get(activity_id)
            if item is not None:
                self._bus.publish(EventType.ACTIVITY_UPDATED, item, source="activity")

    def trim(self) -> int:
        try:
            cursor = self._db.execute("DELETE FROM activity WHERE id IN (SELECT id FROM activity ORDER BY started_at "
                                      "DESC LIMIT -1 OFFSET ?)", (self._keep(),))
            return max(0, cursor.rowcount or 0)
        except Exception:
            return 0

    def clear(self, *, before: float | None = None) -> int:
        """Apaga o histórico (todo ou anterior a ``before``). A interface pede confirmação antes."""
        if before is None:
            cursor = self._db.execute("DELETE FROM activity")
        else:
            cursor = self._db.execute("DELETE FROM activity WHERE started_at < ?", (float(before),))
        with self._lock:
            self._actions.clear()
        return max(0, cursor.rowcount or 0)

    # ------------------------------------------------------------ leitura
    @staticmethod
    def _row(row) -> dict:
        item = dict(row)
        try:
            item["detail"] = json.loads(item.get("detail") or "{}")
        except ValueError:
            item["detail"] = {}
        finished = item.get("finished_at")
        item["seconds"] = round(finished - item["started_at"], 3) if finished else None
        item["kind_label"] = KINDS.get(item["kind"], item["kind"])
        item["state_label"] = STATES.get(item["state"], item["state"])
        item["final"] = item["state"] in FINAL_STATES
        return item

    def get(self, activity_id: str) -> dict | None:
        try:
            row = self._db.one("SELECT * FROM activity WHERE id=?", (activity_id,))
        except Exception:
            return None
        return self._row(row) if row else None

    def recent(self, limit: int = 200, *, kinds: tuple | list | None = None, states: tuple | list | None = None,
               search: str = "", parent: str | None = None, since: float | None = None) -> list[dict]:
        where, params = [], []
        if kinds:
            where.append(f"kind IN ({','.join('?' * len(kinds))})")
            params += list(kinds)
        if states:
            where.append(f"state IN ({','.join('?' * len(states))})")
            params += list(states)
        if search:
            where.append("(title LIKE ? OR input LIKE ? OR result LIKE ? OR error LIKE ?)")
            params += [f"%{search}%"] * 4
        if parent is not None:
            where.append("parent=?")
            params.append(parent)
        if since is not None:
            where.append("started_at >= ?")
            params.append(float(since))
        sql = "SELECT * FROM activity" + (f" WHERE {' AND '.join(where)}" if where else "")
        sql += " ORDER BY started_at DESC, rowid DESC LIMIT ?"
        try:
            rows = self._db.query(sql, (*params, max(1, min(5000, int(limit)))))
        except Exception:
            return []
        return [self._row(r) for r in rows]

    def children(self, activity_id: str) -> list[dict]:
        return list(reversed(self.recent(500, parent=activity_id)))

    def count(self) -> int:
        try:
            row = self._db.one("SELECT COUNT(*) FROM activity")
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def summary(self, since: float | None = None) -> dict:
        """Contagem por estado (diagnóstico e tela de atividades)."""
        try:
            rows = self._db.query("SELECT state, COUNT(*) AS n FROM activity WHERE started_at >= ? GROUP BY state",
                                  (float(since or 0.0),))
        except Exception:
            return {}
        return {r["state"]: int(r["n"]) for r in rows}

    # ------------------------------------------------------------ pedidos (núcleo)
    def finish_request(self, activity_id: str, response: Any, *, cancelled: bool = False) -> None:
        """Encerra o pedido com a resposta que o JARVIS deu (``Response`` do orquestrador)."""
        if not activity_id:
            return
        kind = getattr(response, "kind", "answer")
        success = getattr(response, "success", None)
        verified = getattr(response, "verified", None)
        text = getattr(response, "text", "")
        if cancelled:
            state = "cancelado"
        elif kind == "question":
            state = "pergunta"
        elif kind == "refusal":
            state = "recusado"
        elif kind == "error" or success is False:
            state = "falhou"
        elif verified is True:
            state = "verificado"
        elif verified is False and success:
            state = "nao_confirmado"
        else:
            state = "concluido"
        self.update(activity_id, state=state, result=text if state != "falhou" else None,
                    error=text if state == "falhou" else None, detail={"response": kind})

    # ------------------------------------------------------------ ações (ExecutionEngine, mesma thread)
    def action_waiting(self, action, description: str, *, risk: str, permission: str = "",
                       category: str = "") -> str:
        activity_id = self.begin("acao", description, origin=action.origin, parent=self.current(),
                                 ref=f"acao:{action.skill}", state="aguardando_confirmacao",
                                 detail={"skill": action.skill, "risk": risk, "permission": permission,
                                         "sensitive": category})
        if activity_id:
            with self._lock:
                self._actions[action.id] = activity_id
        return activity_id

    def action_record(self, action_id: str) -> str:
        """Id do registro de uma ação em andamento ("" se não há)."""
        with self._lock:
            return self._actions.get(action_id, "")

    def action_started(self, action, description: str, *, risk: str) -> str:
        with self._lock:
            activity_id = self._actions.get(action.id, "")
        if activity_id:
            self.update(activity_id, state="executando")
            return activity_id
        activity_id = self.begin("acao", description, origin=action.origin, parent=self.current(),
                                 ref=f"acao:{action.skill}", state="executando",
                                 detail={"skill": action.skill, "risk": risk})
        if activity_id:
            with self._lock:
                self._actions[action.id] = activity_id
        return activity_id

    def action_finished(self, record) -> None:
        action = record.action
        state = _EXECUTION_STATES.get(record.status, "falhou")
        result = record.result
        detail = {"status": record.status, "error_kind": result.error_kind, "seconds": result.seconds}
        if record.authorization:
            detail["authorization"] = record.authorization.get("status", "")
            detail["authorized_by"] = record.authorization.get("resolved_by", "")
        with self._lock:
            activity_id = self._actions.get(action.id, "")
            if len(self._actions) > 500:
                for key in list(self._actions)[:250]:
                    del self._actions[key]
        if not activity_id:                      # recusada/indisponível antes de começar
            activity_id = self.begin("acao", action.description or action.skill, origin=action.origin,
                                     parent=self.current(), ref=f"acao:{action.skill}", state=state,
                                     detail={"skill": action.skill, **detail}, result=result.result,
                                     error=result.error)
            if activity_id:
                with self._lock:
                    self._actions[action.id] = activity_id
            return
        self.update(activity_id, state=state, result=result.result or None, error=result.error or None,
                    detail=detail)

    # ------------------------------------------------------------ eventos do barramento
    def _on_verification(self, event) -> None:
        with self._lock:
            activity_id = self._actions.get(event.get("action_id"), "")
        if not activity_id:
            return
        current = self.get(activity_id)
        if current is None or current["state"] not in ("concluido", "executando"):
            return                               # negada/recusada/falhou: a verificação não muda o desfecho
        state = _VERIFICATION_STATES.get(str(event.get("status")), "nao_confirmado")
        self.update(activity_id, state=state, detail={"verification": event.get("status"),
                                                      "verification_reason": event.get("reason", "")},
                    error=event.get("reason") if state == "falhou" else None)

    def _on_reminder(self, event) -> None:
        self.record("lembrete", str(event.get("notice") or event.get("title") or "Lembrete"), origin="reminders",
                    state="aviso", result=str(event.get("when_text") or ""),
                    detail={"record_id": event.get("record_id"), "silent": event.get("silent"),
                            "late": event.get("late")})

    def _on_failure(self, event) -> None:
        if event.type is EventType.ERROR_DETECTED and event.get("action_id") is not None:
            return                               # já está no registro da própria ação
        if event.type is EventType.COMPONENT_FAILED:
            title = f"Componente {event.get('component', '?')} falhou"
        elif event.type is EventType.MODEL_UNAVAILABLE:
            fallback = event.get("fallback")
            title = f"Modelo indisponível{f' — usando {fallback}' if fallback else ''}"
        else:
            title = f"Erro em {event.get('skill') or event.source or 'componente'}"
        self.record("erro", title, origin=event.source or "system", state="falhou",
                    error=str(event.get("error") or event.get("reason") or ""))

    def _on_system(self, event) -> None:
        if event.type is EventType.SYSTEM_READY:
            failed = list(event.get("failed") or [])
            seconds = float(event.get("seconds") or 0.0)
            self.record("sistema", "JARVIS pronto", origin="system", state="concluido" if not failed else "aviso",
                        result=f"inicialização em {seconds:.1f} s" + (f"; com falha: {', '.join(map(str, failed))}"
                                                                     if failed else ""))
        else:
            self.record("sistema", "Encerramento do JARVIS solicitado", origin=str(event.get("by") or "user"))
