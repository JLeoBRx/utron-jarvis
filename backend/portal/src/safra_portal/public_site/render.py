"""Ambiente de modelos do site público. O escape automático está sempre ligado; o único HTML produzido fora dos
modelos é o de `render_inline`, que escapa antes de converter."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..domain.blocks import render_inline

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
STATIC = Path(__file__).resolve().parent.parent / "static"
_MONTHS = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
           "novembro", "dezembro")

# Navegação pública: aparece só o que estiver publicado.
NAVIGATION = (("sobre", "Sobre"), ("funcionalidades", "Funcionalidades"), ("inteligencia-artificial", "Inteligência artificial"),
              ("seguranca-e-privacidade", "Segurança"), ("atualizacoes", "Atualizações"), ("documentacao", "Documentação"),
              ("downloads", "Downloads"))
FOOTER_NAVIGATION = (("perguntas-frequentes", "Perguntas frequentes"), ("contato", "Contato"),
                     ("politica-de-privacidade", "Política de privacidade"), ("termos-de-uso", "Termos de uso"))


def long_date(value: datetime | None) -> str:
    if value is None:
        return ""
    return f"{value.day} de {_MONTHS[value.month - 1]} de {value.year}"


def iso_date(value: datetime | None) -> str:
    return value.date().isoformat() if value else ""


def make_environment() -> Environment:
    environment = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(default=True),
                              trim_blocks=True, lstrip_blocks=True)
    environment.filters["inline"] = render_inline
    environment.filters["long_date"] = long_date
    environment.filters["iso_date"] = iso_date
    return environment


def render(environment: Environment, template: str, **context: Any) -> str:
    return environment.get_template(template).render(**context)
