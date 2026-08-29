import asyncio

from conftest import auth_header, register_user
from fastapi.testclient import TestClient

from app.api.admin import get_ollama_client
from app.models import AuditLog, Chunk, Entity, KnowledgeBase, Relation, WikiPage
from app.models.m1 import new_uuid, now_utc
from app.services.chat import service as chat_service
from app.services.retrieval.fusion import reciprocal_rank_fusion
from app.services.retrieval.graph import graph_search


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


def seed_chat_chunks(client: TestClient, kb_id: str, actor_id: str) -> tuple[str, str]:
    async def seed() -> tuple[str, str]:
        async with client.app.state.session_factory() as session:
            kb = await session.get(KnowledgeBase, kb_id)
            assert kb is not None
            document_id = new_uuid()
            chunk_id = new_uuid()
            from app.models import Document

            session.add(
                Document(
                    id=document_id,
                    kb_id=kb_id,
                    filename="m5-chat.md",
                    file_hash=new_uuid().replace("-", ""),
                    file_path="/tmp/m5-chat.md",
                    file_size=120,
                    status="completed",
                    chunk_count=1,
                    created_by=actor_id,
                    created_by_username="admin",
                    created_at=now_utc(),
                    updated_at=now_utc(),
                )
            )
            session.add(
                Chunk(
                    id=chunk_id,
                    document_id=document_id,
                    kb_id=kb_id,
                    content="OWV2-M5 使用单 KB 会话、SSE 流式回答和引用溯源。",
                    header_path=["M5", "问答"],
                    seq=0,
                    start_pos=0,
                    end_pos=40,
                    embedding=[0.1] * 1024,
                    search_text="OWV2-M5 单 KB 会话 SSE 流式回答 引用溯源",
                    chunk_type="text",
                    created_at=now_utc(),
                )
            )
            await session.commit()
            return document_id, chunk_id

    return asyncio.run(seed())


def test_chat_session_crud_rejects_kb_ids_and_audits(client: TestClient) -> None:
    admin = register_user(client, "admin")
    headers = auth_header(admin["tokens"]["access_token"])
    kb_id = create_source_kb(client, admin["tokens"]["access_token"])

    rejected = client.post(
        "/api/v1/chat/sessions",
        headers=headers,
        json={"kb_ids": [kb_id]},
    )
    assert rejected.status_code == 422

    created = client.post(
        "/api/v1/chat/sessions",
        headers=headers,
        json={"kb_id": kb_id, "title": "M5 验收"},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert created.json()["kb_id"] == kb_id

    listed = client.get("/api/v1/chat/sessions", headers=headers, params={"kb_id": kb_id})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == session_id

    renamed = client.patch(
        f"/api/v1/chat/sessions/{session_id}",
        headers=headers,
        json={"title": "M5 已重命名"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "M5 已重命名"

    deleted = client.delete(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 204

    async def actions() -> set[str]:
        async with client.app.state.session_factory() as db:
            rows = (await db.execute(AuditLog.__table__.select())).all()
            return {row.action for row in rows}

    assert {"chat.session_create", "chat.session_update", "chat.session_delete"}.issubset(asyncio.run(actions()))


def test_viewer_can_stream_chat_with_grounded_citations(client: TestClient) -> None:
    admin = register_user(client, "admin")
    viewer = register_user(client, "viewer")
    admin_headers = auth_header(admin["tokens"]["access_token"])
    kb_id = create_source_kb(client, admin["tokens"]["access_token"])
    _, chunk_id = seed_chat_chunks(client, kb_id, admin["user"]["id"])
    add_viewer = client.post(
        "/api/v1/workspaces/current/members",
        headers=admin_headers,
        json={"username": "viewer", "role": "viewer"},
    )
    assert add_viewer.status_code == 201
    viewer_headers = auth_header(viewer["tokens"]["access_token"])

    created = client.post("/api/v1/chat/sessions", headers=viewer_headers, json={"kb_id": kb_id})
    assert created.status_code == 201
    session_id = created.json()["id"]

    with client.stream(
        "GET",
        f"/api/v1/chat/sessions/{session_id}/stream",
        headers=viewer_headers,
        params={"question": "M5 如何回答？"},
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: progress" in body
    assert "event: token" in body
    assert "event: done" in body
    assert chunk_id in body
    assert "trace_id" in body

    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages", headers=viewer_headers)
    assert messages.status_code == 200
    items = messages.json()["items"]
    assert [item["role"] for item in items] == ["user", "assistant"]
    assistant = items[-1]
    assert assistant["citations"][0]["chunk_id"] == chunk_id
    assert assistant["citations"][0]["source_type"] == "document"


def test_stream_error_does_not_expose_internal_exception(client: TestClient, monkeypatch) -> None:
    admin = register_user(client, "safe-error-owner")
    headers = auth_header(admin["tokens"]["access_token"])
    kb_id = create_source_kb(client, admin["tokens"]["access_token"])
    seed_chat_chunks(client, kb_id, admin["user"]["id"])
    created = client.post("/api/v1/chat/sessions", headers=headers, json={"kb_id": kb_id})
    assert created.status_code == 201
    session_id = created.json()["id"]

    async def broken_search(*args, **kwargs):
        raise RuntimeError("SELECT * FROM chunks WHERE secret = $1 [parameters: ('token',)]")

    monkeypatch.setattr(chat_service, "hybrid_search", broken_search)

    async def collect() -> str:
        fake_client = client.app.dependency_overrides[get_ollama_client]()
        async with client.app.state.session_factory() as session:
            chunks: list[str] = []
            async for item in chat_service.stream_chat_answer(
                session,
                settings=client.app.state.settings,
                ollama_client=fake_client,
                workspace_id=admin["workspace"]["id"],
                actor_id=admin["user"]["id"],
                session_id=session_id,
                question="会泄露 SQL 吗？",
            ):
                chunks.append(item)
            return "".join(chunks)

    body = asyncio.run(collect())
    assert "event: error" in body
    assert "问答失败，请稍后重试" in body
    assert "SELECT * FROM chunks" not in body
    assert "parameters" not in body


def test_graph_search_and_rrf_wiki_boost(client: TestClient) -> None:
    admin = register_user(client, "graph-owner")
    token = admin["tokens"]["access_token"]
    source_id = create_source_kb(client, token)
    wiki = client.post(
        "/api/v1/kbs",
        headers=auth_header(token),
        json={
            "type": "wiki",
            "name": "图谱 Wiki",
            "description": "",
            "embedding_model_tag": "bge-m3",
            "source_knowledge_base_ids": [source_id],
        },
    )
    assert wiki.status_code == 201
    wiki_id = wiki.json()["id"]

    async def seed_graph() -> tuple[str, str]:
        async with client.app.state.session_factory() as session:
            page_a = WikiPage(
                kb_id=wiki_id,
                slug="entity/m5",
                title="M5",
                page_type="entity",
                summary="M5 问答",
                content="M5 问答页面",
                category_path=["里程碑"],
                aliases=["方案B"],
                source_refs=[],
                source_citations=[],
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            page_b = WikiPage(
                kb_id=wiki_id,
                slug="entity/sse",
                title="SSE",
                page_type="entity",
                summary="流式输出",
                content="SSE 页面",
                category_path=["技术"],
                aliases=[],
                source_refs=[],
                source_citations=[],
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            session.add_all([page_a, page_b])
            await session.flush()
            entity_a = Entity(
                kb_id=wiki_id,
                name="M5",
                slug="entity/m5",
                entity_type="milestone",
                description="M5",
                aliases=["方案B"],
                wiki_page_id=page_a.id,
                created_at=now_utc(),
            )
            entity_b = Entity(
                kb_id=wiki_id,
                name="SSE",
                slug="entity/sse",
                entity_type="tech",
                description="SSE",
                aliases=[],
                wiki_page_id=page_b.id,
                created_at=now_utc(),
            )
            session.add_all([entity_a, entity_b])
            await session.flush()
            session.add(
                Relation(
                    kb_id=wiki_id,
                    source_entity_id=entity_a.id,
                    target_entity_id=entity_b.id,
                    relation_type="包含",
                    created_at=now_utc(),
                )
            )
            chunk_a = Chunk(
                kb_id=wiki_id,
                document_id=None,
                content="M5 方案B 是单 KB RAG 问答。",
                header_path=["M5"],
                seq=0,
                start_pos=0,
                end_pos=20,
                embedding=[0.1] * 1024,
                search_text="M5 方案B 单 KB RAG 问答",
                chunk_type="wiki_page",
                source_page_id=page_a.id,
                created_at=now_utc(),
            )
            chunk_b = Chunk(
                kb_id=wiki_id,
                document_id=None,
                content="SSE 用于流式输出 token。",
                header_path=["SSE"],
                seq=1,
                start_pos=0,
                end_pos=20,
                embedding=[0.1] * 1024,
                search_text="SSE 流式输出 token",
                chunk_type="wiki_page",
                source_page_id=page_b.id,
                created_at=now_utc(),
            )
            session.add_all([chunk_a, chunk_b])
            await session.commit()
            return chunk_a.id, chunk_b.id

    chunk_a_id, chunk_b_id = asyncio.run(seed_graph())

    async def search() -> list[str]:
        async with client.app.state.session_factory() as session:
            results = await graph_search(session, kb_id=wiki_id, query="方案B 的流式输出", top_k=5)
            return [item.chunk_id for item in results]

    graph_chunk_ids = asyncio.run(search())
    assert chunk_a_id in graph_chunk_ids
    assert chunk_b_id in graph_chunk_ids

    from app.services.retrieval.dense import RetrievalResult

    text_result = RetrievalResult(
        chunk_id="text",
        kb_id=source_id,
        content="text",
        header_path=[],
        document_id=None,
        chunk_type="text",
        source_page_id=None,
        score=1,
    )
    wiki_result = RetrievalResult(
        chunk_id="wiki",
        kb_id=wiki_id,
        content="wiki",
        header_path=[],
        document_id=None,
        chunk_type="wiki_page",
        source_page_id=None,
        score=1,
    )
    fused = reciprocal_rank_fusion([[text_result], [wiki_result]], top_k=2)
    assert fused[0].chunk_id == "wiki"
