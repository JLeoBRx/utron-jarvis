"""Conteúdo estruturado em blocos. O painel nunca envia HTML: envia blocos tipados, e o site os desenha com
escape automático. Assim, texto digitado no CMS não vira marcação nem script (ver PORTAL_THREAT_MODEL.md, XSS).

Dentro de um texto vale só um subconjunto mínimo: ``**negrito**``, ``*itálico*``, `` `código` `` e
``[texto](endereço)``, convertido por `render_inline` DEPOIS do escape.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from markupsafe import Markup, escape
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

MAX_BLOCKS = 200
_SAFE_HREF = re.compile(r"^(https://[^\s<>\"']+|http://[^\s<>\"']+|mailto:[^\s<>\"']+|/[^\s<>\"'\\]*|#[\w-]*)$")
Text = Annotated[str, Field(min_length=1, max_length=4000)]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]
TAGS = ("", "implementado", "em desenvolvimento", "planejado")


def safe_href(value: str) -> str:
    """Aceita só endereços http(s), mailto, caminhos locais e âncoras. Nunca ``javascript:`` ou ``data:``."""
    value = value.strip()
    if not _SAFE_HREF.match(value) or value.startswith("//"):
        raise ValueError("endereço não permitido: use https://…, mailto:…, um caminho começando com / ou uma âncora")
    return value


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Heading(_Block):
    type: Literal["heading"] = "heading"
    level: Literal[2, 3] = 2
    text: ShortText


class Paragraph(_Block):
    type: Literal["paragraph"] = "paragraph"
    text: Text


class ListBlock(_Block):
    type: Literal["list"] = "list"
    ordered: bool = False
    items: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=50)


class Quote(_Block):
    type: Literal["quote"] = "quote"
    text: Text
    cite: str = Field(default="", max_length=200)


class Callout(_Block):
    type: Literal["callout"] = "callout"
    tone: Literal["info", "attention", "status"] = "info"
    title: str = Field(default="", max_length=200)
    text: Text


class Image(_Block):
    type: Literal["image"] = "image"
    media_id: int = Field(ge=1)
    caption: str = Field(default="", max_length=300)


class Card(_Block):
    title: ShortText
    text: Annotated[str, Field(min_length=1, max_length=1000)]
    tag: Literal["", "implementado", "em desenvolvimento", "planejado"] = ""


class Cards(_Block):
    type: Literal["cards"] = "cards"
    items: list[Card] = Field(min_length=1, max_length=24)


class FaqItem(_Block):
    question: ShortText
    answer: Text


class Faq(_Block):
    type: Literal["faq"] = "faq"
    items: list[FaqItem] = Field(min_length=1, max_length=60)


class Button(_Block):
    type: Literal["button"] = "button"
    label: Annotated[str, Field(min_length=1, max_length=60)]
    href: str = Field(max_length=500)

    @field_validator("href")
    @classmethod
    def _href(cls, value: str) -> str:
        return safe_href(value)


class Divider(_Block):
    type: Literal["divider"] = "divider"


Block = Annotated[Union[Heading, Paragraph, ListBlock, Quote, Callout, Image, Cards, Faq, Button, Divider],
                  Field(discriminator="type")]
_BLOCKS = TypeAdapter(Annotated[list[Block], Field(max_length=MAX_BLOCKS)])


def validate_blocks(raw: object) -> list[dict]:
    """Valida e normaliza a lista de blocos. Lança ``pydantic.ValidationError`` se algo não for permitido."""
    return [block.model_dump() for block in _BLOCKS.validate_python(raw)]


def media_ids(blocks: list[dict]) -> set[int]:
    return {int(block["media_id"]) for block in blocks if block.get("type") == "image"}


_INLINE = re.compile(r"\*\*(?P<bold>[^*\n]+)\*\*|\*(?P<em>[^*\n]+)\*|`(?P<code>[^`\n]+)`|\[(?P<label>[^\]\n]+)\]\((?P<href>[^)\s]+)\)")


def render_inline(text: str) -> Markup:
    """Escapa TUDO e só então converte o subconjunto de marcação. Endereço fora da regra vira texto comum."""
    escaped = str(escape(text))

    def replace(match: re.Match) -> str:
        if match.group("bold") is not None:
            return f"<strong>{match.group('bold')}</strong>"
        if match.group("em") is not None:
            return f"<em>{match.group('em')}</em>"
        if match.group("code") is not None:
            return f"<code>{match.group('code')}</code>"
        href = match.group("href").replace("&amp;", "&")
        try:
            href = safe_href(href)
        except ValueError:
            return match.group(0)
        external = href.startswith("http")
        rel = ' rel="noopener noreferrer"' if external else ""
        return f'<a href="{escape(href)}"{rel}>{match.group("label")}</a>'

    return Markup(_INLINE.sub(replace, escaped).replace("\n", "<br>"))
