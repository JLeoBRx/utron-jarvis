"""Erros do SAFRA: cada um tem um código estável, um status HTTP e uma mensagem que pode ser mostrada.

A mensagem pública nunca carrega rastro interno, caminho de arquivo ou segredo. O detalhe técnico vai para o
log, ligado à resposta pelo identificador de correlação.
"""
from __future__ import annotations

from typing import Any


class SafraError(Exception):
    """Erro previsto. ``code`` é contrato: a interface decide o que fazer por ele, não pelo texto."""

    code = "erro_interno"
    status = 500
    default_message = "Ocorreu um erro interno. O problema foi registrado."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details = dict(details or {})
        super().__init__(self.message)


class ConfigError(SafraError):
    code = "configuracao_invalida"
    default_message = "A configuração é inválida."


class StorageError(SafraError):
    code = "armazenamento"
    default_message = "Não foi possível acessar o armazenamento de dados."


class InvalidInput(SafraError):
    code = "validacao"
    status = 422
    default_message = "Os dados enviados são inválidos."


class NotAuthenticated(SafraError):
    code = "nao_autenticado"
    status = 401
    default_message = "É preciso entrar para continuar."


class Forbidden(SafraError):
    code = "nao_permitido"
    status = 403
    default_message = "Você não tem permissão para esta operação."


class OriginRefused(SafraError):
    code = "origem_recusada"
    status = 403
    default_message = "A origem do pedido não é aceita."


class NotFound(SafraError):
    code = "nao_encontrado"
    status = 404
    default_message = "O item pedido não existe."


class MethodNotAllowed(SafraError):
    code = "metodo_nao_permitido"
    status = 405
    default_message = "Este endereço não aceita o método usado."


class Conflict(SafraError):
    code = "conflito"
    status = 409
    default_message = "A operação entra em conflito com o estado atual."


class RateLimited(SafraError):
    code = "limite_excedido"
    status = 429
    default_message = "Muitas tentativas. Aguarde antes de tentar de novo."


class Unavailable(SafraError):
    code = "indisponivel"
    status = 503
    default_message = "O serviço necessário está indisponível no momento."


def error_payload(error: SafraError, correlation_id: str = "") -> dict[str, Any]:
    """Formato único de erro da API (ver CONTRATO_V1, seção 1.1)."""
    body: dict[str, Any] = {"code": error.code, "message": error.message, "correlation_id": correlation_id}
    if error.details:
        body["details"] = error.details
    return {"error": body}
