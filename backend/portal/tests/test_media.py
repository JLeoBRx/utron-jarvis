import pytest

from safra_portal.media.service import clean_name, dimensions, sniff

from conftest import make_png, page_data

PNG = make_png(4, 3)


def _upload(session, data: bytes, filename: str = "foto.png", **params):
    return session.post("/media", content=data, params={"filename": filename, **params},
                        headers={"Content-Type": "application/octet-stream"})


def test_valid_image_is_stored_with_a_server_generated_name_and_served_safely(portal):
    admin = portal.login("administrador")
    response = _upload(admin, PNG, "Minha Foto.png", alt_text="Um quadrado vermelho", category="galeria")
    assert response.status_code == 201, response.text
    media = response.json()
    assert (media["content_type"], media["width"], media["height"], media["size"]) == ("image/png", 4, 3, len(PNG))
    assert media["alt_text"] == "Um quadrado vermelho" and "Minha" not in media["url"] and media["url"].endswith(".png")
    served = portal.public.get(media["url"])
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png" and served.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in served.headers["cache-control"]
    assert [m["id"] for m in admin.get("/media").json()] == [media["id"]]


INVALID = {
    "texto": b"apenas texto, nada de imagem",
    "html": b"<html><script>alert(1)</script></html>",
    "svg": b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>',
    "executavel": b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 200,
    "php": b"<?php system($_GET['c']); ?>",
    "zip": b"PK\x03\x04" + b"\x00" * 100,
    "png-truncado": b"\x89PNG\r\n\x1a\n" + b"\x00" * 4,
    "png-gigante": make_png(1, 1)[:16] + (9000).to_bytes(4, "big") + (9000).to_bytes(4, "big") + make_png(1, 1)[24:],
    "vazio": b"",
}


@pytest.mark.parametrize("kind", sorted(INVALID))
def test_invalid_or_malicious_uploads_are_rejected(portal, kind):
    """Critério 13: o tipo é decidido pelo conteúdo; a extensão e o tipo informados não contam."""
    admin = portal.login("administrador")
    for filename, content_type in (("imagem.png", "image/png"), ("foto.jpg", "image/jpeg")):
        response = admin.post("/media", content=INVALID[kind], params={"filename": filename},
                              headers={"Content-Type": content_type})
        assert response.status_code == 422, (kind, response.status_code)
    assert admin.get("/media").json() == []
    assert not any(p.is_file() for p in portal.settings.media_dir.rglob("*")) if portal.settings.media_dir.exists() else True


def test_oversized_upload_is_rejected(portal):
    admin = portal.login("administrador")
    big = PNG + b"\x00" * (portal.settings.max_upload_bytes + 1)
    assert _upload(admin, big).status_code == 422
    assert admin.get("/media").json() == []


@pytest.mark.parametrize("filename", ["../../etc/passwd.png", "..\\..\\windows\\system32\\x.png", "/etc/shadow",
                                      "a\x00b.png", "<script>.png", "con.png", ""])
def test_the_original_name_never_becomes_a_path(portal, filename):
    admin = portal.login("administrador")
    media = _upload(admin, PNG, filename).json()
    assert "/" not in media["original_name"] and "\\" not in media["original_name"] and "<" not in media["original_name"]
    stored = [p for p in portal.settings.media_dir.rglob("*") if p.is_file()]
    assert len(stored) == 1 and portal.settings.media_dir in stored[0].parents


@pytest.mark.parametrize("path", ["/media/../portal.sqlite3", "/media/aa/../../portal.sqlite3", "/media/aa/portal.sqlite3",
                                  "/media/%2e%2e/%2e%2e/portal.sqlite3", "/media/aa/" + "0" * 32 + ".png",
                                  "/media/aa/..%2f..%2fportal.sqlite3", "/media/aa/x.png%00.txt"])
def test_only_registered_files_are_served(portal, path):
    portal.login("administrador")                                   # garante que o banco existe na pasta de dados
    assert (portal.settings.data_dir / "portal.sqlite3").is_file()
    response = portal.public.get(path)
    assert response.status_code == 404 and b"SQLite" not in response.content


def test_metadata_can_be_edited_and_media_in_use_cannot_be_removed(portal):
    admin = portal.login("administrador")
    media = _upload(admin, PNG).json()
    assert admin.patch(f"/media/{media['id']}", json={"alt_text": "Novo texto"}).json()["alt_text"] == "Novo texto"
    page = admin.post("/pages", json=page_data(blocks=[{"type": "image", "media_id": media["id"], "caption": "Legenda"}])).json()
    admin.post(f"/pages/{page['id']}/publish")
    public = portal.public.get("/pagina-de-teste").text
    assert f'src="{media["url"]}"' in public and 'alt="Novo texto"' in public and "Legenda" in public
    blocked = admin.delete(f"/media/{media['id']}")
    assert blocked.status_code == 409 and blocked.json()["error"]["details"] == {"used_in": ["page:pagina-de-teste"]}
    assert admin.get(f"/media/{media['id']}/usage").json() == {"used_in": ["page:pagina-de-teste"]}
    admin.delete(f"/pages/{page['id']}", json={"confirm_slug": "pagina-de-teste"})
    assert admin.delete(f"/media/{media['id']}").status_code == 200
    assert portal.public.get(media["url"]).status_code == 404
    assert not any(p.is_file() for p in portal.settings.media_dir.rglob("*"))


def test_sniffing_and_dimensions():
    assert sniff(PNG) == "image/png" and dimensions(PNG, "image/png") == (4, 3)
    gif = b"GIF89a" + (5).to_bytes(2, "little") + (7).to_bytes(2, "little") + b"\x00" * 10
    assert sniff(gif) == "image/gif" and dimensions(gif, "image/gif") == (5, 7)
    assert sniff(b"RIFF\x00\x00\x00\x00WEBPVP8X") == "image/webp"
    assert sniff(b"<svg") is None and sniff(b"") is None
    assert clean_name("../../a b.png") == "a b.png" and clean_name("") == "imagem"
