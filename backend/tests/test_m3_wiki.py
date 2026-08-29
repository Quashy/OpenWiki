import asyncio
import json
import re
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


class EmptyReduceLLMProvider(LLMProvider):
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> str:
        content = messages[-1]["content"]
        if "<stage>extract</stage>" in content:
            if "西湖" in content:
                return (
                    '{"candidates":[{"name":"西湖","slug":"entity/west-lake","page_type":"entity",'
                    '"entity_type":"place","aliases":["西湖"],"description":"杭州旅行行程中的西湖地点。"}]}'
                )
            if "柠檬蛋糕" in content:
                return (
                    '{"candidates":[{"name":"柠檬蛋糕","slug":"entity/lemon-cake","page_type":"entity",'
                    '"entity_type":"other","aliases":["柠檬蛋糕"],"description":"柠檬蛋糕食谱条目。"}]}'
                )
            return '{"candidates":[]}'
        if "<stage>dedup</stage>" in content:
            return '{"merges":{}}'
        if "<stage>citation</stage>" in content:
            west_lake_chunks = chunk_ids_containing(content, "西湖")
            cake_chunks = chunk_ids_containing(content, "柠檬蛋糕")
            return (
                '{"citations":['
                f'{{"slug":"entity/west-lake","chunk_ids":{json_array(west_lake_chunks)}}},'
                f'{{"slug":"entity/lemon-cake","chunk_ids":{json_array(cake_chunks)}}}'
                "]}"
            )
        if "<stage>taxonomy</stage>" in content:
            return (
                '{"items":['
                '{"slug":"entity/west-lake","category_path":["旅行","地点"]},'
                '{"slug":"entity/lemon-cake","category_path":["生活","食谱"]}'
                "]}"
            )
        if "<stage>source_summary</stage>" in content:
            return "SUMMARY: 来源摘要。\n\n## 关键要点\n\n- 仅按当前文档摘要。"
        if "<stage>reduce</stage>" in content:
            if "entity/west-lake" in content:
                return '{"content":"","relations":[{"target_slug":"entity/lemon-cake","relation_type":"相关"}]}'
            return '{"content":"","relations":[]}'
        if "<stage>overview</stage>" in content:
            return "SUMMARY: 全局综述。\n\n## 覆盖范围\n\n- 当前 Wiki 覆盖两个独立主题。"
        return "{}"


class NeighborhoodReduceLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self.reduce_allowed_links_by_slug: dict[str, list[str]] = {}

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> str:
        content = messages[-1]["content"]
        if "<stage>extract</stage>" in content:
            if "杭州家庭旅行" in content:
                return (
                    '{"candidates":['
                    '{"name":"杭州家庭旅行","slug":"entity/hangzhou-family-trip","page_type":"entity",'
                    '"entity_type":"event","aliases":["杭州家庭旅行"],"description":"杭州家庭旅行安排。"},'
                    '{"name":"西湖","slug":"entity/west-lake","page_type":"entity",'
                    '"entity_type":"place","aliases":["西湖"],"description":"杭州家庭旅行中的西湖地点。"},'
                    '{"name":"G7391","slug":"entity/g7391","page_type":"entity",'
                    '"entity_type":"other","aliases":["G7391"],"description":"杭州家庭旅行乘坐的 G7391 车次。"}'
                    "]}"
                )
            if "柠檬蛋糕" in content:
                return (
                    '{"candidates":[{"name":"柠檬蛋糕","slug":"entity/lemon-cake","page_type":"entity",'
                    '"entity_type":"other","aliases":["柠檬蛋糕"],"description":"柠檬蛋糕食谱条目。"}]}'
                )
            return '{"candidates":[]}'
        if "<stage>dedup</stage>" in content:
            return '{"merges":{}}'
        if "<stage>citation</stage>" in content:
            travel_chunks = sorted(set(chunk_ids_containing(content, "杭州家庭旅行") + chunk_ids_containing(content, "G7391")))
            west_lake_chunks = chunk_ids_containing(content, "西湖")
            cake_chunks = chunk_ids_containing(content, "柠檬蛋糕")
            return (
                '{"citations":['
                f'{{"slug":"entity/hangzhou-family-trip","chunk_ids":{json_array(travel_chunks)}}},'
                f'{{"slug":"entity/west-lake","chunk_ids":{json_array(west_lake_chunks)}}},'
                f'{{"slug":"entity/g7391","chunk_ids":{json_array(travel_chunks)}}},'
                f'{{"slug":"entity/lemon-cake","chunk_ids":{json_array(cake_chunks)}}}'
                "]}"
            )
        if "<stage>taxonomy</stage>" in content:
            return (
                '{"items":['
                '{"slug":"entity/hangzhou-family-trip","category_path":["旅行","安排"]},'
                '{"slug":"entity/west-lake","category_path":["旅行","地点"]},'
                '{"slug":"entity/g7391","category_path":["旅行","交通"]},'
                '{"slug":"entity/lemon-cake","category_path":["生活","食谱"]}'
                "]}"
            )
        if "<stage>source_summary</stage>" in content:
            return "SUMMARY: 来源摘要。\n\n## 关键要点\n\n- 仅按当前文档摘要。"
        if "<stage>reduce</stage>" in content:
            candidate = json_tag(content, "candidate_json")
            allowed_links = json_tag(content, "allowed_links_json")
            slug = candidate["slug"]
            self.reduce_allowed_links_by_slug[slug] = [item["slug"] for item in allowed_links]
            link_lines = "\n".join(f"- [[{item['slug']}|{item['name']}]]" for item in allowed_links)
            relations = []
            if slug == "entity/hangzhou-family-trip":
                relations = [
                    {"target_slug": "entity/west-lake", "relation_type": "发生于"},
                    {"target_slug": "entity/g7391", "relation_type": "乘坐"},
                    {"target_slug": "entity/lemon-cake", "relation_type": "相关"},
                ]
            return json.dumps(
                {
                    "content": f"SUMMARY: {candidate['name']}。\n\n## 概述\n\n{link_lines or '- 无相关证据邻域链接'}",
                    "relations": relations,
                },
                ensure_ascii=False,
            )
        if "<stage>overview</stage>" in content:
            return "SUMMARY: 全局综述。\n\n## 覆盖范围\n\n- 当前 Wiki 覆盖旅行和食谱两个独立主题。"
        return "{}"


def json_tag(prompt: str, tag: str) -> object:
    match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", prompt, re.S)
    assert match is not None
    return json.loads(match.group(1))


def json_array(items: list[str]) -> str:
    return "[" + ",".join(f'"{item}"' for item in items) + "]"


def chunk_ids_containing(prompt: str, needle: str) -> list[str]:
    ids: list[str] = []
    blocks = prompt.split('"id":')
    for block in blocks[1:]:
        chunk_id = block.split('"', 2)[1]
        if needle in block:
            ids.append(chunk_id)
    return ids


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


def upload_completed_text_document(client: TestClient, token: str, kb_id: str, filename: str, content: str) -> str:
    headers = auth_header(token)
    upload = client.post(
        f"/api/v1/kbs/{kb_id}/documents/upload",
        headers=headers,
        files=[("files", (filename, content.encode("utf-8"), "text/markdown"))],
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


def run_empty_reduce_wiki_worker(client: TestClient, task_id: str) -> None:
    async def run_worker() -> None:
        fake_client = client.app.dependency_overrides[get_ollama_client]()
        async with client.app.state.session_factory() as session:
            await process_wiki_ingest_job(
                session,
                settings=client.app.state.settings,
                ollama_client=fake_client,
                task_id=task_id,
                llm_provider=EmptyReduceLLMProvider(),
            )

    asyncio.run(run_worker())


def run_wiki_worker_with_llm(client: TestClient, task_id: str, llm_provider: LLMProvider) -> None:
    async def run_worker() -> None:
        fake_client = client.app.dependency_overrides[get_ollama_client]()
        async with client.app.state.session_factory() as session:
            await process_wiki_ingest_job(
                session,
                settings=client.app.state.settings,
                ollama_client=fake_client,
                task_id=task_id,
                llm_provider=llm_provider,
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
    assert "edges" in graph.json()

    second = client.post(f"/api/v1/wiki/{wiki_kb_id}/ingest", headers=headers, json={})
    assert second.status_code == 202
    run_wiki_worker(client, second.json()["task_id"])
    pages_after = client.get(f"/api/v1/wiki/{wiki_kb_id}/pages", headers=headers).json()["items"]
    graph_after = client.get(f"/api/v1/wiki/{wiki_kb_id}/graph", headers=headers).json()
    assert len(pages_after) == len(items)
    assert len(graph_after["nodes"]) == len(graph.json()["nodes"])
    assert len(graph_after["edges"]) == len(graph.json()["edges"])


def test_wiki_rebuild_empty_reduce_does_not_create_unrelated_links_or_edges(client: TestClient) -> None:
    admin = register_user(client, "empty-reduce-owner")
    token = admin["tokens"]["access_token"]
    headers = auth_header(token)
    source_kb_id = create_source_kb(client, token)
    west_lake_document_id = upload_completed_text_document(
        client,
        token,
        source_kb_id,
        "itinerary.md",
        "# 杭州旅行行程\n\n第一天下午去西湖散步，晚上返回酒店。",
    )
    cake_document_id = upload_completed_text_document(
        client,
        token,
        source_kb_id,
        "lemon-cake-recipe.md",
        "# 柠檬蛋糕食谱\n\n柠檬蛋糕使用柠檬皮、黄油和低筋面粉，烘烤 35 分钟。",
    )
    wiki_kb_id = create_wiki_kb(client, token, source_kb_id)

    rebuild = client.post(f"/api/v1/wiki/{wiki_kb_id}/rebuild", headers=headers, json={"confirm": "REBUILD"})
    assert rebuild.status_code == 202
    task_id = rebuild.json()["task_id"]
    run_empty_reduce_wiki_worker(client, task_id)

    task = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert task.status_code == 200
    assert task.json()["status"] == "completed"
    degraded = task.json()["payload"]["reduce_degraded_pages"]
    assert {item["slug"] for item in degraded} == {"entity/west-lake", "entity/lemon-cake"}

    pages = client.get(f"/api/v1/wiki/{wiki_kb_id}/pages", headers=headers)
    assert pages.status_code == 200
    by_slug = {item["slug"]: item for item in pages.json()["items"]}
    west_lake = client.get(f"/api/v1/wiki-pages/{by_slug['entity/west-lake']['id']}", headers=headers).json()
    lemon_cake = client.get(f"/api/v1/wiki-pages/{by_slug['entity/lemon-cake']['id']}", headers=headers).json()

    assert "## 相关条目" not in west_lake["content"]
    assert "## 相关条目" not in lemon_cake["content"]
    assert "entity/lemon-cake" not in west_lake["content"]
    assert "entity/west-lake" not in lemon_cake["content"]

    west_lake_sources = client.get(f"/api/v1/wiki-pages/{west_lake['id']}/sources", headers=headers).json()["items"]
    lemon_cake_sources = client.get(f"/api/v1/wiki-pages/{lemon_cake['id']}/sources", headers=headers).json()["items"]
    assert {item["document_id"] for item in west_lake_sources} == {west_lake_document_id}
    assert {item["document_id"] for item in lemon_cake_sources} == {cake_document_id}
    assert west_lake_sources[0]["precise"] is True
    assert lemon_cake_sources[0]["precise"] is True

    graph = client.get(f"/api/v1/wiki/{wiki_kb_id}/graph", headers=headers)
    assert graph.status_code == 200
    nodes = {item["id"]: item for item in graph.json()["nodes"]}
    unrelated_edges = [
        item
        for item in graph.json()["edges"]
        if {nodes[item["source_entity_id"]]["slug"], nodes[item["target_entity_id"]]["slug"]}
        == {"entity/west-lake", "entity/lemon-cake"}
    ]
    assert unrelated_edges == []


def test_wiki_reduce_allowed_links_are_limited_to_citation_neighborhood(client: TestClient) -> None:
    admin = register_user(client, "neighborhood-owner")
    token = admin["tokens"]["access_token"]
    headers = auth_header(token)
    source_kb_id = create_source_kb(client, token)
    upload_completed_text_document(
        client,
        token,
        source_kb_id,
        "itinerary.md",
        "# 杭州家庭旅行\n\n杭州家庭旅行第一天下午去西湖，上午乘坐 G7391 次列车到达杭州东站。",
    )
    upload_completed_text_document(
        client,
        token,
        source_kb_id,
        "lemon-cake-recipe.md",
        "# 柠檬蛋糕食谱\n\n柠檬蛋糕使用柠檬皮、黄油和低筋面粉，烘烤 35 分钟。",
    )
    wiki_kb_id = create_wiki_kb(client, token, source_kb_id)
    provider = NeighborhoodReduceLLMProvider()

    rebuild = client.post(f"/api/v1/wiki/{wiki_kb_id}/rebuild", headers=headers, json={"confirm": "REBUILD"})
    assert rebuild.status_code == 202
    run_wiki_worker_with_llm(client, rebuild.json()["task_id"], provider)

    trip_allowed_links = set(provider.reduce_allowed_links_by_slug["entity/hangzhou-family-trip"])
    assert {"entity/west-lake", "entity/g7391"}.issubset(trip_allowed_links)
    assert "entity/lemon-cake" not in trip_allowed_links

    pages = client.get(f"/api/v1/wiki/{wiki_kb_id}/pages", headers=headers).json()["items"]
    trip_page_id = next(item["id"] for item in pages if item["slug"] == "entity/hangzhou-family-trip")
    trip_page = client.get(f"/api/v1/wiki-pages/{trip_page_id}", headers=headers).json()
    assert "[[entity/west-lake|西湖]]" in trip_page["content"]
    assert "[[entity/g7391|G7391]]" in trip_page["content"]
    assert "entity/lemon-cake" not in trip_page["content"]

    graph = client.get(f"/api/v1/wiki/{wiki_kb_id}/graph", headers=headers).json()
    nodes = {item["id"]: item for item in graph["nodes"]}
    trip_edges = {
        (nodes[item["source_entity_id"]]["slug"], nodes[item["target_entity_id"]]["slug"], item["relation_type"])
        for item in graph["edges"]
    }
    assert ("entity/hangzhou-family-trip", "entity/west-lake", "发生于") in trip_edges
    assert ("entity/hangzhou-family-trip", "entity/g7391", "乘坐") in trip_edges
    assert ("entity/hangzhou-family-trip", "entity/lemon-cake", "相关") not in trip_edges


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
