"""Motor da TARDIS: fila própria, prazos, cancelamento, eventos, persistência e o modo do rotor.

* Uma thread própria (``ultron-tardis``) consome a fila em ordem; cada análise roda numa thread auxiliar
  com o prazo do tipo — se travar, a tarefa falha por TIMEOUT e a fila segue (a thread é avisada para
  parar na próxima verificação). Cancelar uma tarefa na fila a remove; em execução, encerra na hora.
* A cadeia de delegação é verificada na entrada (``check_chain``): ciclo ou saltos demais → REJECTED.
* Cada tarefa é gravada no banco do JARVIS e aparece no histórico de atividades (tipo "tardis").
* Eventos: TARDIS_TASK_QUEUED/STARTED/FINISHED/FAILED/REJECTED/CANCELLED e TARDIS_STATE (modo do rotor).

O modo do rotor reflete o estado REAL: ``jarvis`` (tarefa pedida pelo JARVIS em execução),
``processando`` (outra tarefa em execução ou na fila), ``operacao`` (backup, exportação ou escrita que o
JARVIS está executando), ``falha`` (uma tarefa falhou há menos de ``FAULT_WINDOW`` s) e ``repouso``.
"""
from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from ..core.events import EventType
from .analyzers import Run, TardisContext, registry
from .protocol import KINDS, STATE_LABELS, TaskCancelled, TaskEnvelope, TaskFailed, TaskResult, check_chain
from .store import TardisStore

log = logging.getLogger("ultron.tardis")

FAULT_WINDOW = 8.0                    # segundos com o anel de falha aceso depois de uma tarefa falhar
GRACE = 2.0                           # tolerância além do prazo antes de abandonar uma análise travada
RECENT = 40
MODE_LABELS = {"repouso": "repouso", "processando": "processando", "operacao": "operação",
               "jarvis": "consulta do JARVIS", "falha": "falha"}
ACTIVITY_STATES = {"QUEUED": "recebido", "RUNNING": "executando", "DONE": "concluido", "FAILED": "falhou",
                   "REJECTED": "recusado", "CANCELLED": "cancelado"}
ACTIVITY_ORIGINS = {"jarvis": "core", "usuario": "user", "tardis": "tardis", "agendador": "automation"}
ORIGIN_LABELS = {"jarvis": "JARVIS", "usuario": "usuário", "tardis": "TARDIS", "agendador": "agendador"}
FINAL_EVENTS = {"DONE": EventType.TARDIS_TASK_FINISHED, "FAILED": EventType.TARDIS_TASK_FAILED,
                "REJECTED": EventType.TARDIS_TASK_REJECTED, "CANCELLED": EventType.TARDIS_TASK_CANCELLED}
# skills que o JARVIS executa e que acendem o modo "operação" no rotor (dados sendo gravados ou exportados)
OPERATION_SKILLS = frozenset({"memory.backup", "secondbrain.export", "network.export", "secondbrain.empty_trash",
                              "activity.clear", "fs.copy", "fs.move", "fs.delete", "fs.write_text", "fs.edit_text",
                              "fs.create_file", "fs.create_folder", "dev.install_dependency", "dev.create_venv"})


def brief(envelope: TaskEnvelope) -> dict[str, Any]:
    """Resumo de uma tarefa para eventos e listas (sem os itens completos do resultado)."""
    result = envelope.result
    spec = KINDS.get(envelope.kind)
    return {"id": envelope.id, "kind": envelope.kind, "kind_label": envelope.label, "origin": envelope.origin,
            "chain": list(envelope.chain), "state": envelope.state,
            "state_label": STATE_LABELS.get(envelope.state, envelope.state), "panel": spec.panel if spec else "",
            "input": _input_text(envelope.input), "summary": result.summary if result else "",
            "actions": len(result.actions) if result else 0, "error": envelope.error,
            "created": envelope.created, "started": envelope.started, "finished": envelope.finished,
            "duration_ms": envelope.duration_ms, "model": envelope.model}


def _input_text(data: dict) -> str:
    for key in ("question", "goal", "text", "search", "project", "run"):
        if data.get(key):
            return " ".join(str(data[key]).split())[:200]
    return ""


class TardisEngine:
    name = "tardis"

    def __init__(self, store: TardisStore, context: TardisContext | None = None, *, bus=None, activity=None,
                 analyzers: dict[str, Callable[[Run, dict], Any]] | None = None):
        self.store = store
        self.ctx = context or TardisContext()
        self.ctx.store = store
        self.ctx.engine = self
        self._bus = bus
        self._activity = activity
        self._analyzers = dict(analyzers) if analyzers is not None else registry()
        self._lock = threading.RLock()
        self._wake = threading.Condition(self._lock)
        self._queue: deque[TaskEnvelope] = deque()
        self._running: TaskEnvelope | None = None
        self._cancels: dict[str, threading.Event] = {}
        self._done: dict[str, threading.Event] = {}
        self._activities: dict[str, str] = {}
        self._parents: dict[str, str] = {}
        self._recent: deque[TaskEnvelope] = deque(maxlen=RECENT)
        self._operations: dict[str, str] = {}
        self._fault_until = 0.0
        self._fault_text = ""
        self._last_signature: tuple = ()
        self._thread: threading.Thread | None = None
        self._stopping = False
        self.started = False
        self.interrupted_on_start = 0

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        if self.started:
            return
        try:
            self.interrupted_on_start = self.store.interrupted()
        except Exception as exc:                        # banco indisponível: a TARDIS sobe e registra
            log.warning("TARDIS: tarefas interrompidas não marcadas: %s", exc)
        self._stopping = False
        self._thread = threading.Thread(target=self._loop, name="ultron-tardis", daemon=True)
        self._thread.start()
        self.started = True
        self._publish_state(force=True)

    def stop(self) -> None:
        if not self.started:
            return
        with self._lock:
            self._stopping = True
            pending = list(self._queue)
            self._queue.clear()
            running = self._running
            self._wake.notify_all()
        for envelope in pending:
            self._final(envelope, "CANCELLED", error={"code": "SHUTDOWN", "message": "o JARVIS foi encerrado"})
        if running is not None:
            running.error = {"code": "SHUTDOWN", "message": "o JARVIS foi encerrado"}
            self._cancels.get(running.id, threading.Event()).set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self.started = False

    def health(self) -> dict:
        if not self.started:
            return {"status": "UNKNOWN", "detail": "TARDIS não iniciada"}
        if self._thread is None or not self._thread.is_alive():
            return {"status": "FAIL", "detail": "a fila da TARDIS parou"}
        state = self.state()
        running = state["running"]
        detail = f"modo {state['mode_label']}; {state['queued']} na fila" + \
                 (f"; executando {running['kind_label']}" if running else "")
        return {"status": "WARN" if state["fault"] else "OK", "detail": detail}

    # ------------------------------------------------------------ entrada
    def submit(self, kind: str, input: dict | None = None, *, origin: str = "usuario",
               chain: list[str] | None = None) -> TaskEnvelope:
        """Enfileira (ou recusa com o motivo). Nunca executa na thread de quem chama."""
        envelope = TaskEnvelope(kind=kind, input=dict(input or {}), origin=origin, chain=list(chain or []))
        reason = check_chain(kind, origin, envelope.chain)
        if not reason and kind not in self._analyzers:
            reason = f"sem analisador para {kind}"
        if not reason and (not self.started or self._stopping):
            reason = "a TARDIS não está em funcionamento"
        parent = self._activity.current() if self._activity is not None else ""
        self._begin_activity(envelope, parent)
        if reason:
            envelope.note(f"recusada: {reason}")
            self._final(envelope, "REJECTED", error={"code": "REJECTED", "message": reason})
            return envelope
        envelope.note(f"na fila (pedida por {ORIGIN_LABELS.get(envelope.origin, envelope.origin)})")
        with self._lock:
            self._cancels[envelope.id] = threading.Event()
            self._done[envelope.id] = threading.Event()
        self._save(envelope)                                # gravada e anunciada ANTES de a thread poder
        self._emit(EventType.TARDIS_TASK_QUEUED, envelope)  # começá-la: os eventos saem sempre em ordem
        with self._lock:
            stopping = self._stopping
            if not stopping:
                self._queue.append(envelope)
                self._wake.notify_all()
        if stopping:                                        # o JARVIS fechou enquanto a tarefa entrava
            self._final(envelope, "CANCELLED", error={"code": "SHUTDOWN", "message": "o JARVIS foi encerrado"})
            return envelope
        self._publish_state()
        return envelope

    def wait(self, task_id: str, timeout: float | None = None) -> TaskEnvelope | None:
        """Espera a tarefa terminar (ou o tempo acabar) e devolve o envelope atual."""
        with self._lock:
            done = self._done.get(task_id)
        if done is not None:
            done.wait(timeout)
        return self.get(task_id)

    def request(self, kind: str, input: dict | None = None, *, origin: str = "jarvis",
                chain: list[str] | None = None, timeout: float | None = None, cancel=None) -> TaskEnvelope:
        """Envia e espera o resultado (usado pela skill ``tardis.consult``). Cancelar quem pediu cancela a
        tarefa; o tempo de espera padrão é o prazo do tipo mais a tolerância."""
        envelope = self.submit(kind, input, origin=origin, chain=chain)
        if envelope.final:
            return envelope
        spec = KINDS[kind]
        limit = time.monotonic() + (timeout if timeout is not None else spec.deadline + GRACE + 30.0)
        asked = False
        while time.monotonic() < limit:
            current = self.wait(envelope.id, 0.1)
            if current is not None and current.final:
                return current
            if not asked and cancel is not None and getattr(cancel, "cancelled", False):
                asked = self.cancel(envelope.id, "cancelado por quem pediu") or True
        current = self.get(envelope.id) or envelope
        if not current.final:
            self.cancel(envelope.id, "tempo de espera esgotado")
            current = self.wait(envelope.id, 3.0) or current
        return current

    def cancel(self, task_id: str, reason: str = "cancelada pelo usuário") -> bool:
        with self._lock:
            queued = next((e for e in self._queue if e.id == task_id), None)
            if queued is not None:
                self._queue.remove(queued)
            running = self._running if self._running is not None and self._running.id == task_id else None
            event = self._cancels.get(task_id)
        if queued is not None:
            queued.note(f"cancelada na fila: {reason}")
            self._final(queued, "CANCELLED", error={"code": "CANCELLED", "message": reason})
            self._publish_state()
            return True
        if running is not None and event is not None:
            running.note(f"cancelamento pedido: {reason}")
            running.error = {"code": "CANCELLED", "message": reason}
            event.set()
            return True
        return False

    def cancel_all(self, reason: str = "cancelada pelo usuário", *, origin: str | None = None) -> int:
        """Cancela a fila e a tarefa em execução (só as de ``origin``, se informada)."""
        with self._lock:
            tasks = list(self._queue) + ([self._running] if self._running is not None else [])
        ids = [e.id for e in tasks if origin is None or e.origin == origin]
        return sum(1 for task_id in ids if self.cancel(task_id, reason))

    # ------------------------------------------------------------ memória de projeto
    def add_note(self, text: str, *, project: str = "", kind: str = "nota", data: dict | None = None,
                 source: str = "usuario") -> int:
        note_id = self.store.add_note(text, project=project, kind=kind, data=data, source=source)
        if self._activity is not None:
            self._activity.record("tardis", f"Memória de projeto: {kind}" + (f" ({project})" if project else ""),
                                  origin=ACTIVITY_ORIGINS.get(source, source), input=text[:300],
                                  result=f"nota #{note_id} gravada", ref=f"nota:{note_id}")
        return note_id

    # ------------------------------------------------------------ operações do JARVIS (modo do rotor)
    def begin_operation(self, key: str, label: str) -> None:
        with self._lock:
            self._operations[key] = label
        self._publish_state()

    def end_operation(self, key: str) -> None:
        with self._lock:
            removed = self._operations.pop(key, None)
        if removed is not None:
            self._publish_state()

    @contextmanager
    def operation(self, label: str) -> Iterator[None]:
        key = uuid.uuid4().hex[:8]
        self.begin_operation(key, label)
        try:
            yield
        finally:
            self.end_operation(key)

    # ------------------------------------------------------------ leitura
    def get(self, task_id: str) -> TaskEnvelope | None:
        with self._lock:
            for envelope in ([self._running] if self._running is not None else []) + list(self._queue) \
                    + list(self._recent):
                if envelope.id == task_id:
                    return envelope
        try:
            return self.store.get(task_id)
        except Exception:
            return None

    def recent(self, limit: int = 20) -> list[TaskEnvelope]:
        """Mais recentes primeiro: em execução, fila e terminadas nesta sessão (memória, sem banco)."""
        with self._lock:
            items = ([self._running] if self._running is not None else []) + list(reversed(self._queue)) \
                    + list(reversed(self._recent))
        seen: set[str] = set()
        unique = [e for e in items if not (e.id in seen or seen.add(e.id))]
        return unique[:limit]

    def history(self, limit: int = 100, *, kind: str | None = None) -> list[TaskEnvelope]:
        return self.store.recent(limit, kind=kind)

    def state(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            running = self._running
            queued = len(self._queue)
            operations = list(self._operations.values())
            fault = now < self._fault_until
            fault_text = self._fault_text if fault else ""
            fault_until = self._fault_until
        if running is not None:
            mode = "jarvis" if running.origin == "jarvis" else "processando"
        elif queued:
            mode = "processando"
        elif operations:
            mode = "operacao"
        elif fault:
            mode = "falha"
        else:
            mode = "repouso"
        return {"mode": mode, "mode_label": MODE_LABELS[mode], "running": brief(running) if running else None,
                "queued": queued, "operations": operations, "fault": fault, "fault_text": fault_text,
                "fault_until": fault_until, "started": self.started}

    def snapshot(self) -> dict[str, Any]:
        state = self.state()
        hour_ago = time.time() - 3600
        with self._lock:
            recent = list(self._recent)
            queue = [brief(e) for e in self._queue]
        state.update(queue=queue, recent=[brief(e) for e in reversed(recent)][:20],
                     failed_recent=sum(1 for e in recent if e.state == "FAILED" and (e.finished or 0) >= hour_ago),
                     done_recent=sum(1 for e in recent if e.state == "DONE" and (e.finished or 0) >= hour_ago))
        return state

    # ------------------------------------------------------------ execução
    def _loop(self) -> None:
        while True:
            with self._lock:
                while not self._queue and not self._stopping:
                    self._wake.wait(1.0)
                if self._stopping:
                    return
                envelope = self._queue.popleft()
                self._running = envelope
            try:
                self._execute(envelope)
            except Exception:                               # a fila nunca para por causa de uma tarefa
                log.exception("TARDIS: falha inesperada ao executar %s", envelope.id)
                if not envelope.final:
                    self._final(envelope, "FAILED", error={"code": "INTERNAL", "message": "falha interna do motor"})
            finally:
                with self._lock:
                    self._running = None
                self._publish_state()

    def _execute(self, envelope: TaskEnvelope) -> None:
        spec = KINDS[envelope.kind]
        cancel = self._cancels.setdefault(envelope.id, threading.Event())
        envelope.state = "RUNNING"
        envelope.started = time.time()
        started = time.monotonic()
        deadline = started + spec.deadline
        envelope.note(f"iniciada: {spec.label} (prazo {spec.deadline:g} s)")
        self._save(envelope)
        self._update_activity(envelope)
        self._emit(EventType.TARDIS_TASK_STARTED, envelope)
        self._publish_state()
        work = copy.deepcopy(envelope)                     # a análise escreve numa cópia: se for abandonada,
        run = Run(work, self.ctx, deadline, cancel)         # nada do que fizer depois altera a tarefa final
        with self._lock:                                     # o próprio pedido não é fonte da resposta
            run.related_activity = {a for a in (self._activities.get(envelope.id), self._parents.get(envelope.id))
                                    if a}
        box: dict[str, Any] = {}
        finished = threading.Event()
        analyzer = self._analyzers[envelope.kind]

        def target() -> None:
            try:
                box["value"] = analyzer(run, dict(work.input))
            except BaseException as exc:                    # inclui TaskFailed/TaskCancelled
                box["error"] = exc
            finally:
                finished.set()

        threading.Thread(target=target, name=f"tardis-{envelope.kind}", daemon=True).start()
        while not finished.wait(0.05):
            if cancel.is_set() or time.monotonic() > deadline + GRACE:
                break
        envelope.log, envelope.model = list(work.log), work.model
        envelope.duration_ms = int((time.monotonic() - started) * 1000)
        if not finished.is_set():
            if cancel.is_set():
                reason = (envelope.error or {}).get("message") or "cancelada"
                self._final(envelope, "CANCELLED", error={"code": "CANCELLED", "message": reason})
            else:
                cancel.set()                                # avisa a análise travada para parar
                self._final(envelope, "FAILED", error={"code": "TIMEOUT", "message":
                                                       f"{spec.label} excedeu o prazo de {spec.deadline:g} s"})
            return
        error = box.get("error")
        if isinstance(error, TaskCancelled) or (error is None and cancel.is_set()):
            reason = (envelope.error or {}).get("message") or str(error or "cancelada")
            self._final(envelope, "CANCELLED", error={"code": "CANCELLED", "message": reason})
        elif isinstance(error, TaskFailed):
            self._final(envelope, "FAILED", error={"code": error.code, "message": str(error)})
        elif error is not None:
            log.warning("TARDIS: %s falhou: %s", envelope.kind, error, exc_info=error)
            self._final(envelope, "FAILED", error={"code": "INTERNAL",
                                                   "message": f"{type(error).__name__}: {error}"[:300]})
        elif not isinstance(box.get("value"), TaskResult):
            self._final(envelope, "FAILED", error={"code": "INTERNAL", "message": "o analisador não devolveu "
                                                                                    "um resultado"})
        else:
            envelope.result = box["value"]
            self._final(envelope, "DONE")

    def _final(self, envelope: TaskEnvelope, state: str, *, error: dict | None = None) -> None:
        envelope.state = state
        envelope.error = error if state != "DONE" else None
        envelope.finished = time.time()
        if envelope.duration_ms is None and envelope.started:
            envelope.duration_ms = int((envelope.finished - envelope.started) * 1000)
        if error:
            envelope.note(f"{STATE_LABELS[state]}: {error.get('message', '')}")
        else:
            envelope.note(STATE_LABELS[state])
        if state == "FAILED":
            with self._lock:
                self._fault_until = time.time() + FAULT_WINDOW
                self._fault_text = f"{envelope.label}: {(error or {}).get('message', '')}"[:160]
            timer = threading.Timer(FAULT_WINDOW + 0.1, self._publish_state)   # o anel de falha apaga sozinho
            timer.daemon = True
            timer.start()
        with self._lock:
            self._recent.append(envelope)
            self._cancels.pop(envelope.id, None)
            self._parents.pop(envelope.id, None)
            done = self._done.pop(envelope.id, None)
        self._save(envelope)
        self._update_activity(envelope)
        self._emit(FINAL_EVENTS[state], envelope)
        if done is not None:
            done.set()
        self._publish_state()

    # ------------------------------------------------------------ registro e eventos
    def _save(self, envelope: TaskEnvelope) -> None:
        try:
            self.store.save(envelope)
        except Exception as exc:                            # o banco não para a análise; fica no log
            log.warning("TARDIS: tarefa %s não gravada: %s", envelope.id, exc)

    def _begin_activity(self, envelope: TaskEnvelope, parent: str) -> None:
        if self._activity is None:
            return
        text = _input_text(envelope.input)
        activity_id = self._activity.begin(
            "tardis", f"TARDIS · {envelope.label}" + (f": {text[:120]}" if text else ""),
            origin=ACTIVITY_ORIGINS.get(envelope.origin, envelope.origin), input=text, parent=parent,
            ref=envelope.id, detail={"cadeia": " → ".join(envelope.chain) or "direta"})
        with self._lock:
            if activity_id:
                self._activities[envelope.id] = activity_id
            if parent:
                self._parents[envelope.id] = parent

    def _update_activity(self, envelope: TaskEnvelope) -> None:
        if self._activity is None:
            return
        with self._lock:
            activity_id = self._activities.get(envelope.id, "")
            if envelope.final:
                self._activities.pop(envelope.id, None)
        if not activity_id:
            return
        result = envelope.result.summary if envelope.result else None
        error = (envelope.error or {}).get("message") if envelope.error else None
        detail = {"modelo": envelope.model} if envelope.model else None
        if envelope.duration_ms is not None and envelope.final:
            detail = {**(detail or {}), "duracao_ms": envelope.duration_ms}
        self._activity.update(activity_id, state=ACTIVITY_STATES[envelope.state], result=result, error=error,
                              detail=detail)

    def _emit(self, kind: EventType, envelope: TaskEnvelope) -> None:
        if self._bus is not None:
            self._bus.publish(kind, brief(envelope), source="tardis")

    def _publish_state(self, *, force: bool = False) -> None:
        if self._bus is None:
            return
        state = self.state()
        running = state["running"]
        signature = (state["mode"], state["queued"], running["id"] if running else "", tuple(state["operations"]),
                     state["fault"])
        with self._lock:
            if signature == self._last_signature and not force:
                return
            self._last_signature = signature
        self._bus.publish(EventType.TARDIS_STATE, state, source="tardis")
