from conftest import auth_header, register_user
from fastapi.testclient import TestClient


def test_model_config_masks_api_key_and_lists_ollama_models(client: TestClient) -> None:
    admin = register_user(client, "admin")
    headers = auth_header(admin["tokens"]["access_token"])

    update = client.put(
        "/api/v1/admin/llm-config",
        headers=headers,
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-secret",
            "temperature": 0.2,
            "max_tokens": 1024,
            "timeout_seconds": 30,
        },
    )
    assert update.status_code == 200
    assert update.json()["api_key_configured"] is True
    assert "sk-test-secret" not in update.text
    assert update.json()["api_key_masked"].startswith("sk-t")

    models = client.get("/api/v1/admin/ollama/models", headers=headers)
    assert models.status_code == 200
    items = models.json()["items"]
    assert any(item["tag"] == "bge-m3" and item["usable_for_v1"] for item in items)
    assert any(
        item["tag"] == "nomic-embed-text"
        and item["unusable_reason"] == "dimension_incompatible"
        for item in items
    )


def test_kb_crud_bindings_and_embedding_lock(client: TestClient) -> None:
    admin = register_user(client, "admin")
    headers = auth_header(admin["tokens"]["access_token"])

    source = client.post(
        "/api/v1/kbs",
        headers=headers,
        json={
            "type": "document",
            "name": "产品文档库",
            "description": "Source KB",
            "embedding_model_tag": "bge-m3",
        },
    )
    assert source.status_code == 201
    source_id = source.json()["id"]
    assert source.json()["embedding_dim"] == 1024

    incompatible = client.post(
        "/api/v1/kbs",
        headers=headers,
        json={
            "type": "document",
            "name": "坏模型",
            "embedding_model_tag": "nomic-embed-text",
        },
    )
    assert incompatible.status_code == 422

    wiki = client.post(
        "/api/v1/kbs",
        headers=headers,
        json={
            "type": "wiki",
            "name": "团队 Wiki",
            "embedding_model_tag": "bge-m3",
            "source_knowledge_base_ids": [source_id],
        },
    )
    assert wiki.status_code == 201
    assert wiki.json()["bound_source_kbs"][0]["id"] == source_id

    locked = client.patch(
        f"/api/v1/kbs/{source_id}",
        headers=headers,
        json={"embedding_model_tag": "another"},
    )
    assert locked.status_code == 422

    renamed = client.patch(
        f"/api/v1/kbs/{source_id}",
        headers=headers,
        json={"name": "产品资料库"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "产品资料库"
