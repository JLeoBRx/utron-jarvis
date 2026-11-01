"""Falhas — quando algo quebra, o JARVIS diz o motivo, não perde dados do usuário e volta ao repouso.

* configurações ilegíveis: padrões em uso e o arquivo original guardado antes de qualquer gravação;
* banco danificado: o início para com uma mensagem clara (código 3) e o arquivo não é tocado; um backup o
  restaura e o arquivo danificado fica guardado;
* banco que recusa gravação (somente leitura, disco cheio): a conversa continua e a resposta diz o que não
  foi gravado;
* backup que falha no meio: nenhum arquivo pela metade e os backups anteriores intactos;
* modelo que quebra no meio do pedido: resposta honesta e o JARVIS volta ao repouso;
* sensor que falha: fica marcado com o motivo, sem derrubar os outros.

As falhas são provocadas de propósito — disco cheio por exceção injetada, banco somente leitura por
``PRAGMA query_only``, servidor do modelo que quebra por HTTP local. Não é teste de disco, Windows ou rede de
verdade.
"""
import errno
import hashlib
import json
import os
import subprocess
import sys
import time
import unittest

import helpers

from fake_ollama import FakeOllama
from ultron.config.settings import SettingsManager
from ultron.memory import backup
from ultron.memory.store import Database
from ultron.perception.base import Percept, Sensor, SensorUnavailable


def digest(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


class SettingsFailureTest(unittest.TestCase):
    def test_unreadable_settings_fall_back_and_the_original_is_kept(self):
        folder = helpers.temp_dir("cfg-")
        path = folder / "settings.json"
        garbage = b'{"audio_input_name": "Microfone USB (2- Realtek)", "hud_fps": 4'       # cortado no meio
        path.write_bytes(garbage)
        manager = SettingsManager(path)
        settings = manager.load()
        self.assertEqual(settings.hud_fps, type(settings)().hud_fps, "padrões em uso")
        kept = list(folder.glob("settings.ilegivel-*.json"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_bytes(), garbage, "o original ficou guardado byte a byte")
        self.assertTrue(any("ilegível" in note for note in manager.migration_notes), manager.migration_notes)
        manager.update(hud_fps=30)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["hud_fps"], 30)
        self.assertEqual(kept[0].read_bytes(), garbage, "a gravação seguinte não apagou a cópia")
        path.write_bytes(garbage)
        SettingsManager(path).load()
        self.assertEqual(len(list(folder.glob("settings.ilegivel-*.json"))), 1, "mesmo conteúdo: uma cópia só")


class DatabaseFailureTest(unittest.TestCase):
    def run_jarvis(self, data_dir, *args):
        env = {**os.environ, "ULTRON_DATA_DIR": str(data_dir), "QT_QPA_PLATFORM": "offscreen"}
        return subprocess.run([sys.executable, str(helpers.ROOT / "main.py"), *args], cwd=helpers.ROOT, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)

    def test_damaged_database_stops_startup_with_a_clear_message_and_is_left_untouched(self):
        data = helpers.temp_dir("dados-")
        database = data / "ultron.sqlite3"
        database.write_bytes(b"isto nao e um banco sqlite\n" * 50)
        before = digest(database)
        for args in (["--headless", "--no-voice", "--no-perception", "--no-plugins"], ["--backup"]):
            done = self.run_jarvis(data, *args)
            output = done.stdout + done.stderr
            self.assertEqual(done.returncode, 3, output[-2000:])
            self.assertIn("O banco de memória do JARVIS não abriu", output)
            self.assertIn("O arquivo NÃO foi alterado", output)
            self.assertIn("--restore-backup", output)
            self.assertNotIn("Traceback", output)
        self.assertEqual(digest(database), before, "o arquivo do usuário não foi tocado")

    def test_a_backup_restores_a_damaged_database_and_the_damaged_copy_is_kept(self):
        folder = helpers.temp_dir("restaura-")
        path = folder / "ultron.sqlite3"
        db = Database(path)
        db.set_meta("lembrete-importante", "levar o carro na revisão")
        saved = backup.create_backup(db, directory=folder / "backups")
        db.close()
        for extra in ("-wal", "-shm"):
            if os.path.exists(str(path) + extra):
                os.remove(str(path) + extra)
        path.write_bytes(b"\x00danificado\x00" * 100)
        damaged = digest(path)
        result = backup.restore_backup(saved, database=path)
        restored = Database(path)
        self.assertEqual(restored.get_meta("lembrete-importante"), "levar o carro na revisão")
        restored.close()
        self.assertEqual(digest(result["previous"]), damaged, "o banco danificado ficou guardado, não apagado")

    def test_failed_backup_leaves_no_partial_file_and_the_old_backups_intact(self):
        folder = helpers.temp_dir("backup-")
        db = Database(folder / "ultron.sqlite3")
        old = backup.create_backup(db, directory=folder / "backups", clock=lambda: 1_700_000_000)
        old_digest = digest(old)

        class DiskFull:
            def __init__(self, conn):
                self._conn = conn

            def backup(self, target, **_):
                raise OSError(errno.ENOSPC, "No space left on device")

            def __getattr__(self, name):
                return getattr(self._conn, name)

        real = db._conn
        db._conn = DiskFull(real)
        try:
            with self.assertRaises(OSError):
                backup.create_backup(db, directory=folder / "backups", clock=lambda: 1_700_000_100)
        finally:
            db._conn = real
            db.close()
        files = sorted(p.name for p in (folder / "backups").iterdir())
        self.assertEqual(files, [old.name], "nenhum backup pela metade")
        self.assertEqual(digest(old), old_digest)


def responder(payload):
    messages = payload.get("messages") or []
    if "poesia" in str(messages[-1].get("content", "")):
        raise RuntimeError("o servidor do modelo quebrou no meio do pedido")
    return "Certo."


class RuntimeFailureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ultron.config.settings import SettingsManager as Manager
        from ultron.core.events import EventType
        from ultron.core.neural_core import NeuralCore
        cls.fake = FakeOllama(["qwen2.5:3b"], responder=responder)
        cls.fake.__enter__()
        manager = Manager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = cls.fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        cls.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
        cls.responses = []
        cls.core.bus.subscribe(EventType.RESPONSE_READY, lambda e: cls.responses.append(e.payload), name="t")
        cls.core.boot()

    @classmethod
    def tearDownClass(cls):
        cls.core.memory.db.execute("PRAGMA query_only=OFF")
        cls.core.shutdown()
        cls.fake.__exit__(None, None, None)

    def ask(self, text, seconds=30):
        mark = len(self.responses)
        self.assertTrue(self.core.submit(text, source="text"))
        end = time.time() + seconds
        while time.time() < end:
            final = [r for r in self.responses[mark:] if not r.get("partial")]
            if final:
                return final[-1]
            time.sleep(0.02)
        self.fail(f"sem resposta para: {text}")

    def assert_at_rest(self):
        end = time.time() + 5
        while time.time() < end and self.core.state.runtime_state != "IDLE":
            time.sleep(0.02)
        self.assertEqual(self.core.state.runtime_state, "IDLE")

    def test_a_database_that_refuses_writes_never_breaks_the_conversation(self):
        db = self.core.memory.db
        db.execute("PRAGMA query_only=ON")
        try:
            self.assertRegex(self.ask("que horas são?")["text"], r"São \d{2}:\d{2}")
            note = self.ask("anote uma ideia: horta vertical na varanda")
            self.assertFalse(note.get("success"))
            self.assertIn("Não consegui gravar na memória do JARVIS", note["text"])
            self.assertIn("Nada foi registrado", note["text"])
            self.assert_at_rest()
        finally:
            db.execute("PRAGMA query_only=OFF")
        again = self.ask("anote uma ideia: horta vertical na varanda")
        self.assertNotIn("Não consegui gravar", again["text"], "com o banco de volta, a nota é gravada")

    def test_a_model_that_breaks_mid_request_gets_an_honest_answer(self):
        answer = self.ask("o que você acha de poesia?")
        self.assertEqual((answer.get("kind"), answer.get("success")), ("error", False))
        self.assertIn("O modelo local falhou", answer["text"])
        self.assert_at_rest()
        self.assertEqual(self.ask("me diga algo")["text"], "Certo.", "o pedido seguinte funciona")


class SensorFailureTest(unittest.TestCase):
    def test_a_failing_sensor_is_marked_with_its_reason_and_recovers(self):
        class Flaky(Sensor):
            name = "teste"
            mode = "quebra"

            def sense(self):
                if self.mode == "quebra":
                    raise RuntimeError("driver da câmera sumiu")
                if self.mode == "ausente":
                    raise SensorUnavailable("câmera desconectada")
                return Percept(self.name, "telemetry", {"ok": True}, 1.0)

        sensor = Flaky()
        self.assertIsNone(sensor.poll(), "nunca levanta exceção")
        self.assertEqual((sensor.status, sensor.errors), ("ERROR", 1))
        self.assertIn("driver da câmera sumiu", sensor.reason)
        sensor.mode = "ausente"
        self.assertIsNone(sensor.poll())
        self.assertEqual((sensor.status, sensor.reason), ("UNAVAILABLE", "câmera desconectada"))
        sensor.mode = "ok"
        self.assertIsNotNone(sensor.poll())
        self.assertEqual((sensor.status, sensor.reason), ("OK", ""))
        sensor.enabled = False
        self.assertIsNone(sensor.poll())
        self.assertEqual(sensor.status, "DISABLED")


if __name__ == "__main__":
    unittest.main()
