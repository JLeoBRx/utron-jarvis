"""Migração de teste: dono do banco e uma tabela."""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    owner = op.create_table("safra_service", sa.Column("service", sa.String(32), primary_key=True))
    op.bulk_insert(owner, [{"service": "teste"}])
    op.create_table("app_meta", sa.Column("key", sa.String(64), primary_key=True), sa.Column("value", sa.Text(), nullable=False))


def downgrade() -> None:
    op.drop_table("app_meta")
    op.drop_table("safra_service")
