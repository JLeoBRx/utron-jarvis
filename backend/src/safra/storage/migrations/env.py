"""Ambiente do Alembic. As migrações rodam na conexão entregue por ``safra.storage.migrations``."""
from alembic import context
from sqlalchemy import create_engine

config = context.config


def _run(connection) -> None:  # noqa: ANN001
    context.configure(connection=connection, target_metadata=None, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:                                                      # uso direto pela linha de comando do Alembic
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.connect() as direct:
        _run(direct)
        direct.commit()
