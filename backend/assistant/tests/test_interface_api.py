"""API local usada pela interface principal e pelo console: dados reais, nada simulado, e a guarda de origem."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from safra.api.app import create_app

ORIGIN_HEADERS = {}


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), base_url=f"http://127.0.0.1:{settings.api_port}") as test_client:
        test_client.headers["Origin"] = f"http://127.0.0.1:{settings.api_port}"
        yield test_client


def test_conversation_flow_stores_the_message_and_says_there_is_no_ai(client):
    created = client.post("/api/v1/conversations", json={}).json()
    assert created["title"] == "Conversa sem título" and created["message_count"] == 0
    sent = client.post(f"/api/v1/conversations/{created['id']}/messages", json={"content": "Organize minha semana"})
    assert sent.status_code == 201
    body = sent.json()
    assert body["message"]["role"] == "user" and body["message"]["content"] == "Organize minha semana"
    assert body["reply"]["status"] == "indisponivel" and body["reply"]["code"] == "gateway_ia_nao_implementado"
    full = client.get(f"/api/v1/conversations/{created['id']}").json()
    assert full["title"] == "Organize minha semana"                 # o início da primeira mensagem vira o título
    assert [m["role"] for m in full["messages"]] == ["user"]         # nenhuma resposta inventada
    listed = client.get("/api/v1/conversations").json()
    assert listed[0]["preview"] == "Organize minha semana" and listed[0]["message_count"] == 1


def test_conversation_search_archive_and_validation(client):
    first = client.post("/api/v1/conversations", json={"title": "Viagem"}).json()
    client.post(f"/api/v1/conversations/{first['id']}/messages", json={"content": "passagens para Recife"})
    client.post("/api/v1/conversations", json={"title": "Orçamento"})
    assert [c["title"] for c in client.get("/api/v1/conversations", params={"q": "recife"}).json()] == ["Viagem"]
    assert client.patch(f"/api/v1/conversations/{first['id']}", json={"archived": True}).json()["archived"] is True
    assert [c["title"] for c in client.get("/api/v1/conversations").json()] == ["Orçamento"]
    assert [c["title"] for c in client.get("/api/v1/conversations", params={"archived": True}).json()] == ["Viagem"]
    blocked = client.post(f"/api/v1/conversations/{first['id']}/messages", json={"content": "mais uma"})
    assert blocked.status_code == 409
    assert client.post(f"/api/v1/conversations/{first['id']}/messages", json={"content": ""}).status_code == 422
    assert client.post("/api/v1/conversations/999/messages", json={"content": "oi"}).status_code == 404
    assert client.post("/api/v1/conversations", json={"title": "x", "extra": 1}).status_code == 422
    assert client.post("/api/v1/conversations", json={"project_id": 42}).status_code == 422


def test_projects_with_counts_unique_names_and_archive(client):
    project = client.post("/api/v1/projects", json={"name": "TCC", "description": "Trabalho de conclusão"}).json()
    assert project["status"] == "active" and project["conversation_count"] == 0
    assert client.post("/api/v1/projects", json={"name": "tcc"}).status_code == 409
    client.post("/api/v1/conversations", json={"title": "Capítulo 1", "project_id": project["id"]})
    client.post("/api/v1/memories", json={"kind": "fact", "content": "Entrega em 2027", "project_id": project["id"]})
    counted = client.get(f"/api/v1/projects/{project['id']}").json()
    assert counted["conversation_count"] == 1 and counted["memory_count"] == 1
    archived = client.patch(f"/api/v1/projects/{project['id']}", json={"status": "archived"}).json()
    assert archived["status"] == "archived" and archived["archived_at"]
    assert client.get("/api/v1/projects", params={"status": "active"}).json() == []


def test_memories_go_to_the_trash_and_come_back(client):
    memory = client.post("/api/v1/memories", json={"kind": "reminder", "content": "Pagar a conta de luz", "importance": 2}).json()
    assert memory["kind_label"] == "Lembrete" and memory["source"] == "user"
    assert client.get("/api/v1/memories", params={"q": "luz"}).json()[0]["id"] == memory["id"]
    assert client.delete(f"/api/v1/memories/{memory['id']}").json()["deleted_at"]
    assert client.get("/api/v1/memories").json() == []
    assert client.get("/api/v1/memories", params={"trash": True}).json()[0]["id"] == memory["id"]
    assert client.patch(f"/api/v1/memories/{memory['id']}", json={"content": "editar"}).status_code == 409
    client.post(f"/api/v1/memories/{memory['id']}/restore")
    assert client.patch(f"/api/v1/memories/{memory['id']}", json={"content": "Pagar a conta de água"}).json()["content"] == "Pagar a conta de água"
    assert client.post("/api/v1/memories", json={"kind": "segredo", "content": "x"}).status_code == 422


def test_preferences_are_validated_and_keep_their_source(client):
    prefs = client.get("/api/v1/preferences").json()
    assert prefs["movimento_reduzido"]["value"] is False and prefs["movimento_reduzido"]["source"] == "padrao"
    saved = client.put("/api/v1/preferences/movimento_reduzido", json={"value": True}).json()
    assert saved["value"] is True and saved["source"] == "user"
    assert client.put("/api/v1/preferences/densidade", json={"value": "minuscula"}).status_code == 422
    assert client.put("/api/v1/preferences/movimento_reduzido", json={"value": "sim"}).status_code == 422
    assert client.put("/api/v1/preferences/desconhecida", json={"value": "x"}).status_code == 404
    assert client.put("/api/v1/preferences/nome", json={"value": "Ana"}).json()["value"] == "Ana"


def test_ai_and_tools_report_what_does_not_exist_yet(client):
    ai = client.get("/api/v1/ai/status").json()
    assert ai["gateway"]["situacao"] == "nao_implementado" and ai["selection_allowed"] is False and ai["providers"] == []
    tools = client.get("/api/v1/tools").json()
    assert tools["executor"]["situacao"] == "nao_implementado" and tools["tools"] == [] and tools["executions"] == []


def test_system_status_resources_settings_and_activity_are_real(client):
    client.post("/api/v1/projects", json={"name": "Casa"})
    status = client.get("/api/v1/system/status").json()
    assert status["health"]["status"] == "ok" and status["database"]["revision"] == status["database"]["head"]
    assert status["database"]["counts"]["projects"] == 1 and status["database"]["size_bytes"] > 0
    modules = {m["name"]: m for m in status["modules"]}
    assert len(modules) == 13
    assert modules["ai_gateway"]["situacao"] == "planejado" and modules["storage"]["situacao"] == "implementado"
    assert status["ai"]["situacao"] == "nao_implementado"
    resources = client.get("/api/v1/system/resources").json()
    assert resources["process"]["rss_mb"] > 10 and resources["system"]["cpu_count"] >= 1
    settings = client.get("/api/v1/system/settings").json()
    assert settings["api_host"] == "127.0.0.1" and settings["editable"] is False
    events = client.get("/api/v1/activity").json()
    assert events[0]["title"] == "Projeto criado: Casa"


def test_activity_never_copies_the_private_message(client):
    conversation = client.post("/api/v1/conversations", json={}).json()
    client.post(f"/api/v1/conversations/{conversation['id']}/messages", json={"content": "minha senha do banco é 1234"})
    assert all("1234" not in e["title"] for e in client.get("/api/v1/activity").json())


# ------------------------------------------------------------------ guarda de origem (AD-25)
def test_pages_from_other_sites_cannot_change_anything(client):
    bad = {"Origin": "https://site-qualquer.example"}
    assert client.post("/api/v1/projects", json={"name": "X"}, headers=bad).status_code == 403
    assert client.post("/api/v1/projects", json={"name": "X"}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    other_port = {"Origin": "http://127.0.0.1:5173"}
    assert client.post("/api/v1/projects", json={"name": "X"}, headers=other_port).status_code == 403
    assert client.get("/api/v1/projects").json() == []


def test_changes_must_be_json(client):
    response = client.post("/api/v1/projects", content=b"name=X", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 415 and response.json()["error"]["code"] == "tipo_nao_aceito"
    response = client.post("/api/v1/projects", content=b'{"name": "X"}', headers={"Content-Type": "text/plain"})
    assert response.status_code == 415


def test_local_programs_without_origin_are_accepted(client):
    del client.headers["Origin"]
    assert client.post("/api/v1/projects", json={"name": "Via script"}).status_code == 201


def test_responses_carry_a_strict_content_security_policy(client):
    response = client.get("/api/v1/health")
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY" and "access-control-allow-origin" not in response.headers
