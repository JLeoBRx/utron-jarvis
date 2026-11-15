import re

import pytest


PAGES = ["/", "/sobre", "/funcionalidades", "/inteligencia-artificial", "/seguranca-e-privacidade", "/atualizacoes",
         "/documentacao", "/downloads", "/perguntas-frequentes", "/contato", "/politica-de-privacidade", "/termos-de-uso"]


@pytest.mark.parametrize("path", PAGES)
def test_the_twelve_public_pages_are_served_with_seo_and_semantics(portal, path):
    response = portal.public.get(path)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    html = response.text
    assert '<html lang="pt-BR">' in html and html.count("<h1") == 1 and "<main id=\"conteudo\"" in html
    assert re.search(r"<title>[^<]{3,70}</title>", html)
    assert f'<link rel="canonical" href="{portal.origin}{path}">' in html
    assert 'property="og:title"' in html and 'property="og:url"' in html and 'name="viewport"' in html
    if path != "/":
        assert re.search(r'<meta name="description" content="[^"]{10,300}">', html)
    assert 'href="#conteudo"' in html and "<nav" in html and "<footer" in html and "<header" in html


@pytest.mark.parametrize("path", PAGES)
def test_public_pages_have_no_script_no_cookie_and_no_external_resource(portal, path):
    response = portal.public.get(path)
    assert "<script" not in response.text and "set-cookie" not in response.headers
    assert not re.findall(r'(?:src|href)="(?:https?:)?//(?!127\.0\.0\.1)', response.text.replace(portal.origin, ""))
    assert " style=" not in response.text and " onclick=" not in response.text


def test_security_headers(portal):
    headers = portal.public.get("/").headers
    csp = headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp and "*" not in csp
    assert headers["x-content-type-options"] == "nosniff" and headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["x-safra-correlacao"].startswith("c-")


def test_unknown_address_gets_a_real_404_page(portal):
    for path in ("/nao-existe", "/atualizacoes/nao-existe", "/a/b/c"):
        response = portal.public.get(path)
        assert response.status_code == 404 and "Página não encontrada" in response.text
        assert 'content="noindex, nofollow"' in response.text and response.headers["cache-control"] == "no-store"
    api = portal.public.get("/admin/api/nao-existe")
    assert api.status_code == 404 and api.json()["error"]["code"] == "nao_encontrado"       # a API responde em JSON


def test_sitemap_and_robots(portal):
    sitemap = portal.public.get("/sitemap.xml")
    assert sitemap.headers["content-type"].startswith("application/xml")
    locations = re.findall(r"<loc>([^<]+)</loc>", sitemap.text)
    assert f"{portal.origin}/" in locations and f"{portal.origin}/sobre" in locations
    assert f"{portal.origin}/atualizacoes/safra-4-comeca-a-reconstrucao" in locations
    assert not any("/admin" in location for location in locations)
    robots = portal.public.get("/robots.txt").text
    assert "Disallow: /admin" in robots and f"Sitemap: {portal.origin}/sitemap.xml" in robots


def test_navigation_shows_only_what_is_published(portal):
    admin = portal.login("administrador")
    assert 'href="/documentacao"' in portal.public.get("/").text
    page = next(p for p in admin.get("/pages").json() if p["slug"] == "documentacao")
    admin.post(f"/pages/{page['id']}/unpublish")
    assert 'href="/documentacao"' not in portal.public.get("/sobre").text
    assert portal.public.get("/documentacao").status_code == 404


def test_homepage_is_driven_by_the_admin(portal):
    admin = portal.login("administrador")
    home = admin.get("/homepage").json()
    home["title"], home["subtitle"] = "SAFRA em teste", "Subtítulo alterado pelo painel"
    home["buttons"] = [{"label": "Botão novo", "href": "/sobre"}]
    home["sections"] = [s for s in reversed(home["sections"]) if s["key"] != "security"]
    assert admin.put("/homepage", json=home).status_code == 200
    html = portal.public.get("/").text
    assert "SAFRA em teste" in html and "Subtítulo alterado pelo painel" in html and "Botão novo" in html
    assert 'id="secao-security"' not in html
    order = re.findall(r'id="secao-([a-z_]+)"', html)
    assert order == [s["key"] for s in home["sections"]]
    bad = {**home, "buttons": [{"label": "x", "href": "javascript:alert(1)"}]}
    assert admin.put("/homepage", json=bad).status_code == 422
    assert admin.put("/homepage", json={**home, "campo_inventado": 1}).status_code == 422


def test_site_info_and_contact_are_public_settings(portal):
    admin = portal.login("administrador")
    assert "ainda não foram publicados" in portal.public.get("/contato").text
    site = admin.get("/site").json()
    site["contact_email"] = "contato@exemplo.test"
    site["footer_links"] = [{"label": "Repositório", "href": "https://exemplo.test/repo"}]
    assert admin.put("/site", json=site).status_code == 200
    assert 'href="mailto:contato@exemplo.test"' in portal.public.get("/contato").text
    assert 'href="https://exemplo.test/repo" rel="noopener noreferrer"' in portal.public.get("/").text


def test_installer_publication_is_blocked_in_code(portal):
    from safra_portal.cms import releases
    assert releases.RELEASE_PUBLICATION_ENABLED is False
    admin = portal.login("administrador")
    release = admin.post("/releases", json={"version": "4.0.0-beta.1", "channel": "beta", "notes": "Primeira beta."})
    assert release.status_code == 201 and release.json()["status"] == "draft"
    blocked = admin.post(f"/releases/{release.json()['id']}/publish")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "publicacao_bloqueada"
    listing = admin.get("/releases").json()
    assert listing["publication_enabled"] is False and listing["items"][0]["status"] == "draft"
    public = portal.public.get("/downloads").text
    assert "Ainda não há instaladores publicados" in public and "4.0.0-beta.1" not in public
    assert admin.post("/releases", json={"version": "não é versão"}).status_code == 422
    assert admin.post("/releases", json={"version": "4.0.0-beta.1", "channel": "beta"}).status_code == 409


def test_requests_for_another_host_are_refused(portal):
    response = portal.public.get("/", headers={"host": "evil.example"})
    assert response.status_code == 403 and "<h1>" in response.text       # página de erro, não a página inicial


def test_health_endpoint_says_only_the_minimum(portal):
    assert set(portal.public.get("/healthz").json()) == {"status", "service", "version"}
    assert portal.public.get("/healthz").json()["service"] == "portal"


def test_seed_is_honest_about_what_is_not_ready(portal):
    assert "ainda não está disponível para uso" in portal.public.get("/sobre").text
    assert "Texto-modelo" in portal.public.get("/politica-de-privacidade").text
    assert "Texto-modelo" in portal.public.get("/termos-de-uso").text
    tags = re.findall(r'class="selo selo--([a-z-]+)"', portal.public.get("/funcionalidades").text)
    assert tags.count("implementado") == 1 and "em-desenvolvimento" in tags and "planejado" in tags


def test_admin_shell_reports_when_the_panel_is_not_built(tmp_path):
    from safra_portal.config import load_settings
    from conftest import Portal
    settings = load_settings(env={}, environment="test", data_dir=tmp_path / "p", log_to_file=False,
                             admin_dist=tmp_path / "nao-existe")
    portal = Portal(settings)
    try:
        assert portal.public.get("/admin", follow_redirects=False).status_code == 308
        response = portal.public.get("/admin/")
        assert response.status_code == 503 and "ainda não foi compilado" in response.text
    finally:
        portal.close()
