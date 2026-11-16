"""Ambiente comum do Alembic: o ``env.py`` de cada serviço só chama ``run()``."""
from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine


def run() -> None:
    config = context.config
    version_table = config.attributes.get("version_table", "alembic_version")

    def migrate(connection) -> None:  # noqa: ANN001
        context.configure(connection=connection, target_metadata=None, render_as_batch=True,
                          version_table=version_table)
        with context.begin_transaction():
            context.run_migrations()

    connection = config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
        return
    engine = create_engine(config.get_main_option("sqlalchemy.url"))   # uso direto pela linha de comando do Alembic
    with engine.connect() as direct:
        migrate(direct)
        direct.commit()
