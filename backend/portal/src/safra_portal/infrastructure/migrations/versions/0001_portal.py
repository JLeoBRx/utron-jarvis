"""Esquema inicial do Portal: contas e permissões, conteúdo com versões, mídia, downloads, auditoria e
configurações públicas.

Revisão: 0001
Anterior: nenhuma
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

Stamp = sa.DateTime(timezone=True)
NOW = sa.func.current_timestamp()

# Retrato da matriz de permissões no momento desta migração (a fonte viva é domain/permissions.py;
# tests/test_models.py confere que as duas coincidem).
ROLES = {"administrador": "Administrador", "editor": "Editor", "publicador": "Publicador"}
PERMISSIONS = {
    "admin.access": "Entrar no painel administrativo",
    "dashboard.read": "Ver o resumo do painel",
    "content.read": "Ver páginas e notícias no painel, inclusive rascunhos, versões e pré-visualização",
    "content.edit": "Criar e editar páginas e notícias, salvar rascunhos e restaurar versões como rascunho",
    "content.publish": "Publicar e despublicar páginas e notícias",
    "content.delete": "Excluir páginas e notícias",
    "categories.manage": "Criar, renomear e remover categorias de notícias",
    "media.read": "Ver a biblioteca de mídia",
    "media.upload": "Enviar imagens e editar seus metadados",
    "media.delete": "Remover imagens que não estão em uso",
    "homepage.edit": "Alterar a página inicial e as informações públicas do site",
    "releases.manage": "Cadastrar e editar versões do software para download",
    "users.manage": "Gerenciar usuários, papéis e recuperação de acesso",
    "audit.read": "Consultar a auditoria administrativa",
}
MATRIX = {
    "administrador": sorted(PERMISSIONS),
    "editor": ["admin.access", "categories.manage", "content.edit", "content.read", "dashboard.read", "media.delete",
               "media.read", "media.upload"],
    "publicador": ["admin.access", "content.publish", "content.read", "dashboard.read", "media.read"],
}


def upgrade() -> None:
    owner = op.create_table("safra_service",
                            sa.Column("service", sa.String(32), primary_key=True),
                            sa.Column("created_at", Stamp, nullable=False, server_default=NOW))
    op.bulk_insert(owner, [{"service": "portal"}])

    roles = op.create_table("roles", sa.Column("key", sa.String(32), primary_key=True),
                            sa.Column("name", sa.String(64), nullable=False))
    permissions = op.create_table("permissions", sa.Column("key", sa.String(64), primary_key=True),
                                  sa.Column("description", sa.String(200), nullable=False))
    role_permissions = op.create_table(
        "role_permissions",
        sa.Column("role_key", sa.String(32), sa.ForeignKey("roles.key", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_key", sa.String(64), sa.ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True))
    op.bulk_insert(roles, [{"key": key, "name": name} for key, name in ROLES.items()])
    op.bulk_insert(permissions, [{"key": key, "description": text} for key, text in PERMISSIONS.items()])
    op.bulk_insert(role_permissions, [{"role_key": role, "permission_key": permission}
                                      for role, keys in MATRIX.items() for permission in keys])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False, server_default=""),
        sa.Column("role_key", sa.String(32), sa.ForeignKey("roles.key"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", Stamp), sa.Column("last_login_at", Stamp), sa.Column("password_changed_at", Stamp),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("deleted_at", Stamp))
    op.create_index("ix_users_role_key", "users", ["role_key"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("last_seen_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("expires_at", Stamp, nullable=False),
        sa.Column("revoked_at", Stamp),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(256), nullable=False, server_default=""))
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "recovery_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("expires_at", Stamp, nullable=False),
        sa.Column("used_at", Stamp))
    op.create_index("ix_recovery_tokens_user_id", "recovery_tokens", ["user_id"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("deleted_at", Stamp))

    op.create_table(
        "media",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("stored_name", sa.String(80), nullable=False, unique=True),
        sa.Column("original_name", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("width", sa.Integer), sa.Column("height", sa.Integer),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("alt_text", sa.String(300), nullable=False, server_default=""),
        sa.Column("category", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("deleted_at", Stamp))
    op.create_index("ix_media_sha256", "media", ["sha256"])

    def content_fields():
        return [
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("summary", sa.String(500), nullable=False, server_default=""),
            sa.Column("blocks", sa.JSON, nullable=False),
            sa.Column("seo_title", sa.String(200), nullable=False, server_default=""),
            sa.Column("seo_description", sa.String(300), nullable=False, server_default=""),
            sa.Column("cover_media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="SET NULL")),
            sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id", ondelete="SET NULL")),
        ]

    op.create_table(
        "contents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        *content_fields(),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("published_version_id", sa.Integer),
        sa.Column("published_at", Stamp),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("deleted_at", Stamp),
        sa.Column("lock_version", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("type", "slug", name="uq_contents_type_slug"),
        sa.CheckConstraint("type IN ('page', 'news')", name="ck_contents_type"),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_contents_status"))
    op.create_index("ix_contents_type_status", "contents", ["type", "status"])

    op.create_table(
        "content_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content_id", sa.Integer, sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        *content_fields(),
        sa.Column("kind", sa.String(16), nullable=False, server_default="save"),
        sa.Column("note", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
        sa.UniqueConstraint("content_id", "number", name="uq_content_versions_content_id_number"))
    op.create_index("ix_content_versions_content_id", "content_versions", ["content_id"])

    with op.batch_alter_table("contents") as batch:            # referência circular: criada depois das duas tabelas
        batch.create_foreign_key("fk_contents_published_version", "content_versions", ["published_version_id"], ["id"],
                                 ondelete="SET NULL")

    op.create_table(
        "publication_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content_id", sa.Integer, sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.Integer, sa.ForeignKey("content_versions.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("at", Stamp, nullable=False, server_default=NOW))
    op.create_index("ix_publication_events_content_id", "publication_events", ["content_id"])
    op.create_index("ix_publication_events_at", "publication_events", ["at"])

    op.create_table(
        "releases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("platform", sa.String(24), nullable=False, server_default="windows"),
        sa.Column("channel", sa.String(16), nullable=False, server_default="experimental"),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("published_at", Stamp),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("updated_at", Stamp, nullable=False, server_default=NOW),
        sa.Column("deleted_at", Stamp),
        sa.UniqueConstraint("version", "platform", name="uq_releases_version_platform"),
        sa.CheckConstraint("channel IN ('stable', 'beta', 'experimental')", name="ck_releases_channel"),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_releases_status"))

    op.create_table(
        "release_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("release_id", sa.Integer, sa.ForeignKey("releases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", Stamp, nullable=False, server_default=NOW))
    op.create_index("ix_release_files_release_id", "release_files", ["release_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False, server_default=""),
        sa.Column("target_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("detail", sa.JSON, nullable=False),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("at", Stamp, nullable=False, server_default=NOW))
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_at", "audit_events", ["at"])

    op.create_table(
        "site_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", Stamp, nullable=False, server_default=NOW))


def downgrade() -> None:
    with op.batch_alter_table("contents") as batch:
        batch.drop_constraint("fk_contents_published_version", type_="foreignkey")
    for table in ("site_settings", "audit_events", "release_files", "releases", "publication_events",
                  "content_versions", "contents", "media", "categories", "recovery_tokens", "sessions", "users",
                  "role_permissions", "permissions", "roles", "safra_service"):
        op.drop_table(table)
