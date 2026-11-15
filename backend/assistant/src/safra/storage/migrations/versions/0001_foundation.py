"""Fundação: dono do banco e metadados da instalação.

Revisão: 0001
Anterior: nenhuma
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    owner = op.create_table(
        "safra_service",
        sa.Column("service", sa.String(length=32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.bulk_insert(owner, [{"service": "assistant"}])
    op.create_table(
        "app_meta",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
    )


def downgrade() -> None:
    op.drop_table("app_meta")
    op.drop_table("safra_service")
