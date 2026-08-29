import asyncio
from pathlib import Path

import pytest
from conftest import auth_header, register_user
from fastapi.testclient import TestClient

from app.api.admin import get_ollama_client
from app.models import Chunk, Document, KnowledgeBase, User, WikiPage, Workspace, WorkspaceMember
from app.models.m1 import new_uuid, now_utc
from app.services.document_service import process_document_job
from app.services.llm.base import LLMProvider
from app.services.wiki.pipeline import process_wiki_ingest_job


class CancelledLLMProvider(LLMProvider):
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> str:
        raise asyncio.CancelledError


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


def run_cancelled_wiki_worker(client: TestClient, task_id: str) -> None:
    async def run_worker() -> None:
        fake_client = client.app.dependency_overrides[get_ollama_client]()
        async with client.app.state.session_factory() as session:
            await process_wiki_ingest_job(
                session,
                settings=client.app.state.settings,
                ollama_client=fake_client,
                task_id=task_id,
                llm_provider=CancelledLLMProvider(),
            )

    asyncio.run(run_worker())


def clear_page_citations(client: TestClient, page_id: str) -> None:
    async def update_page() -> None:
        async with client.app.state.session_factory() as session:
            page = await session.get(WikiPage, page_id)
            assert page is not None
            page.source_citations = []
            await session.commit()

    asyncio.run(update_page())


def inject_foreign_source(client: TestClient, page_id: str) -> tuple[str, str]:
    async def create_foreign_source() -> tuple[str, str]:
        async with client.app.state.session_factory() as session:
            user_id = new_uuid()
            workspace_id = new_uuid()
            kb_id = new_uuid()
            document_id = new_uuid()
            chunk_id = new_uuid()
            session.add_all(
                [
                    User(id=user_id, username=f"foreign-{user_id}", password_hash="x"),
                    Workspace(id=workspace_id, name="外部 Workspace", created_by=user_id),
                    WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="admin"),
                    KnowledgeBase(
                        id=kb_id,
                        workspace_id=workspace_id,
                        name="外部文档库",
                        description="",
                        type="document",
                        status="active",
                        embedding_provider="ollama",
                        embedding_model_tag="bge-m3",
                        embedding_model_digest="sha256:bge",
                        embedding_dim=1024,
                    ),
                    Document(
                        id=document_id,
                        kb_id=kb_id,
                        filename="foreign.md",
                        file_hash=new_uuid().replace("-", ""),
                        file_path="/tmp/foreign.md",
                        file_size=10,
                        status="completed",
                        chunk_count=1,
                        created_by=user_id,
                        created_by_username="foreign",
                        created_at=now_utc(),
                        updated_at=now_utc(),
                    ),
                    Chunk(
                        id=chunk_id,
                        document_id=document_id,
                        kb_id=kb_id,
                        content="foreign workspace content",
                        header_path=["外部"],
                        seq=0,
                        start_pos=0,
                        end_pos=24,
                        embedding=[0.1] * 1024,
                        search_text="foreign workspace content",
                    ),
                ]
            )

            page = await session.get(WikiPage, page_id)
            assert page is not None
            page.source_refs = sorted(set([*list(page.source_refs or []), document_id]))
            page.source_citations = [
                *list(page.source_citations or []),
                {"document_id": document_id, "chunk_ids": [chunk_id]},
            ]
            await session.commit()
            return document_id, chunk_id

    return asyncio.run(create_foreign_source())


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

    sources = client.get(f"/api/v1/wiki-pages/{page_id}/sources", headers=headers)
    assert sources.status_code == 200
    source_items = sources.json()["items"]
    assert source_items
    assert source_items[0]["document_id"] == document_id
    assert source_items[0]["precise"] is True
    assert source_items[0]["chunks"]
    assert {"id", "seq", "header_path", "content", "start_pos", "end_pos"}.issubset(source_items[0]["chunks"][0])

    source_page_id = next(item["id"] for item in items if item["page_type"] == "source")
    source_page_sources = client.get(f"/api/v1/wiki-pages/{source_page_id}/sources", headers=headers)
    assert source_page_sources.status_code == 200
    assert source_page_sources.json()["items"][0]["precise"] is True

    clear_page_citations(client, page_id)
    fallback_sources = client.get(f"/api/v1/wiki-pages/{page_id}/sources", headers=headers)
    assert fallback_sources.status_code == 200
    assert fallback_sources.json()["items"][0]["precise"] is False
    assert fallback_sources.json()["items"][0]["chunks"]

    foreign_document_id, _ = inject_foreign_source(client, page_id)
    isolated_sources = client.get(f"/api/v1/wiki-pages/{page_id}/sources", headers=headers)
    assert isolated_sources.status_code == 200
    assert foreign_document_id not in {item["document_id"] for item in isolated_sources.json()["items"]}

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


def test_wiki_rebuild_cancelled_task_releases_building_status(client: TestClient) -> None:
    admin = register_user(client, "cancelled-owner")
    token = admin["tokens"]["access_token"]
    headers = auth_header(token)
    source_kb_id = create_source_kb(client, token)
    upload_completed_document(client, token, source_kb_id)
    wiki_kb_id = create_wiki_kb(client, token, source_kb_id)

    rebuild = client.post(f"/api/v1/wiki/{wiki_kb_id}/rebuild", headers=headers, json={"confirm": "REBUILD"})
    assert rebuild.status_code == 202
    task_id = rebuild.json()["task_id"]

    with pytest.raises(asyncio.CancelledError):
        run_cancelled_wiki_worker(client, task_id)

    task = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert task.status_code == 200
    assert task.json()["status"] == "failed"
    assert task.json()["stage"] == "failed"
    assert task.json()["error"]["code"] == "wiki_ingest_cancelled"

    pages = client.get(f"/api/v1/wiki/{wiki_kb_id}/pages", headers=headers)
    assert pages.status_code == 200
