import pytest
from sqlalchemy import select

from safra_portal.domain.blocks import render_inline, validate_blocks
from safra_portal.domain.models import AuditEvent, Content, ContentVersion, PublicationEvent
from safra_portal.infrastructure.db import transaction

from conftest import page_data


def test_draft_is_not_public_and_published_content_is(portal):
    """Critérios 10 e 11."""
    admin = portal.login("administrador")
    page = admin.post("/pages", json=page_data(title="Página nova", summary="Um resumo público")).json()
    assert page["status"] == "draft" and page["public_path"] is None
    assert portal.public.get("/pagina-de-teste").status_code == 404
    assert "pagina-de-teste" not in portal.public.get("/sitemap.xml").text
    assert admin.post(f"/pages/{page['id']}/publish").json()["public_path"] == "/pagina-de-teste"
    public = portal.public.get("/pagina-de-teste")
    assert public.status_code == 200
    assert "<h1>Página nova</h1>" in public.text and "Texto inicial." in public.text and "Um resumo público" in public.text
    assert "/pagina-de-teste</loc>" in portal.public.get("/sitemap.xml").text
    assert admin.post(f"/pages/{page['id']}/unpublish").status_code == 200
    assert portal.public.get("/pagina-de-teste").status_code == 404


def test_edits_after_publishing_stay_private_until_published_again(portal):
    admin = portal.login("administrador")
    page = admin.post("/pages", json=page_data()).json()
    admin.post(f"/pages/{page['id']}/publish")
    changed = page_data(title="Título secreto", blocks=[{"type": "paragraph", "text": "Rascunho confidencial."}])
    saved = admin.put(f"/pages/{page['id']}", json={**changed, "lock_version": 1}).json()
    assert saved["has_unpublished_changes"] is True and saved["status"] == "published"
    public = portal.public.get("/pagina-de-teste").text
    assert "Texto inicial." in public and "confidencial" not in public and "secreto" not in public
    admin.post(f"/pages/{page['id']}/publish")
    assert "Rascunho confidencial." in portal.public.get("/pagina-de-teste").text


def test_versions_are_kept_and_an_old_one_can_be_restored(portal):
    """Critério 12."""
    admin = portal.login("administrador")
    page = admin.post("/pages", json=page_data(title="Versão um")).json()
    for number, title in ((1, "Versão dois"), (2, "Versão três")):
        page = admin.put(f"/pages/{page['id']}", json={**page_data(title=title), "lock_version": number}).json()
    versions = admin.get(f"/pages/{page['id']}/versions").json()
    assert [v["number"] for v in versions] == [3, 2, 1] and [v["title"] for v in versions] == ["Versão três", "Versão dois", "Versão um"]
    first = versions[-1]
    assert admin.get(f"/pages/{page['id']}/versions/{first['id']}").json()["title"] == "Versão um"
    restored = admin.post(f"/pages/{page['id']}/versions/{first['id']}/restore").json()
    assert restored["title"] == "Versão um" and restored["status"] == "draft"          # restaurar não publica
    after = admin.get(f"/pages/{page['id']}/versions").json()
    assert len(after) == 4 and after[0]["kind"] == "restore" and after[0]["note"] == "restaurada da versão 1"
    assert [v["title"] for v in after[1:]] == ["Versão três", "Versão dois", "Versão um"]   # o histórico não se perde
    other = admin.post("/pages", json=page_data("outra")).json()
    assert admin.post(f"/pages/{other['id']}/versions/{first['id']}/restore").status_code == 404   # versão de outro conteúdo


def test_simultaneous_editing_never_overwrites_silently(portal):
    admin = portal.login("administrador")
    editor = portal.login("editor")
    page = admin.post("/pages", json=page_data()).json()
    first = editor.put(f"/pages/{page['id']}", json={**page_data(title="Do editor"), "lock_version": 1})
    assert first.status_code == 200
    stale = admin.put(f"/pages/{page['id']}", json={**page_data(title="Do administrador"), "lock_version": 1})
    assert stale.status_code == 409
    assert stale.json()["error"]["details"] == {"current_lock_version": 2, "updated_by": "Editor"}
    assert admin.get(f"/pages/{page['id']}").json()["title"] == "Do editor"


def test_delete_needs_confirmation_is_logical_and_frees_the_address(portal):
    admin = portal.login("administrador")
    page = admin.post("/pages", json=page_data()).json()
    admin.post(f"/pages/{page['id']}/publish")
    assert admin.delete(f"/pages/{page['id']}", json={"confirm_slug": "errado"}).status_code == 422
    assert portal.public.get("/pagina-de-teste").status_code == 200
    assert admin.delete(f"/pages/{page['id']}", json={"confirm_slug": "pagina-de-teste"}).status_code == 200
    assert portal.public.get("/pagina-de-teste").status_code == 404
    assert admin.get(f"/pages/{page['id']}").status_code == 404
    with transaction(portal.app.state.session_factory) as db:
        row = db.get(Content, page["id"])
        assert row is not None and row.deleted_at is not None                       # o registro continua no banco
        assert db.scalar(select(ContentVersion).where(ContentVersion.content_id == page["id"])) is not None
    assert admin.post("/pages", json=page_data()).status_code == 201                # o endereço pode ser reusado


def test_publication_history_and_audit_record_who_did_what(portal):
    admin = portal.login("administrador")
    page = admin.post("/pages", json=page_data()).json()
    admin.post(f"/pages/{page['id']}/publish")
    admin.post(f"/pages/{page['id']}/unpublish")
    with transaction(portal.app.state.session_factory) as db:
        events = db.scalars(select(PublicationEvent).where(PublicationEvent.content_id == page["id"])
                            .order_by(PublicationEvent.id)).all()
        assert [e.action for e in events] == ["create", "publish", "unpublish"]
        assert {e.actor_id for e in events} == {admin.session["user"]["id"]}
        actions = [a.action for a in db.scalars(select(AuditEvent).where(
                AuditEvent.target_type == "page", AuditEvent.target_id == str(page["id"])).order_by(AuditEvent.id))]
    assert actions == ["page.create", "page.publish", "page.unpublish"]
    listed = admin.get("/audit").json()
    assert listed[0]["action"] == "page.unpublish" and listed[0]["actor"] == "Administrador"
    assert "Texto inicial" not in str(listed)                                        # a auditoria não guarda o conteúdo


@pytest.mark.parametrize("slug", ["", "Com Maiúscula", "com espaço", "acentuação", "-inicio", "fim-", "a--b", "x" * 81,
                                  "admin", "static", "media", "healthz", "../etc", "a/b"])
def test_invalid_and_reserved_addresses_are_rejected(portal, slug):
    admin = portal.login("administrador")
    assert admin.post("/pages", json=page_data(slug)).status_code == 422


def test_duplicate_address_is_a_conflict_within_the_same_type_only(portal):
    admin = portal.login("administrador")
    assert admin.post("/pages", json=page_data("repetido")).status_code == 201
    assert admin.post("/pages", json=page_data("repetido")).status_code == 409
    assert admin.post("/news", json=page_data("repetido")).status_code == 201


XSS = ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "\"><svg onload=alert(1)>",
       "[clique](javascript:alert(1))", "[x](data:text/html,<script>alert(1)</script>)", "{{ 7*7 }}", "{% include 'base.html' %}",
       "[a](https://exemplo.test/\"onmouseover=\"alert(1))", "**<b onmouseover=alert(1)>negrito</b>**"]


@pytest.mark.parametrize("payload", XSS)
def test_text_typed_in_the_cms_never_becomes_markup_or_script(portal, payload):
    admin = portal.login("administrador")
    data = page_data(title=payload, summary=payload, seo_title=payload, seo_description=payload, blocks=[
        {"type": "heading", "level": 2, "text": payload}, {"type": "paragraph", "text": payload},
        {"type": "list", "ordered": False, "items": [payload]}, {"type": "quote", "text": payload, "cite": payload},
        {"type": "callout", "tone": "info", "title": payload, "text": payload},
        {"type": "cards", "items": [{"title": payload, "text": payload, "tag": ""}]},
        {"type": "faq", "items": [{"question": payload, "answer": payload}]}])
    page = admin.post("/pages", json=data)
    assert page.status_code == 201, page.text
    admin.post(f"/pages/{page.json()['id']}/publish")
    html = portal.public.get("/pagina-de-teste").text
    assert "<script" not in html and "<svg" not in html.replace('<svg class="simbolo', "") and "<img src=x" not in html
    assert "onerror=" not in html.replace("onerror=alert(1)&gt;", "") or "&lt;img" in html
    assert 'href="javascript:' not in html and 'href="data:' not in html
    assert "49" not in html.split("<main")[1].split("</main>")[0] or "7*7" in html      # modelo não é avaliado
    assert "onmouseover=\"alert" not in html and "<b onmouseover" not in html


def test_inline_markup_subset():
    assert str(render_inline("**forte** e *ênfase* e `código`")) == "<strong>forte</strong> e <em>ênfase</em> e <code>código</code>"
    assert str(render_inline("[site](https://exemplo.test/a?b=1&c=2)")) == (
        '<a href="https://exemplo.test/a?b=1&amp;c=2" rel="noopener noreferrer">site</a>')
    assert str(render_inline("[interna](/sobre)")) == '<a href="/sobre">interna</a>'
    assert str(render_inline("[x](javascript:alert(1))")) == "[x](javascript:alert(1))"
    assert str(render_inline("[x](//evil.example)")) == "[x](//evil.example)"
    assert str(render_inline("a < b & c")) == "a &lt; b &amp; c"
    assert str(render_inline("linha 1\nlinha 2")) == "linha 1<br>linha 2"


@pytest.mark.parametrize("blocks", [
    [{"type": "html", "html": "<b>x</b>"}], [{"type": "paragraph", "text": "x", "html": "<b>"}],
    [{"type": "button", "label": "x", "href": "javascript:alert(1)"}], [{"type": "heading", "level": 1, "text": "x"}],
    [{"type": "image", "media_id": 0}], [{"type": "paragraph", "text": ""}], [{"type": "paragraph", "text": "x" * 4001}],
    [{"type": "cards", "items": [{"title": "a", "text": "b", "tag": "pronto"}]}], [{"type": "paragraph", "text": "x"}] * 201,
    "não é uma lista", [{"sem": "tipo"}]])
def test_only_known_blocks_with_known_fields_are_accepted(blocks):
    with pytest.raises(Exception):
        validate_blocks(blocks)


def test_content_that_references_missing_media_or_category_is_rejected(portal):
    admin = portal.login("administrador")
    assert admin.post("/pages", json=page_data(blocks=[{"type": "image", "media_id": 12345}])).status_code == 422
    assert admin.post("/pages", json=page_data(cover_media_id=12345)).status_code == 422
    assert admin.post("/news", json=page_data(category_id=12345)).status_code == 422


def test_news_with_category_appears_in_the_list_and_on_the_home(portal):
    admin = portal.login("administrador")
    category = admin.post("/categories", json={"slug": "projeto", "name": "Projeto"}).json()
    news = admin.post("/news", json=page_data("noticia-nova", "Notícia nova", category_id=category["id"])).json()
    assert "Notícia nova" not in portal.public.get("/atualizacoes").text
    admin.post(f"/news/{news['id']}/publish")
    assert "Notícia nova" in portal.public.get("/atualizacoes").text and "Notícia nova" in portal.public.get("/").text
    item = portal.public.get("/atualizacoes/noticia-nova")
    assert item.status_code == 200 and "Projeto" in item.text and 'property="og:type" content="article"' in item.text
    assert portal.public.get("/noticia-nova").status_code == 404                    # notícia não é página


def test_preview_needs_a_session_and_is_never_indexed_or_cached(portal):
    admin = portal.login("administrador")
    page = admin.post("/pages", json=page_data(title="Só no rascunho")).json()
    assert portal.public.get(page["preview_path"]).status_code == 401
    preview = admin.client.get(page["preview_path"])
    assert preview.status_code == 200 and "Só no rascunho" in preview.text
    assert "Pré-visualização do rascunho" in preview.text and 'content="noindex, nofollow"' in preview.text
    assert preview.headers["cache-control"] == "no-store" and "rel=\"canonical\"" not in preview.text


def test_dashboard_reports_real_counts(portal):
    admin = portal.login("administrador")
    before = admin.get("/dashboard").json()
    page = admin.post("/pages", json=page_data()).json()
    after = admin.get("/dashboard").json()
    assert after["pages"]["draft"] == before["pages"]["draft"] + 1 and after["pages"]["published"] == before["pages"]["published"]
    admin.post(f"/pages/{page['id']}/publish")
    final = admin.get("/dashboard").json()
    assert final["pages"]["published"] == before["pages"]["published"] + 1
    assert final["recent_changes"][0]["slug"] == "pagina-de-teste" and final["activity"][0]["action"] == "page.publish"
    assert final["downloads_blocked"] is True
    editor = portal.login("editor")
    assert all(a["actor_id"] == editor.session["user"]["id"] for a in editor.get("/dashboard").json()["activity"])
