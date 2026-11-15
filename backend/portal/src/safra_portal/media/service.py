"""Imagens do site.

Defesas (PORTAL_THREAT_MODEL.md, "Upload malicioso" e "Path traversal"):
* o tipo é decidido pelos primeiros bytes do arquivo; a extensão e o tipo informados pelo navegador são ignorados;
* só PNG, JPEG, GIF e WebP — SVG é recusado porque pode carregar script;
* o nome no disco é gerado aqui (aleatório); o nome original fica só como rótulo, depois de higienizado;
* o arquivo é servido apenas se estiver registrado no banco, com o tipo gravado e ``nosniff``.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import struct
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from safra_foundation.errors import Conflict, InvalidInput, NotFound

from ..cms import audit
from ..domain import blocks as blocks_module
from ..domain.models import Content, ContentVersion, Media, SiteSetting, as_utc, utcnow

EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
MAX_DIMENSION = 8000
_STORED = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{32}\.(png|jpg|gif|webp)$")
_UNSAFE_NAME = re.compile(r"[^\w.\- ]+", re.UNICODE)


def sniff(data: bytes) -> str | None:
    """Tipo real pelo cabeçalho do arquivo, ou ``None`` se não for uma imagem aceita."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def dimensions(data: bytes, content_type: str) -> tuple[int, int] | None:
    try:
        if content_type == "image/png" and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        if content_type == "image/gif":
            return struct.unpack("<HH", data[6:10])
        if content_type == "image/webp":
            kind = data[12:16]
            if kind == b"VP8X":
                return (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
            if kind == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
            if kind == b"VP8 ":
                width, height = struct.unpack("<HH", data[26:30])
                return (width & 0x3FFF, height & 0x3FFF)
        if content_type == "image/jpeg":
            position = 2
            while position + 9 < len(data):
                if data[position] != 0xFF:
                    position += 1
                    continue
                marker = data[position + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    height, width = struct.unpack(">HH", data[position + 5:position + 9])
                    return (width, height)
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    position += 2
                    continue
                position += 2 + struct.unpack(">H", data[position + 2:position + 4])[0]
    except (struct.error, IndexError):
        return None
    return None


def clean_name(name: str) -> str:
    """Rótulo exibível: sem caminho, sem caracteres de controle."""
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = _UNSAFE_NAME.sub("_", name).strip(" .")
    return name[:200] or "imagem"


def to_dict(media: Media) -> dict[str, Any]:
    return {"id": media.id, "url": f"/media/{media.stored_name}", "original_name": media.original_name,
            "content_type": media.content_type, "size": media.size, "width": media.width, "height": media.height,
            "alt_text": media.alt_text, "category": media.category, "created_at": as_utc(media.created_at).isoformat()}


class MediaService:
    def __init__(self, directory: Path, max_bytes: int) -> None:
        self.directory, self.max_bytes = directory, max_bytes

    def path_of(self, stored_name: str) -> Path:
        if not _STORED.match(stored_name):                        # nunca monta caminho com texto vindo de fora
            raise NotFound("Arquivo não encontrado.")
        return self.directory / stored_name

    def store(self, db: Db, data: bytes, *, original_name: str, alt_text: str = "", category: str = "",
              actor_id: int | None, ip: str = "") -> Media:
        if not data:
            raise InvalidInput("O arquivo está vazio.")
        if len(data) > self.max_bytes:
            raise InvalidInput(f"O arquivo passa do limite de {self.max_bytes // 1024} KiB.", details={"field": "file"})
        content_type = sniff(data)
        if content_type is None:
            raise InvalidInput("Tipo de arquivo não aceito. Envie PNG, JPEG, GIF ou WebP.", details={"field": "file"})
        size = dimensions(data, content_type)
        if size is None or not (0 < size[0] <= MAX_DIMENSION and 0 < size[1] <= MAX_DIMENSION):
            raise InvalidInput("A imagem está corrompida ou tem dimensões fora do permitido.", details={"field": "file"})
        if len(alt_text) > 300 or len(category) > 64:
            raise InvalidInput("Texto alternativo ou categoria longos demais.")
        token = secrets.token_hex(16)
        stored_name = f"{token[:2]}/{token}.{EXTENSIONS[content_type]}"
        target = self.directory / stored_name
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".parcial")
        partial.write_bytes(data)
        partial.replace(target)
        media = Media(stored_name=stored_name, original_name=clean_name(original_name), content_type=content_type,
                      size=len(data), width=size[0], height=size[1], sha256=hashlib.sha256(data).hexdigest(),
                      alt_text=alt_text.strip(), category=category.strip(), created_by=actor_id)
        db.add(media)
        db.flush()
        audit.record(db, "media.upload", actor_id=actor_id, target_type="media", target_id=media.id,
                     detail={"content_type": content_type, "size": len(data)}, ip=ip)
        return media

    def get(self, db: Db, media_id: int) -> Media:
        media = db.get(Media, media_id)
        if media is None or media.deleted_at is not None:
            raise NotFound("Imagem não encontrada.")
        return media

    def list(self, db: Db, *, category: str = "") -> list[Media]:
        query = select(Media).where(Media.deleted_at.is_(None))
        if category:
            query = query.where(Media.category == category)
        return list(db.scalars(query.order_by(Media.created_at.desc()).limit(500)))

    def update(self, db: Db, media_id: int, *, alt_text: str | None, category: str | None,
               actor_id: int | None, ip: str = "") -> Media:
        media = self.get(db, media_id)
        if alt_text is not None:
            if len(alt_text) > 300:
                raise InvalidInput("O texto alternativo pode ter até 300 caracteres.", details={"field": "alt_text"})
            media.alt_text = alt_text.strip()
        if category is not None:
            if len(category) > 64:
                raise InvalidInput("A categoria pode ter até 64 caracteres.", details={"field": "category"})
            media.category = category.strip()
        audit.record(db, "media.update", actor_id=actor_id, target_type="media", target_id=media.id, ip=ip)
        return media

    def usage(self, db: Db, media_id: int) -> list[str]:
        """Onde a imagem é usada: rascunhos, versões publicadas e página inicial."""
        used: list[str] = []
        contents = db.scalars(select(Content).where(Content.deleted_at.is_(None)))
        for content in contents:
            in_draft = content.cover_media_id == media_id or media_id in blocks_module.media_ids(content.blocks)
            published = db.get(ContentVersion, content.published_version_id) if content.published_version_id else None
            in_published = published is not None and (published.cover_media_id == media_id
                                                      or media_id in blocks_module.media_ids(published.blocks))
            if in_draft or in_published:
                used.append(f"{content.type}:{content.slug}")
        homepage = db.get(SiteSetting, "homepage")
        if homepage is not None and homepage.value.get("image_media_id") == media_id:
            used.append("homepage")
        return used

    def remove(self, db: Db, media_id: int, *, actor_id: int | None, ip: str = "") -> None:
        """Remoção controlada: recusa se a imagem estiver em uso; o arquivo sai do ar e é apagado do disco."""
        media = self.get(db, media_id)
        used = self.usage(db, media_id)
        if used:
            raise Conflict("A imagem está em uso e não pode ser removida.", details={"used_in": used})
        media.deleted_at = utcnow()
        audit.record(db, "media.delete", actor_id=actor_id, target_type="media", target_id=media.id, ip=ip)
        db.flush()
        self.path_of(media.stored_name).unlink(missing_ok=True)

    def public_file(self, db: Db, stored_name: str) -> tuple[Path, Media]:
        """Só entrega arquivo registrado, não removido e existente."""
        path = self.path_of(stored_name)
        media = db.scalar(select(Media).where(Media.stored_name == stored_name, Media.deleted_at.is_(None)))
        if media is None or not path.is_file():
            raise NotFound("Arquivo não encontrado.")
        return path, media
