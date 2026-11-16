"""Papéis e permissões do painel administrativo — a fonte da matriz documentada em
docs/security/PORTAL_PERMISSIONS.md. A conferência é sempre no servidor (`auth.deps.require`)."""
from __future__ import annotations

ADMINISTRADOR, EDITOR, PUBLICADOR = "administrador", "editor", "publicador"

ROLES: dict[str, str] = {
    ADMINISTRADOR: "Administrador",
    EDITOR: "Editor",
    PUBLICADOR: "Publicador",
}

PERMISSIONS: dict[str, str] = {
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

MATRIX: dict[str, frozenset[str]] = {
    ADMINISTRADOR: frozenset(PERMISSIONS),
    EDITOR: frozenset({"admin.access", "dashboard.read", "content.read", "content.edit", "categories.manage",
                       "media.read", "media.upload", "media.delete"}),
    PUBLICADOR: frozenset({"admin.access", "dashboard.read", "content.read", "content.publish", "media.read"}),
}
# O visitante não tem conta nem permissão: alcança só o conteúdo publicado, pelas rotas públicas.


def role_allows(role: str, permission: str) -> bool:
    return permission in MATRIX.get(role, frozenset())
