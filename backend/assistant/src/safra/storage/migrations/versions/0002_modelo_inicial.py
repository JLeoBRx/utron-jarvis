"""Modelo inicial do Assistant: configurações, preferências, projetos, provedores de IA, conversas, mensagens,
memórias, ferramentas, execuções, atividades e eventos de log.

Revisão: 0002
Anterior: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

Stamp = sa.DateTime(timezone=True)
NOW = sa.func.current_timestamp()


def upgrade() -> None:
    op.create_table("settings", sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("value", sa.JSON, nullable=False),
                    sa.Column("updated_at", Stamp, nullable=False, server_default=NOW))
    op.create_table("preferences", sa.Column("key", sa.String(120), primary_key=True),
                    sa.Column("value", sa.JSON, nullable=False),
                    sa.Column("source", sa.String(16), nullable=False, server_default="user"),
                    sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
                    sa.CheckConstraint("source IN ('user', 'learned', 'import')", name="ck_preferences_source"))
    op.create_table("projects", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("name", sa.String(120), nullable=False, unique=True),
                    sa.Column("description", sa.Text, nullable=False, server_default=""),
                    sa.Column("status", sa.String(16), nullable=False, server_default="active"),
                    sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
                    sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
                    sa.Column("archived_at", Stamp),
                    sa.CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status"))
    op.create_table("ai_providers", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("name", sa.String(64), nullable=False, unique=True),
                    sa.Column("kind", sa.String(16), nullable=False),
                    sa.Column("base_url", sa.String(300), nullable=False, server_default=""),
                    sa.Column("default_model", sa.String(120), nullable=False, server_default=""),
                    sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
                    sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
                    sa.Column("allows_private", sa.Boolean, nullable=False, server_default=sa.false()),
                    sa.Column("credential_ref", sa.String(120), nullable=False, server_default=""),
                    sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
                    sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
                    sa.CheckConstraint("kind IN ('local', 'remote')", name="ck_ai_providers_kind"))
    op.create_table("conversations", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("title", sa.String(200), nullable=False, server_default=""),
                    sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL")),
                    sa.Column("started_at", Stamp, nullable=False, server_default=NOW),
                    sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
                    sa.Column("archived_at", Stamp))
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])
    op.create_table("messages", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("role", sa.String(16), nullable=False),
                    sa.Column("content", sa.Text, nullable=False),
                    sa.Column("provenance", sa.JSON, nullable=False),
                    sa.Column("provider_id", sa.Integer, sa.ForeignKey("ai_providers.id", ondelete="SET NULL")),
                    sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
                    sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name="ck_messages_role"))
    op.create_index("ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"])
    op.create_table("memories", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("kind", sa.String(16), nullable=False),
                    sa.Column("content", sa.Text, nullable=False),
                    sa.Column("data", sa.JSON, nullable=False),
                    sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL")),
                    sa.Column("source", sa.String(16), nullable=False, server_default="user"),
                    sa.Column("importance", sa.Integer, nullable=False, server_default="0"),
                    sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
                    sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
                    sa.Column("deleted_at", Stamp),
                    sa.CheckConstraint("kind IN ('fact', 'episode', 'procedure', 'note', 'reminder')", name="ck_memories_kind"),
                    sa.CheckConstraint("source IN ('user', 'assistant', 'import')", name="ck_memories_source"))
    op.create_index("ix_memories_kind_deleted_at", "memories", ["kind", "deleted_at"])
    op.create_index("ix_memories_project_id", "memories", ["project_id"])
    op.create_table("tools", sa.Column("name", sa.String(80), primary_key=True),
                    sa.Column("category", sa.String(40), nullable=False),
                    sa.Column("risk", sa.String(8), nullable=False, server_default="none"),
                    sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
                    sa.Column("description", sa.String(300), nullable=False, server_default=""),
                    sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
                    sa.CheckConstraint("risk IN ('none', 'low', 'medium', 'high')", name="ck_tools_risk"))
    op.create_table("tool_executions", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("tool_name", sa.String(80), sa.ForeignKey("tools.name", ondelete="RESTRICT"), nullable=False),
                    sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id", ondelete="SET NULL")),
                    sa.Column("arguments", sa.JSON, nullable=False),
                    sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
                    sa.Column("result", sa.JSON),
                    sa.Column("error", sa.Text, nullable=False, server_default=""),
                    sa.Column("verified", sa.Boolean),
                    sa.Column("requested_at", Stamp, nullable=False, server_default=NOW),
                    sa.Column("started_at", Stamp), sa.Column("finished_at", Stamp),
                    sa.CheckConstraint("status IN ('pending', 'authorized', 'denied', 'running', 'succeeded', 'failed', 'cancelled')",
                                       name="ck_tool_executions_status"))
    op.create_index("ix_tool_executions_tool_name", "tool_executions", ["tool_name"])
    op.create_index("ix_tool_executions_conversation_id", "tool_executions", ["conversation_id"])
    op.create_index("ix_tool_executions_status_requested_at", "tool_executions", ["status", "requested_at"])
    op.create_table("activity_events", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("kind", sa.String(32), nullable=False),
                    sa.Column("origin", sa.String(32), nullable=False, server_default=""),
                    sa.Column("title", sa.String(300), nullable=False),
                    sa.Column("state", sa.String(16), nullable=False, server_default="done"),
                    sa.Column("detail", sa.JSON, nullable=False),
                    sa.Column("ref_type", sa.String(32), nullable=False, server_default=""),
                    sa.Column("ref_id", sa.String(64), nullable=False, server_default=""),
                    sa.Column("at", Stamp, nullable=False, server_default=NOW))
    op.create_index("ix_activity_events_kind", "activity_events", ["kind"])
    op.create_index("ix_activity_events_at", "activity_events", ["at"])
    op.create_table("log_events", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("level", sa.String(8), nullable=False),
                    sa.Column("component", sa.String(64), nullable=False),
                    sa.Column("message", sa.Text, nullable=False),
                    sa.Column("data", sa.JSON, nullable=False),
                    sa.Column("correlation_id", sa.String(32), nullable=False, server_default=""),
                    sa.Column("at", Stamp, nullable=False, server_default=NOW))
    op.create_index("ix_log_events_level_at", "log_events", ["level", "at"])


def downgrade() -> None:
    for table in ("log_events", "activity_events", "tool_executions", "tools", "memories", "messages", "conversations",
                  "ai_providers", "projects", "preferences", "settings"):
        op.drop_table(table)
