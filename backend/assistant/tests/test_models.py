import sqlite3

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from safra.storage import MIGRATIONS
from safra.storage.models import (AiProvider, Base, Conversation, Memory, Message, Project, Tool, ToolExecution)
from safra_foundation import backup, migrations
from safra_foundation.database import make_engine, sqlite_path

EXTRA_TABLES = {"safra_service", "app_meta", "alembic_version_assistant"}


@pytest.fixture
def engine(settings):
    engine = make_engine(settings.database_url)
    migrations.upgrade(engine, MIGRATIONS, backups_dir=settings.backups_dir)
    yield engine
    engine.dispose()


def test_migration_and_models_describe_the_same_schema(engine):
    inspector = inspect(engine)
    in_database = {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}
    in_models = {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}
    assert set(in_database) - EXTRA_TABLES == set(in_models) and len(in_models) == 11
    for table, columns in in_models.items():
        assert in_database[table] == columns, table


def test_head_is_0002_and_the_model_can_be_reverted_without_touching_the_foundation(engine, settings):
    assert migrations.current_revision(engine, MIGRATIONS) == migrations.head_revision(MIGRATIONS) == "0002"
    result = migrations.downgrade(engine, MIGRATIONS, "0001", backups_dir=settings.backups_dir)
    assert result.after == "0001" and result.backup is not None
    tables = set(inspect(engine).get_table_names())
    assert "conversations" not in tables and {"safra_service", "app_meta"} <= tables
    migrations.upgrade(engine, MIGRATIONS, backups_dir=settings.backups_dir)
    assert "conversations" in inspect(engine).get_table_names()


def test_conversation_with_messages_project_memory_and_tool_execution(engine):
    with Session(engine) as db:
        project = Project(name="Horta")
        provider = AiProvider(name="local", kind="local", enabled=True, allows_private=True)
        db.add_all([project, provider])
        db.flush()
        conversation = Conversation(title="Plantio", project_id=project.id)
        db.add(conversation)
        db.flush()
        db.add_all([Message(conversation_id=conversation.id, role="user", content="O que plantar em novembro?"),
                    Message(conversation_id=conversation.id, role="assistant", content="Alface e rúcula.",
                            provenance={"label": "modelo local"}, provider_id=provider.id),
                    Memory(kind="note", content="Horta vertical na varanda", project_id=project.id),
                    Tool(name="files.list", category="arquivos", risk="low")])
        db.flush()
        db.add(ToolExecution(tool_name="files.list", conversation_id=conversation.id, arguments={"path": "~"}))
        db.commit()
        assert [m.role for m in db.scalars(select(Message).order_by(Message.id))] == ["user", "assistant"]
        db.delete(conversation)                                  # apagar a conversa apaga as mensagens...
        db.commit()
        assert db.scalar(select(Message)) is None
        execution = db.scalar(select(ToolExecution))             # ...e preserva o registro da execução
        assert execution is not None and execution.conversation_id is None
        db.delete(project)
        db.commit()
        assert db.scalar(select(Memory)).project_id is None      # a memória sobrevive ao projeto


def test_invalid_values_and_dangling_references_are_refused_by_the_database(engine, settings):
    path = sqlite_path(settings.database_url)
    engine.dispose()
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys=ON")
    try:
        for statement in (
            "INSERT INTO messages (conversation_id, role, content, provenance) VALUES (999, 'user', 'x', '{}')",
            "INSERT INTO conversations (title) VALUES ('c')",
            "INSERT INTO messages (conversation_id, role, content, provenance) VALUES (1, 'hacker', 'x', '{}')",
            "INSERT INTO memories (kind, content, data) VALUES ('segredo', 'x', '{}')",
            "INSERT INTO ai_providers (name, kind) VALUES ('p', 'nuvem')",
            "INSERT INTO tool_executions (tool_name, arguments) VALUES ('nao.existe', '{}')",
            "INSERT INTO tools (name, category, risk) VALUES ('t', 'c', 'extremo')",
            "INSERT INTO projects (name, status) VALUES ('p', 'apagado')",
        ):
            if statement.startswith("INSERT INTO conversations"):
                raw.execute(statement)                          # válido: prepara a linha para o caso seguinte
                continue
            with pytest.raises(sqlite3.IntegrityError):
                raw.execute(statement)
    finally:
        raw.close()


def test_no_table_has_a_column_meant_for_secrets(engine):
    inspector = inspect(engine)
    columns = {c["name"] for t in inspector.get_table_names() for c in inspector.get_columns(t)}
    assert not {c for c in columns if any(word in c for word in ("password", "secret", "token", "api_key"))}
    assert "credential_ref" in columns                           # só o nome da credencial no cofre do sistema


def test_private_data_survives_backup_and_restore(engine, settings):
    with Session(engine) as db:
        db.add(Memory(kind="fact", content="Aniversário da Ana em 3 de março"))
        db.commit()
    path = sqlite_path(settings.database_url)
    saved = backup.backup_sqlite(path, settings.backups_dir, reason="teste", prefix="safra-assistant")
    with Session(engine) as db:
        db.query(Memory).delete()
        db.commit()
    engine.dispose()
    backup.restore_sqlite(saved.path, path, safety_dir=settings.backups_dir, prefix="safra-assistant")
    restored = make_engine(settings.database_url)
    with Session(restored) as db:
        assert db.scalar(select(Memory.content)) == "Aniversário da Ana em 3 de março"
    restored.dispose()
