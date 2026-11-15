"""Rotas públicas. Toda leitura de conteúdo passa por `cms.content.public_*`, que só devolve versões publicadas."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from safra_foundation.errors import NotFound

from .. import __version__
from ..auth.deps import get_db, require
from ..auth.service import Identity
from ..cms import content, homepage, releases
from ..domain import blocks as blocks_module
from ..domain.models import Category, Content, Media
from .render import FOOTER_NAVIGATION, NAVIGATION, render

router = APIRouter()
preview_router = APIRouter()          # registrado antes da montagem de /admin
PUBLIC_CACHE = "public, max-age=60"
NEWS_PER_PAGE = 10
SPECIAL_PAGES = {"atualizacoes": "news_list.html", "downloads": "downloads.html", "contato": "contact.html"}


def _media_map(db: Db, ids: set[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    rows = db.scalars(select(Media).where(Media.id.in_(ids), Media.deleted_at.is_(None)))
    return {m.id: {"url": f"/media/{m.stored_name}", "alt": m.alt_text, "width": m.width, "height": m.height} for m in rows}


def _published_slugs(db: Db) -> set[str]:
    return set(db.scalars(select(Content.slug).where(Content.type == "page", Content.status == "published",
                                                     Content.deleted_at.is_(None))))


def base_context(request: Request, db: Db, *, path: str, title: str, description: str = "", og_type: str = "website",
                 image_url: str = "", noindex: bool = False) -> dict[str, Any]:
    settings = request.app.state.settings
    slugs = _published_slugs(db)
    return {
        "site": homepage.load(db, homepage.SITE_KEY),
        "nav": [(f"/{slug}", label) for slug, label in NAVIGATION if slug in slugs],
        "footer_nav": [(f"/{slug}", label) for slug, label in FOOTER_NAVIGATION if slug in slugs],
        "current_path": path,
        "seo": {"title": f"{title} — SAFRA" if title and title != "SAFRA" else "SAFRA",
                "description": description, "canonical": settings.public_base_url + path, "type": og_type,
                "image": settings.public_base_url + image_url if image_url else "", "noindex": noindex},
        "version": __version__,
    }


def _html(request: Request, template: str, context: dict[str, Any], *, status: int = 200,
          cache: str = PUBLIC_CACHE) -> HTMLResponse:
    body = render(request.app.state.templates, template, **context)
    return HTMLResponse(body, status_code=status, headers={"Cache-Control": cache})


def _page_context(request: Request, db: Db, item: content.Published, *, path: str, noindex: bool = False) -> dict[str, Any]:
    media = _media_map(db, blocks_module.media_ids(item.blocks) | ({item.cover_media_id} if item.cover_media_id else set()))
    cover = media.get(item.cover_media_id) if item.cover_media_id else None
    context = base_context(request, db, path=path, title=item.seo_title or item.title,
                           description=item.seo_description or item.summary,
                           og_type="article" if item.type == "news" else "website",
                           image_url=cover["url"] if cover else "", noindex=noindex)
    category = db.get(Category, item.category_id) if item.category_id else None
    context.update(page=item, media=media, cover=cover,
                   category=category if category is not None and category.deleted_at is None else None)
    return context


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request, db: Db = Depends(get_db)) -> HTMLResponse:
    home_data = homepage.load(db, homepage.HOMEPAGE_KEY)
    image = _media_map(db, {home_data["image_media_id"]}) if home_data.get("image_media_id") else {}
    context = base_context(request, db, path="/", title="SAFRA", description=home_data.get("subtitle", ""),
                           image_url=next(iter(image.values()))["url"] if image else "")
    context.update(home=home_data, hero_image=next(iter(image.values())) if image else None,
                   news=content.public_list(db, "news", limit=home_data.get("featured_news", 3)))
    return _html(request, "home.html", context)


@router.get("/atualizacoes/{slug}", response_class=HTMLResponse, include_in_schema=False)
def news_item(slug: str, request: Request, db: Db = Depends(get_db)) -> HTMLResponse:
    item = content.public_get(db, "news", slug)
    if item is None:
        raise NotFound()
    return _html(request, "news_item.html", _page_context(request, db, item, path=f"/atualizacoes/{slug}"))


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap(request: Request, db: Db = Depends(get_db)) -> Response:
    base = request.app.state.settings.public_base_url
    entries = [(base + "/", None)]
    entries += [(f"{base}/{p.slug}", p.updated_at) for p in content.public_list(db, "page", limit=1000)]
    entries += [(f"{base}/atualizacoes/{n.slug}", n.updated_at) for n in content.public_list(db, "news", limit=5000)]
    body = render(request.app.state.templates, "sitemap.xml", entries=entries)
    return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=300"})


@router.get("/robots.txt", include_in_schema=False)
def robots(request: Request) -> PlainTextResponse:
    base = request.app.state.settings.public_base_url
    return PlainTextResponse(f"User-agent: *\nAllow: /\nDisallow: /admin\n\nSitemap: {base}/sitemap.xml\n",
                             headers={"Cache-Control": "public, max-age=3600"})


@router.get("/healthz", include_in_schema=False)
def healthz(request: Request) -> dict[str, str]:
    """Sem sessão: só o estado geral, o serviço e a versão."""
    return {"status": request.app.state.health.report().status, "service": "portal", "version": __version__}


@router.get("/media/{folder}/{name}", include_in_schema=False)
def media_file(folder: str, name: str, request: Request, db: Db = Depends(get_db)) -> FileResponse:
    path, media = request.app.state.media.public_file(db, f"{folder}/{name}")
    return FileResponse(path, media_type=media.content_type,
                        headers={"Cache-Control": "public, max-age=31536000, immutable",
                                 "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"})


@preview_router.get("/admin/preview/{plural}/{item_id}", response_class=HTMLResponse, include_in_schema=False)
def preview(plural: str, item_id: int, request: Request, _: Identity = Depends(require("content.read")),
            db: Db = Depends(get_db)) -> HTMLResponse:
    """Pré-visualização do RASCUNHO. Exige sessão com permissão, não é indexável e nunca fica em cache."""
    content_type = {"pages": "page", "news": "news"}.get(plural)
    if content_type is None:
        raise NotFound()
    draft = content.get(db, content_type, item_id)
    item = content.Published(draft.id, draft.type, draft.slug, draft.title, draft.summary, draft.blocks,
                             draft.seo_title, draft.seo_description, draft.cover_media_id, draft.category_id,
                             None, None)
    context = _page_context(request, db, item, path=f"/admin/preview/{plural}/{item_id}", noindex=True)
    context["preview"] = True
    template = "news_item.html" if content_type == "news" else "page.html"
    return _html(request, template, context, cache="no-store")


@router.get("/{slug}", response_class=HTMLResponse, include_in_schema=False)
def page(slug: str, request: Request, pagina: int = 1, db: Db = Depends(get_db)) -> HTMLResponse:
    item = content.public_get(db, "page", slug)
    if item is None:
        raise NotFound()
    context = _page_context(request, db, item, path=f"/{slug}")
    if slug == "atualizacoes":
        number = max(1, min(pagina, 500))
        total = content.public_count(db, "news")
        context.update(news=content.public_list(db, "news", limit=NEWS_PER_PAGE, offset=(number - 1) * NEWS_PER_PAGE),
                       page_number=number, has_next=number * NEWS_PER_PAGE < total, has_previous=number > 1)
    elif slug == "downloads":
        context.update(releases=releases.public_list(db), publication_enabled=releases.RELEASE_PUBLICATION_ENABLED)
    return _html(request, SPECIAL_PAGES.get(slug, "page.html"), context)
