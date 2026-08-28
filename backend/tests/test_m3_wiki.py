import asyncio
from pathlib import Path

from conftest import auth_header, register_user
from fastapi.testclient import TestClient

from app.api.admin import get_ollama_client
from app.services.document_service import process_document_job
from app.services.wiki.pipeline import process_wiki_ingest_job


def create_source_kb(client: TestClient, token: str) -> str:
    response = client.post(
        "/api/v1/kbs",
        headers=auth_header(token),
        json={
            "type": "document",
            "name": "产品文档库",
            "description": "Source KB",
            "embedding_model_tag": "bge-m3",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_wiki_kb(client: TestClient, token: str, source_kb_id: str) -> str:
    response = client.post(
        "/api/v1/kbs",
        headers=auth_header(token),
        json={
            "type": "wiki",
            "name": "产品 Wiki",
            "description": "Wiki KB",
            "embedding_model_tag": "bge-m3",
            "source_knowledge_base_ids": [source_kb_id],
            "wiki_config": {
                "auto_ingest": False,
                "llm_timeout_seconds": 60,
                "llm_max_retries": 3,
                "temperature": 0.2,
            },
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def upload_completed_document(client: TestClient, token: str, kb_id: str) -> str:
    headers = auth_header(token)
    corpus = Path("docs/v1/quality-corpus/product-handbook.md").read_bytes()
    upload = client.post(
        f"/api/v1/kbs/{kb_id}/documents/upload",
        headers=headers,
        files=[("files", ("product-handbook.md", corpus, "text/markdown"))],
    )
    assert upload.status_code == 202
    document_id = upload.json()["documents"][0]["id"]

    async def run_worker() -> None:
        fake_client = client.app.dependency_overrides[get_ollama_client]()
        async with client.app.state.session_factory() as session:
            await process_document_job(
                session,
                settings=client.app.state.settings,
                client=fake_client,
                document_id=document_id,
            )

    asyncio.run(run_worker())
    return document_id


def run_wiki_worker(client: TestClient, task_id: str) -> None:
    async def run_worker() -> None:
        fake_client = client.app.dependency_overrides[get_ollama_client]()
        async with client.app.state.session_factory() as session:
            await process_wiki_ingest_job(
                session,
                settings=client.app.state.settings,
                ollama_client=fake_client,
                task_id=task_id,
                llm_provider=None,
            )

    asyncio.run(run_worker())


def test_wiki_ingest_pages_graph_and_idempotency(client: TestClient) -> None:
    admin = register_user(client, "admin")
    token = admin["tokens"]["access_token"]
    headers = auth_header(token)
    source_kb_id = create_source_kb(client, token)
    document_id = upload_completed_document(client, token, source_kb_id)
    wiki_kb_id = create_wiki_kb(client, token, source_kb_id)

    accepted = client.post(f"/api/v1/wiki/{wiki_kb_id}/ingest", headers=headers, json={})
    assert accepted.status_code == 202
    task_id = accepted.json()["task_id"]
    run_wiki_worker(client, task_id)

    task = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert task.status_code == 200
    assert task.json()["stage"] == "completed"
    assert task.json()["payload"]["trace_id"] is None

    pages = client.get(f"/api/v1/wiki/{wiki_kb_id}/pages", headers=headers)
    assert pages.status_code == 200
    items = pages.json()["items"]
    page_types = {item["page_type"] for item in items}
    assert {"index", "source", "entity", "concept", "overview", "analysis"}.issubset(page_types)
    assert all(document_id in item["source_refs"] for item in items if item["page_type"] == "source")
    assert pages.json()["tree"]

    page_id = next(item["id"] for item in items if item["page_type"] == "entity")
    page = client.get(f"/api/v1/wiki-pages/{page_id}", headers=headers)
    assert page.status_code == 200
    assert page.json()["current_revision_id"]
    assert not page.json()["content"].startswith("SUMMARY:")

    graph = client.get(f"/api/v1/wiki/{wiki_kb_id}/graph", headers=headers)
    assert graph.status_code == 200
    assert graph.json()["nodes"]
    assert graph.json()["edges"]

    second = client.post(f"/api/v1/wiki/{wiki_kb_id}/ingest", headers=headers, json={})
    assert second.status_code == 202
    run_wiki_worker(client, second.json()["task_id"])
    pages_after = client.get(f"/api/v1/wiki/{wiki_kb_id}/pages", headers=headers).json()["items"]
    graph_after = client.get(f"/api/v1/wiki/{wiki_kb_id}/graph", headers=headers).json()
    assert len(pages_after) == len(items)
    assert len(graph_after["nodes"]) == len(graph.json()["nodes"])
    assert len(graph_after["edges"]) == len(graph.json()["edges"])


def test_wiki_rebuild_blocks_queries_until_worker_completes(client: TestClient) -> None:
    admin = register_user(client, "owner")
    token = admin["tokens"]["access_token"]
    headers = auth_header(token)
    source_kb_id = create_source_kb(client, token)
    upload_completed_document(client, token, source_kb_id)
    wiki_kb_id = create_wiki_kb(client, token, source_kb_id)

    rebuild = client.post(f"/api/v1/wiki/{wiki_kb_id}/rebuild", headers=headers, json={"confirm": "REBUILD"})
    assert rebuild.status_code == 202
    blocked = client.get(f"/api/v1/wiki/{wiki_kb_id}/pages", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "kb_unavailable"

    run_wiki_worker(client, rebuild.json()["task_id"])
    pages = client.get(f"/api/v1/wiki/{wiki_kb_id}/pages", headers=headers)
    assert pages.status_code == 200
    assert pages.json()["items"]
