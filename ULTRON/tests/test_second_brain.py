"""Memória pessoal (Second Brain) e lembretes: banco real em pasta temporária, relógio simulado.

Nada aqui toca os dados do usuário: cada caso cria o próprio SQLite numa pasta temporária.
"""
import datetime as dt
import unittest
from pathlib import Path
from types import SimpleNamespace

import helpers

from ultron.memory.store import Database
from ultron.secondbrain import timeutil
from ultron.secondbrain.capture import Capture
from ultron.secondbrain.reminders import ReminderScheduler
from ultron.secondbrain.service import NeedsClarification, SecondBrainError, SecondBrainService

TZ = "America/Sao_Paulo"


def settings(**overrides):
    values = {"timezone": TZ, "reminders": True, "reminder_repeat_minutes": 10.0, "reminder_max_repeats": 2,
              "quiet_hours": "", "notifications_muted": False, "overdue_alerts": False,
              "reminder_default_leads": ("10",)}
    values.update(overrides)
    return SimpleNamespace(**values)


class Events:
    def __init__(self):
        self.items = []

    def publish(self, kind, payload, source=""):
        self.items.append((kind.value if hasattr(kind, "value") else str(kind), dict(payload)))

    def of(self, kind):
        return [p for k, p in self.items if k == kind]


class Brain:
    """Serviço + agendador sobre um arquivo SQLite; ``restart()`` simula fechar e abrir o JARVIS."""

    def __init__(self, start: dt.datetime, **overrides):
        self.path = helpers.temp_dir("sb-") / "jarvis.sqlite3"
        self.clock = helpers.FakeClock(timeutil.to_epoch(start, TZ))
        self.settings = settings(**overrides)
        self.open()

    def open(self):
        self.db = Database(self.path)
        self.events = getattr(self, "events", None) or Events()        # o registro de eventos atravessa reinícios
        self.service = SecondBrainService(self.db, bus=self.events, settings_getter=lambda: self.settings,
                                          clock=self.clock)
        self.service.start()
        self.reminders = ReminderScheduler(self.service, bus=self.events, settings_getter=lambda: self.settings,
                                           clock=self.clock)

    def restart(self):
        self.db.close()
        self.open()

    def close(self):
        self.db.close()

    def at(self, wall: dt.datetime) -> None:
        self.clock.now = timeutil.to_epoch(wall, TZ)

    def due(self):
        return self.events.of("REMINDER_DUE")


MONDAY_9 = dt.datetime(2026, 3, 2, 9, 0)            # segunda-feira, 09:00 (horário de parede)


class RecordCrudTest(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(MONDAY_9)
        self.sb = self.brain.service

    def tearDown(self):
        self.brain.close()

    def test_create_edit_complete_reopen_and_history(self):
        task = self.sb.create("task", "Revisar contrato", body="cláusula 4", when=dt.datetime(2026, 3, 3, 14, 0),
                              priority=3)
        self.assertEqual((task.kind, task.status, task.priority, task.due_local), ("task", "open", 3, "2026-03-03 14:00"))
        edited = self.sb.update(task.id, title="Revisar contrato da sala", priority=4)
        self.assertEqual((edited.title, edited.priority), ("Revisar contrato da sala", 4))
        done = self.sb.complete(task.id)
        self.assertEqual(done.status, "done")
        self.assertIsNotNone(done.completed_at)
        self.assertEqual(self.sb.reopen(task.id).status, "open")
        actions = [h["action"] for h in self.sb.history(task.id)]
        for action in ("created", "completed"):
            self.assertIn(action, actions)
        kinds = [k for k, _p in self.brain.events.items]
        self.assertIn("RECORD_CREATED", kinds)
        self.assertIn("RECORD_UPDATED", kinds)

    def test_trash_restore_and_permanent_delete(self):
        note = self.sb.create("note", "A chave reserva fica com a Ana")
        self.sb.delete(note.id)
        self.assertEqual(self.sb.list(kinds=("note",)), [], "na lixeira não aparece nas listas")
        self.assertEqual([r.id for r in self.sb.trash()], [note.id])
        self.sb.restore(note.id)
        self.assertEqual([r.id for r in self.sb.list(kinds=("note",))], [note.id])
        self.sb.delete(note.id, permanent=True)
        self.assertIsNone(self.sb.get(note.id))
        self.assertEqual(self.sb.trash(), [])

    def test_search_ignores_accents_and_respects_filters(self):
        self.sb.create("idea", "Aplicativo de horários de ônibus")
        self.sb.create("task", "Comprar pão", priority=1)
        done = self.sb.create("task", "Ligar para o ônibus escolar")
        self.sb.complete(done.id)
        found = [r.title for r in self.sb.search("onibus")]
        self.assertEqual(sorted(found), ["Aplicativo de horários de ônibus", "Ligar para o ônibus escolar"])
        self.assertEqual([r.title for r in self.sb.search("onibus", kinds=("idea",))], ["Aplicativo de horários de ônibus"])
        self.assertEqual([r.title for r in self.sb.search("ônibus", include_done=False)],
                         ["Aplicativo de horários de ônibus"])
        by_priority = self.sb.list(kinds=("task",), order="priority")
        self.assertEqual(by_priority[0].title, "Ligar para o ônibus escolar", "prioridade normal antes da baixa")

    def test_secrets_are_refused_and_bad_input_rejected(self):
        with self.assertRaises(SecondBrainError):
            self.sb.create("note", "token ghp_abcdefghijklmnopqrstuvwxyz0123456789")
        with self.assertRaises(SecondBrainError):
            self.sb.create("planeta", "x")
        with self.assertRaises(SecondBrainError):
            self.sb.create("task", "   ")
        self.assertEqual(self.sb.list(), [], "nada foi gravado")

    def test_ambiguous_time_asks_instead_of_guessing(self):
        with self.assertRaises(NeedsClarification) as ctx:
            self.sb.create("event", "Dentista", when="amanhã às 3")
        self.assertIn("manhã", ctx.exception.question)
        with self.assertRaises(NeedsClarification):
            self.sb.create("event", "Reunião", when="31/02 às 10h")
        self.assertEqual(self.sb.list(), [], "nenhuma data inventada")
        event = self.sb.create("event", "Dentista", when="amanhã às 15h")
        self.assertEqual(event.due_local, "2026-03-03 15:00")

    def test_today_and_overdue_views(self):
        self.sb.create("task", "Atrasada", when=dt.datetime(2026, 3, 1, 10, 0))
        self.sb.create("event", "Almoço", when=dt.datetime(2026, 3, 2, 12, 30), remind=False)
        self.sb.create("task", "Semana que vem", when=dt.datetime(2026, 3, 10, 10, 0))
        today = self.sb.today()
        self.assertEqual([r.title for r in self.sb.overdue()], ["Atrasada"])
        self.assertEqual([r["title"] if isinstance(r, dict) else r.title for r in today["events"]], ["Almoço"])


class PersistenceTest(unittest.TestCase):
    def test_records_and_reminders_survive_a_restart(self):
        brain = Brain(MONDAY_9)
        try:
            event = brain.service.create("event", "Consulta", when=dt.datetime(2026, 3, 2, 15, 0))
            idea = brain.service.create("idea", "Painel solar no telhado")
            brain.restart()
            self.assertEqual(brain.service.get(event.id).title, "Consulta")
            self.assertEqual(brain.service.get(idea.id).kind, "idea")
            pending = brain.reminders.upcoming()
            self.assertEqual([r["record_id"] for r in pending], [event.id], "o lembrete continua agendado")
        finally:
            brain.close()


class ReminderTest(unittest.TestCase):
    def test_lead_and_due_fire_once_each(self):
        brain = Brain(MONDAY_9)
        try:
            brain.service.create("event", "Reunião", when=dt.datetime(2026, 3, 2, 10, 0), remind=[15])
            brain.reminders.process()
            self.assertEqual(brain.due(), [], "ainda é cedo")
            brain.at(dt.datetime(2026, 3, 2, 9, 46))
            brain.reminders.process()
            brain.reminders.process()
            self.assertEqual([p["kind"] for p in brain.due()], ["lead"], "aviso antecipado uma única vez")
            brain.at(dt.datetime(2026, 3, 2, 10, 0, 30))
            brain.reminders.process()
            brain.reminders.process()
            self.assertEqual([p["kind"] for p in brain.due()], ["lead", "reminder"])
            self.assertFalse(brain.due()[-1]["late"])
            unread = brain.service.notifications(unread_only=True)
            self.assertEqual(len(unread), 2, "cada aviso também vai para a central de notificações")
        finally:
            brain.close()

    def test_unanswered_reminder_repeats_at_most_the_configured_times(self):
        brain = Brain(MONDAY_9, reminder_max_repeats=2, reminder_repeat_minutes=10.0)
        try:
            brain.service.create("task", "Tomar remédio", when=dt.datetime(2026, 3, 2, 9, 30), remind=True)
            for minute in (30, 40, 50, 60, 70, 80):
                brain.at(dt.datetime(2026, 3, 2, 9, 0) + dt.timedelta(minutes=minute, seconds=5))
                brain.reminders.process()
            self.assertEqual([p["repeat"] for p in brain.due()], [0, 1, 2])
        finally:
            brain.close()

    def test_missed_while_closed_is_notified_once_after_restart(self):
        brain = Brain(MONDAY_9)
        try:
            brain.service.create("event", "Entrega do projeto", when=dt.datetime(2026, 3, 2, 11, 0), remind=True)
            brain.restart()                                  # JARVIS fechado das 9h às 14h
            brain.at(dt.datetime(2026, 3, 2, 14, 0))
            brain.reminders.process()
            brain.reminders.process()
            brain.restart()                                  # reiniciar de novo não repete o aviso
            brain.reminders.process()
            missed = brain.due()
            self.assertEqual(len(missed), 1)
            self.assertEqual(missed[0]["kind"], "missed")
            self.assertTrue(missed[0]["late"])
            notes = brain.service.notifications()
            self.assertTrue(any("perdido" in n["title"] for n in notes))
        finally:
            brain.close()

    def test_daily_routine_advances_and_catches_up_without_a_burst(self):
        brain = Brain(MONDAY_9)
        try:
            routine = brain.service.create("routine", "Alongar", when=dt.datetime(2026, 3, 2, 9, 30), remind=True,
                                           recurrence="daily")
            brain.at(dt.datetime(2026, 3, 2, 9, 30, 10))
            brain.reminders.process()
            self.assertEqual(len(brain.due()), 1)
            self.assertEqual(brain.service.get(routine.id).due_local, "2026-03-03 09:30", "próxima ocorrência")
            brain.at(dt.datetime(2026, 3, 6, 12, 0))         # três dias sem o JARVIS aberto
            brain.reminders.process()
            brain.reminders.process()
            fired = brain.due()
            self.assertEqual(len(fired), 2, "as ocorrências perdidas viram UM aviso, não uma rajada")
            self.assertEqual(fired[-1]["kind"], "missed")
            self.assertEqual(brain.service.get(routine.id).due_local, "2026-03-07 09:30")
        finally:
            brain.close()

    def test_completing_a_task_cancels_its_reminder_and_snooze_moves_it(self):
        brain = Brain(MONDAY_9)
        try:
            task = brain.service.create("task", "Pagar conta de luz", when=dt.datetime(2026, 3, 2, 18, 0), remind=True)
            done = brain.service.create("task", "Enviar relatório", when=dt.datetime(2026, 3, 2, 17, 0), remind=True)
            brain.service.complete(done.id)
            brain.at(dt.datetime(2026, 3, 2, 18, 0, 5))
            brain.reminders.process()
            self.assertEqual([p["record_id"] for p in brain.due()], [task.id], "concluída não avisa")
            reminder_id = brain.due()[0]["id"]
            brain.reminders.snooze(reminder_id, 30)
            brain.at(dt.datetime(2026, 3, 2, 18, 20))
            brain.reminders.process()
            self.assertEqual(len(brain.due()), 1, "adiado: nada antes do novo horário")
            brain.at(dt.datetime(2026, 3, 2, 18, 30, 10))
            brain.reminders.process()
            self.assertEqual(len(brain.due()), 2)
        finally:
            brain.close()

    def test_quiet_hours_keep_the_notice_but_silence_it(self):
        brain = Brain(dt.datetime(2026, 3, 2, 22, 0), quiet_hours="22:00-07:00")
        try:
            brain.service.create("task", "Backup do servidor", when=dt.datetime(2026, 3, 2, 23, 0), remind=True)
            brain.at(dt.datetime(2026, 3, 2, 23, 0, 5))
            brain.reminders.process()
            self.assertTrue(brain.due()[0]["silent"], "silêncio não descarta: o aviso fica na central, sem som")
            self.assertEqual(len(brain.service.notifications()), 1)
        finally:
            brain.close()

    def test_reminders_do_not_need_the_ai_model(self):
        """O agendador é determinístico: nenhum modelo, rede ou serviço externo participa."""
        brain = Brain(MONDAY_9)
        try:
            self.assertFalse(hasattr(brain.reminders, "router"))
            brain.service.create("event", "Aula", when=dt.datetime(2026, 3, 2, 9, 5), remind=True)
            brain.at(dt.datetime(2026, 3, 2, 9, 5, 1))
            wait = brain.reminders.process()
            self.assertEqual(len(brain.due()), 1)
            self.assertGreater(wait, 0)
        finally:
            brain.close()


class AgendaConflictTest(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(MONDAY_9)
        self.sb = self.brain.service

    def tearDown(self):
        self.brain.close()

    def test_overlapping_events_are_reported_not_blocked(self):
        meeting = self.sb.create("event", "Reunião de equipe", when=dt.datetime(2026, 3, 3, 14, 0),
                                 end=dt.datetime(2026, 3, 3, 15, 30), remind=False)
        dentist = self.sb.create("event", "Dentista", when=dt.datetime(2026, 3, 3, 15, 0), remind=False)
        later = self.sb.create("event", "Academia", when=dt.datetime(2026, 3, 3, 16, 0), remind=False)
        self.sb.create("event", "Feriado", when=dt.date(2026, 3, 3), remind=False)          # dia inteiro
        self.sb.create("task", "Relatório", when=dt.datetime(2026, 3, 3, 15, 0))            # tarefa não ocupa agenda
        self.assertEqual([r.id for r in self.sb.conflicts(dentist)], [meeting.id])
        self.assertEqual([r.id for r in self.sb.conflicts(meeting)], [dentist.id])
        self.assertEqual(self.sb.conflicts(later), [], "16h começa quando o dentista (1 h) termina")
        pairs = self.sb.agenda_conflicts(days=14)
        self.assertEqual([(a.id, b.id) for a, b in pairs], [(meeting.id, dentist.id)])
        created = self.brain.events.of("RECORD_CREATED")
        self.assertEqual([c["id"] for c in created[1]["conflicts"]], [meeting.id], "o evento informa o conflito")
        self.assertIsNotNone(self.sb.get(dentist.id), "nada é bloqueado: o usuário decide")
        self.sb.complete(meeting.id)
        self.assertEqual(self.sb.conflicts(dentist), [], "compromisso concluído não ocupa mais a agenda")

    def test_capture_confirmation_mentions_the_conflict(self):
        from ultron.secondbrain.capture import confirmation_text

        self.sb.create("event", "Reunião com a diretoria", when=dt.datetime(2026, 3, 3, 10, 0), remind=False)
        capture = Capture(self.sb, settings_getter=lambda: self.brain.settings)
        result = capture.explicit("marque uma consulta amanhã às 10h30", kind="event")
        self.assertTrue(result.ok)
        self.assertEqual([r.title for r in result.conflicts], ["Reunião com a diretoria"])
        text = confirmation_text(result, now=self.sb.now_wall())
        self.assertIn("conflita com Reunião com a diretoria", text)


class ExportBackupTest(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(MONDAY_9)
        self.sb = self.brain.service
        self.sb.create("task", "Comprar café", priority=3, when=dt.datetime(2026, 3, 3, 9, 0))
        self.sb.create("idea", "Horta vertical; com irrigação")
        trashed = self.sb.create("note", "Rascunho antigo")
        self.sb.delete(trashed.id)

    def tearDown(self):
        self.brain.close()

    def test_json_export_is_complete_and_never_overwrites(self):
        import json
        target = helpers.temp_dir("export-") / "memoria.json"
        info = self.sb.export(target, fmt="json")
        data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(info["count"], 2, "a lixeira fica de fora por padrão")
        self.assertEqual(data["count"], 2)
        self.assertEqual(sorted(r["title"] for r in data["records"]), ["Comprar café", "Horta vertical; com irrigação"])
        self.assertTrue(data["reminders"] == [] or all("record_id" in r for r in data["reminders"]))
        with self.assertRaises(SecondBrainError):
            self.sb.export(target, fmt="json")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["count"], 2, "arquivo original intacto")
        with self.assertRaises(SecondBrainError):
            self.sb.export(target.with_suffix(".xml"), fmt="xml")

    def test_csv_export_opens_as_a_spreadsheet(self):
        import csv
        target = helpers.temp_dir("export-") / "memoria.csv"
        self.sb.export(target, fmt="csv", include_deleted=True)
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        self.assertEqual(rows[0][:3], ["id", "kind", "title"])
        titles = {row[2]: row for row in rows[1:]}
        self.assertEqual(set(titles), {"Comprar café", "Horta vertical; com irrigação", "Rascunho antigo"})
        self.assertEqual(titles["Comprar café"][1], "Tarefa")
        self.assertEqual(titles["Comprar café"][6], "2026-03-03 09:00")

    def test_backup_is_consistent_rotated_and_restorable(self):
        from ultron.memory import backup
        from ultron.memory.store import verify_database_file

        folder = helpers.temp_dir("backups-")
        first = backup.create_backup(self.brain.db, keep=2, directory=folder, clock=lambda: 1000.0)
        self.assertTrue(verify_database_file(first)[0])
        self.assertIsNone(backup.backup_if_due(self.brain.db, interval_hours=24, directory=folder,
                                               clock=lambda: 1000.0 + 3600), "último backup há 1 h: nada a fazer")
        second = backup.backup_if_due(self.brain.db, interval_hours=24, keep=2, directory=folder,
                                      clock=lambda: 1000.0 + 25 * 3600)
        self.assertIsNotNone(second)
        backup.create_backup(self.brain.db, keep=2, directory=folder, clock=lambda: 1000.0 + 26 * 3600)
        self.assertEqual(len(backup.list_backups(folder)), 2, "só os mais recentes ficam")
        # restaurar (JARVIS fechado): o banco atual é guardado, nada se perde
        newest = backup.list_backups(folder)[0]["path"]
        self.sb.create("note", "Criada depois do backup")
        self.brain.db.close()
        result = backup.restore_backup(newest, database=self.brain.path, clock=lambda: 5000.0)
        self.assertTrue(Path(result["previous"]).is_file())
        self.brain.open()
        titles = {r.title for r in self.brain.service.list()}
        self.assertNotIn("Criada depois do backup", titles, "voltou ao estado do backup")
        self.assertIn("Comprar café", titles)
        broken = folder / "quebrado.sqlite3"
        broken.write_bytes(b"isto nao e um banco")
        with self.assertRaises(ValueError):
            backup.restore_backup(broken, database=self.brain.path)


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(MONDAY_9)
        self.capture = Capture(self.brain.service, settings_getter=lambda: self.brain.settings)

    def tearDown(self):
        self.brain.close()

    def test_explicit_request_is_confirmed_and_wake_name_is_ignored(self):
        result = self.capture.explicit("Jarvis, anote uma ideia: painel de energia na garagem")
        self.assertTrue(result.ok)
        record = result.records[0]
        self.assertEqual(record.kind, "idea")
        self.assertTrue(record.confirmed)
        self.assertNotIn("jarvis", record.title.lower())

    def test_automatic_capture_needs_clear_evidence(self):
        self.assertFalse(self.capture.auto("talvez eu vá ao dentista amanhã às 15h").ok, "hipótese não é registrada")
        self.assertFalse(self.capture.auto("o que você acha de dentistas?").ok)
        result = self.capture.auto("tenho dentista amanhã às 15h")
        self.assertTrue(result.ok)
        self.assertFalse(result.records[0].confirmed, "inferido: aguarda revisão do usuário")
        self.assertEqual([r.id for r in self.brain.service.review_queue()], [result.records[0].id])

    def test_sensitive_content_is_never_captured_automatically(self):
        self.assertFalse(self.capture.auto("preciso pagar o boleto 23793381286000000000 amanhã às 10h").ok)
        self.assertFalse(self.capture.auto("tenho que trocar a senha do banco amanhã às 9h").ok)



class QueriesTest(unittest.TestCase):
    """Perguntas sobre a memória pessoal: a resposta sai SÓ dos registros salvos; sem registro correspondente,
    diz que não encontrou — nunca completa com suposições."""

    def setUp(self):
        self.brain = Brain(dt.datetime(2026, 3, 10, 9, 0))            # terça-feira, 9h
        self.sb = self.brain.service

    def tearDown(self):
        self.brain.close()

    def ask(self, text):
        from ultron.secondbrain.queries import answer
        return answer(self.sb, text)

    def test_with_nothing_saved_every_question_says_so(self):
        cases = {"quais são minhas prioridades de hoje?": "Não há compromissos nem tarefas prioritárias registrados "
                                                         "para hoje.",
                 "o que está atrasado?": "Nada atrasado.",
                 "o que preciso terminar esta semana?": "Não há tarefas abertas com prazo até o fim desta semana.",
                 "quais ideias salvei para o projeto Atlas?": "Não encontrei ideias salvas para Atlas.",
                 "o que eu havia decidido sobre o orçamento?": "Não encontrei decisões registradas sobre orçamento.",
                 "quais são meus projetos?": "Nenhum projeto ativo registrado.",
                 "o que tenho amanhã?": "Nada agendado para amanhã.",
                 "o que anotei sobre a viagem?": 'Não encontrei registros sobre "a viagem".'}
        for question, expected in cases.items():
            reply = self.ask(question)
            self.assertEqual((reply.text, reply.kind, reply.records), (expected, "empty", []), question)

    def test_answers_come_only_from_saved_records(self):
        sb = self.sb
        atlas = sb.create("project", "Atlas")
        sb.create("idea", "Painel solar portátil", project="Atlas")
        sb.create("idea", "Bateria modular", project="Atlas")
        sb.create("idea", "Horta vertical")                                   # de outro assunto
        sb.create("task", "Revisar orçamento", when="2026-03-08 18:00", priority=3)
        sb.create("task", "Entregar relatório", when="2026-03-13 17:00", project="Atlas")
        sb.create("event", "Dentista", when="2026-03-11 15:00")
        sb.create("note", "Usar fornecedor local", body="sobre o orçamento do Atlas: menor frete",
                  tags=("decisão",))
        ideas = self.ask("quais ideias salvei para o projeto Atlas?")
        self.assertEqual((ideas.kind, len(ideas.records)), ("list", 2))
        self.assertIn("Painel solar portátil", ideas.text)
        self.assertNotIn("Horta vertical", ideas.text, "só as ideias do projeto perguntado")
        overdue = self.ask("o que está atrasado?")
        self.assertEqual([r.title for r in overdue.records], ["Revisar orçamento"])
        week = self.ask("o que preciso terminar esta semana?")
        self.assertIn("Entregar relatório", week.text)
        tomorrow = self.ask("o que tenho amanhã?")
        self.assertIn("Dentista", tomorrow.text)
        decided = self.ask("o que eu havia decidido sobre o orçamento?")
        self.assertIn("Usar fornecedor local", decided.text)
        projects = self.ask("quais são meus projetos?")
        self.assertIn("Atlas (3 aberto(s))", projects.text, "2 ideias e 1 tarefa ligadas ao projeto")
        self.assertEqual(projects.records[0]["id"] if isinstance(projects.records[0], dict) else projects.records[0].id,
                         atlas.id)
        found = self.ask("o que anotei sobre painel solar?")
        self.assertEqual((found.kind, found.query), ("list", "search"))
        self.assertIn("Painel solar portátil", found.text)
        nothing = self.ask("o que anotei sobre submarino?")
        self.assertEqual((nothing.kind, nothing.records), ("empty", []))

    def test_ambiguous_reference_asks_instead_of_guessing(self):
        self.sb.create("task", "Relatório de vendas")
        self.sb.create("task", "Relatório de compras")
        reply = self.ask("quais tarefas dependem do relatório?")
        self.assertEqual(reply.kind, "clarify", reply.text)

if __name__ == "__main__":
    unittest.main()
