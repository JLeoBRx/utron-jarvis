"""Versões do software para download. O cadastro funciona; a PUBLICAÇÃO está bloqueada no código até a análise
de licenças terminar (docs/engineering/LICENSE_INVENTORY.md, decisão AD-17)."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from safra_foundation.errors import Conflict, InvalidInput, NotFound

from ..domain.models import Release, as_utc, utcnow
from . import audit

# Bloqueio deliberado. Só muda por alteração de código acompanhada de decisão registrada — não é configuração.
RELEASE_PUBLICATION_ENABLED = False
BLOCK_REASON = ("A publicação de instaladores está bloqueada até a conclusão do inventário de licenças "
                "e da decisão sobre a licença do SAFRA.")
CHANNELS = ("stable", "beta", "experimental")
PLATFORMS = ("windows",)
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.]{1,20})?$")


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    version = str(data.get("version", "")).strip()
    if not _VERSION.match(version):
        raise InvalidInput("Use um número de versão como 4.0.0 ou 4.0.0-beta.1.", details={"field": "version"})
    channel, platform = str(data.get("channel", "experimental")), str(data.get("platform", "windows"))
    if channel not in CHANNELS:
        raise InvalidInput("Canal inexistente.", details={"field": "channel"})
    if platform not in PLATFORMS:
        raise InvalidInput("Plataforma inexistente.", details={"field": "platform"})
    notes = str(data.get("notes", "")).strip()
    if len(notes) > 8000:
        raise InvalidInput("As notas ficaram longas demais.", details={"field": "notes"})
    return {"version": version, "channel": channel, "platform": platform, "notes": notes}


def to_dict(release: Release) -> dict[str, Any]:
    return {"id": release.id, "version": release.version, "platform": release.platform, "channel": release.channel,
            "notes": release.notes, "status": release.status,
            "published_at": as_utc(release.published_at).isoformat() if release.published_at else None,
            "updated_at": as_utc(release.updated_at).isoformat()}


def get(db: Db, release_id: int) -> Release:
    release = db.get(Release, release_id)
    if release is None or release.deleted_at is not None:
        raise NotFound("Versão não encontrada.")
    return release


def list_admin(db: Db) -> list[Release]:
    return list(db.scalars(select(Release).where(Release.deleted_at.is_(None)).order_by(Release.created_at.desc())))


def create(db: Db, data: dict[str, Any], *, actor_id: int | None, ip: str = "") -> Release:
    fields = _clean(data)
    if db.scalar(select(Release.id).where(Release.version == fields["version"], Release.platform == fields["platform"])):
        raise Conflict("Esta versão já está cadastrada para esta plataforma.")
    release = Release(**fields, created_by=actor_id)
    db.add(release)
    db.flush()
    audit.record(db, "release.create", actor_id=actor_id, target_type="release", target_id=release.id,
                 detail={"version": release.version}, ip=ip)
    return release


def update(db: Db, release_id: int, data: dict[str, Any], *, actor_id: int | None, ip: str = "") -> Release:
    release = get(db, release_id)
    fields = _clean({**to_dict(release), **data})
    clash = db.scalar(select(Release.id).where(Release.version == fields["version"],
                                               Release.platform == fields["platform"], Release.id != release.id))
    if clash:
        raise Conflict("Esta versão já está cadastrada para esta plataforma.")
    for key, value in fields.items():
        setattr(release, key, value)
    release.updated_at = utcnow()
    audit.record(db, "release.update", actor_id=actor_id, target_type="release", target_id=release.id, ip=ip)
    return release


def publish(db: Db, release_id: int, *, actor_id: int | None, ip: str = "") -> Release:
    release = get(db, release_id)
    if not RELEASE_PUBLICATION_ENABLED:
        audit.record(db, "release.publish_blocked", actor_id=actor_id, target_type="release", target_id=release.id, ip=ip)
        db.commit()
        error = Conflict(BLOCK_REASON, details={"reason": "licencas_pendentes"})
        error.code = "publicacao_bloqueada"
        raise error
    release.status, release.published_at, release.updated_at = "published", utcnow(), utcnow()   # pragma: no cover
    audit.record(db, "release.publish", actor_id=actor_id, target_type="release", target_id=release.id, ip=ip)
    return release


def remove(db: Db, release_id: int, *, actor_id: int | None, ip: str = "") -> None:
    release = get(db, release_id)
    release.deleted_at = utcnow()
    release.version = f"{release.version}--excluida-{release.id}"[:40]
    audit.record(db, "release.delete", actor_id=actor_id, target_type="release", target_id=release.id, ip=ip)


def public_list(db: Db) -> list[Release]:
    """Só versões publicadas. Com a publicação bloqueada, esta lista é sempre vazia."""
    return list(db.scalars(select(Release).where(Release.status == "published", Release.deleted_at.is_(None))
                           .order_by(Release.published_at.desc())))
