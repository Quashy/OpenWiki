import asyncio
from pathlib import Path

from conftest import auth_header, register_user
from fastapi.testclient import TestClient

from app.api.admin import get_ollama_client
from app.services.document_service import process_document_job
from app.services.retrieval.dense import dense_search
from app.services.retrieval.sparse import sparse_search


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


def test_tags_upload_list_detail_and_duplicate(client: TestClient) -> None:
    admin = register_user(client, "admin")
    headers = auth_header(admin["tokens"]["access_token"])
    kb_id = create_source_kb(client, admin["tokens"]["access_token"])

    tag = client.post(f"/api/v1/kbs/{kb_id}/tags", headers=headers, json={"name": "PRD"})
    assert tag.status_code == 201
    tag_id = tag.json()["id"]

    corpus = Path("docs/v1/quality-corpus/product-handbook.md").read_bytes()
    upload = client.post(
        f"/api/v1/kbs/{kb_id}/documents/upload",
        headers=headers,
        files=[("files", ("product-handbook.md", corpus, "text/markdown"))],
        data={"tag_ids": tag_id},
    )
    assert upload.status_code == 202
    document = upload.json()["documents"][0]
    assert document["status"] == "pending"
    assert document["created_by_username"] == "admin"
    assert document["tags"][0]["id"] == tag_id
    assert upload.json()["task_ids"]

    duplicate = client.post(
        f"/api/v1/kbs/{kb_id}/documents/upload",
        headers=headers,
        files=[("files", ("product-handbook-duplicate.md", corpus, "text/markdown"))],
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "document_duplicate"

    listed = client.get(f"/api/v1/kbs/{kb_id}/documents", headers=headers, params={"tag_id": tag_id})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == document["id"]
    assert listed.json()["items"][0]["created_by_username"] == "admin"

    detail = client.get(f"/api/v1/documents/{document['id']}", headers=headers)
    assert detail.status_code == 200
    assert "OpenWiki V2" in detail.json()["content"]


def test_worker_processes_document_and_retrieval_then_delete(client: TestClient) -> None:
    admin = register_user(client, "admin")
    headers = auth_header(admin["tokens"]["access_token"])
    kb_id = create_source_kb(client, admin["tokens"]["access_token"])
    corpus = Path("docs/v1/quality-corpus/product-handbook.md").read_bytes()
    upload = client.post(
        f"/api/v1/kbs/{kb_id}/documents/upload",
        headers=headers,
        files=[("files", ("product-handbook.md", corpus, "text/markdown"))],
    )
    document_id = upload.json()["documents"][0]["id"]

    # Keep the worker assertion in one async block to reuse the in-memory SQLite connection.
    async def run_assertions() -> None:
        fake_client = client.app.dependency_overrides[get_ollama_client]()
        async with client.app.state.session_factory() as session:
            await process_document_job(
                session,
                settings=client.app.state.settings,
                client=fake_client,
                document_id=document_id,
            )
        async with client.app.state.session_factory() as session:
            sparse = await sparse_search(
                session,
                kb_ids=[kb_id],
                query="OWV2-INV-2026-0007",
                top_k=3,
            )
            assert any("OWV2-INV-2026-0007" in item.content for item in sparse)
            dense = await dense_search(
                session,
                kb_ids=[kb_id],
                query_embedding=[0.1] * 1024,
                top_k=1,
            )
            assert dense

    asyncio.run(run_assertions())

    detail = client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    assert detail.json()["chunks"]

    delete = client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert delete.status_code == 204
    missing = client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert missing.status_code == 404


def test_viewer_cannot_upload_or_manage_tags(client: TestClient) -> None:
    admin = register_user(client, "admin")
    viewer = register_user(client, "viewer")
    admin_headers = auth_header(admin["tokens"]["access_token"])
    kb_id = create_source_kb(client, admin["tokens"]["access_token"])
    add_viewer = client.post(
        "/api/v1/workspaces/current/members",
        headers=admin_headers,
        json={"username": "viewer", "role": "viewer"},
    )
    assert add_viewer.status_code == 201
    viewer_headers = auth_header(viewer["tokens"]["access_token"])

    denied_tag = client.post(f"/api/v1/kbs/{kb_id}/tags", headers=viewer_headers, json={"name": "只读"})
    assert denied_tag.status_code == 403
    denied_upload = client.post(
        f"/api/v1/kbs/{kb_id}/documents/upload",
        headers=viewer_headers,
        files=[("files", ("a.txt", b"hello", "text/plain"))],
    )
    assert denied_upload.status_code == 403
