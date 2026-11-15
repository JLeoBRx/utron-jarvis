"""Configurações públicas do site: página inicial, rodapé e contato. Tudo aqui é para ser publicado."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session as Db

from safra_foundation.errors import InvalidInput

from ..domain.blocks import safe_href
from ..domain.models import Media, SiteSetting, utcnow
from . import audit

HOMEPAGE_KEY, SITE_KEY = "homepage", "site"
SECTION_KEYS = ("features", "hybrid_ai", "security", "status", "news", "resources")


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=60)
    href: str = Field(max_length=500)

    @field_validator("href")
    @classmethod
    def _href(cls, value: str) -> str:
        return safe_href(value)


class Highlight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=600)
    tag: Literal["", "implementado", "em desenvolvimento", "planejado"] = ""


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Literal["features", "hybrid_ai", "security", "status", "news", "resources"]
    enabled: bool = True
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(default="", max_length=800)
    items: list[Highlight] = Field(default_factory=list, max_length=12)
    links: list[Link] = Field(default_factory=list, max_length=6)


class Homepage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=400)
    image_media_id: int | None = None
    buttons: list[Link] = Field(default_factory=list, max_length=3)
    sections: list[Section] = Field(default_factory=list, max_length=len(SECTION_KEYS))
    featured_news: int = Field(default=3, ge=0, le=6)

    @field_validator("sections")
    @classmethod
    def _unique_sections(cls, value: list[Section]) -> list[Section]:
        keys = [section.key for section in value]
        if len(keys) != len(set(keys)):
            raise ValueError("cada seção só pode aparecer uma vez")
        return value


class SiteInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tagline: str = Field(default="", max_length=200)
    footer_text: str = Field(default="", max_length=400)
    footer_links: list[Link] = Field(default_factory=list, max_length=12)
    contact_email: str = Field(default="", max_length=254)
    contact_links: list[Link] = Field(default_factory=list, max_length=8)

    @field_validator("contact_email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if value and ("@" not in value or " " in value or "<" in value):
            raise ValueError("e-mail inválido")
        return value


_MODELS = {HOMEPAGE_KEY: Homepage, SITE_KEY: SiteInfo}


def load(db: Db, key: str) -> dict[str, Any]:
    row = db.get(SiteSetting, key)
    model = _MODELS[key]
    if row is None:
        return model(title="SAFRA").model_dump() if key == HOMEPAGE_KEY else model().model_dump()
    return model.model_validate(row.value).model_dump()


def save(db: Db, key: str, data: dict[str, Any], *, actor_id: int | None, ip: str = "") -> dict[str, Any]:
    try:
        value = _MODELS[key].model_validate(data)
    except ValidationError as exc:
        problems = [{"field": ".".join(str(p) for p in err["loc"]), "problem": err["msg"]} for err in exc.errors()[:10]]
        raise InvalidInput("Os dados enviados são inválidos.", details={"fields": problems}) from None
    image = getattr(value, "image_media_id", None)
    if image is not None:
        media = db.get(Media, image)
        if media is None or media.deleted_at is not None:
            raise InvalidInput("A imagem escolhida não existe na biblioteca.", details={"field": "image_media_id"})
    row = db.get(SiteSetting, key)
    if row is None:
        row = SiteSetting(key=key)
        db.add(row)
    row.value, row.updated_by, row.updated_at = value.model_dump(), actor_id, utcnow()
    audit.record(db, f"{key}.update", actor_id=actor_id, target_type="site_setting", target_id=key, ip=ip)
    return row.value
