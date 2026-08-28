import hashlib
import asyncio
import json
import re
from pathlib import Path
from typing import Any

import structlog
from arq import create_pool
from fastapi import UploadFile
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.models import Chunk as ChunkModel
from app.models import Document, DocumentTag, KnowledgeBase, ModelSetting, Tag, TaskPendingOp
from app.models.m1 import new_uuid, now_utc
from app.schemas import (
    ChunkingConfig,
    ChunkOut,
    ChunkPreviewItem,
    DocumentDetail,
    DocumentOut,
    DocumentPage,
    DocumentUploadResponse,
    TagOut,
    TaskAcceptedResponse,
)
from app.services.audit_service import record_audit
from app.services.chunking.markdown_chunker import MarkdownChunker
from app.services.chunking.text_chunker import TextChunker
from app.services.embedding.ollama_provider import OllamaEmbeddingProvider
from app.services.model_service import OllamaClient, get_or_create_settings
from app.services.observability import Observability
from app.services.retrieval.dense import vector_literal
from app.workers.settings import redis_settings

logger = structlog.get_logger(__name__)

ALLOWED_EXTENSIONS = {".md", ".txt"}
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


async def enqueue_process_document(task_id: str, document_id: str) -> None:
    try:
        redis = await asyncio.wait_for(create_pool(redis_settings()), timeout=1)
        await asyncio.wait_for(
            redis.enqueue_job("process_document", document_id, _job_id=task_id),
            timeout=1,
        )
        await redis.close()
    except Exception as exc:  # pragma: no cover - local dev/test may not run Redis
        logger.warning("document_enqueue_failed", document_id=document_id, error=str(exc))


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip().replace("\\", "/")
    name = Path(name).name
    stem = SAFE_FILENAME_RE.sub("_", Path(name).stem).strip("._") or "document"
    ext = Path(name).suffix.lower()
    return f"{stem}{ext}"


def validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ApiError("validation_error", "仅支持 .md 和 .txt 文件", 422)
    return ext


async def require_source_kb(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str,
) -> KnowledgeBase:
    kb = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if kb is None:
        raise ApiError("not_found", "知识库不存在", 404)
    if kb.type != "document":
        raise ApiError("validation_error", "只能向 Source KB 上传文档", 422)
    return kb


async def get_tags_by_ids(
    session: AsyncSession,
    *,
    kb_id: str,
    tag_ids: list[str] | None,
) -> list[Tag]:
    if not tag_ids:
        return []
    result = await session.execute(select(Tag).where(Tag.kb_id == kb_id, Tag.id.in_(tag_ids)))
    tags = list(result.scalars())
    if len(tags) != len(set(tag_ids)):
        raise ApiError("validation_error", "标签不存在", 422)
    return tags


async def tags_for_documents(session: AsyncSession, document_ids: list[str]) -> dict[str, list[TagOut]]:
    if not document_ids:
        return {}
    result = await session.execute(
        select(DocumentTag.document_id, Tag)
        .join(Tag, Tag.id == DocumentTag.tag_id)
        .where(DocumentTag.document_id.in_(document_ids))
        .order_by(Tag.name)
    )
    grouped: dict[str, list[TagOut]] = {document_id: [] for document_id in document_ids}
    for document_id, tag in result.all():
        grouped.setdefault(document_id, []).append(TagOut.model_validate(tag))
    return grouped


async def document_out(session: AsyncSession, document: Document) -> DocumentOut:
    grouped = await tags_for_documents(session, [document.id])
    return DocumentOut(
        id=document.id,
        kb_id=document.kb_id,
        filename=document.filename,
        file_hash=document.file_hash,
        file_size=document.file_size,
        status=document.status,
        error_message=document.error_message,
        chunk_count=document.chunk_count,
        tags=grouped.get(document.id, []),
        created_by=document.created_by,
        created_by_username=document.created_by_username,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


async def upload_documents(
    session: AsyncSession,
    *,
    settings: Settings,
    workspace_id: str,
    actor_id: str,
    actor_username: str,
    kb_id: str,
    files: list[UploadFile],
    tag_ids: list[str] | None,
) -> DocumentUploadResponse:
    if not files:
        raise ApiError("validation_error", "至少上传一个文件", 422)
    await require_source_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    tags = await get_tags_by_ids(session, kb_id=kb_id, tag_ids=tag_ids)

    prepared: list[tuple[str, str, bytes, str]] = []
    seen_hashes: set[str] = set()
    max_size = settings.max_file_size_mb * 1024 * 1024
    for file in files:
        safe_name = sanitize_filename(file.filename or "document")
        ext = validate_extension(safe_name)
        content = await file.read()
        if len(content) > max_size:
            raise ApiError("validation_error", f"单文件最大 {settings.max_file_size_mb}MB", 422)
        file_hash = hashlib.sha256(content).hexdigest()
        if file_hash in seen_hashes:
            raise ApiError("document_duplicate", "批量上传中存在重复文件", 409)
        seen_hashes.add(file_hash)
        prepared.append((safe_name, ext, content, file_hash))

    existing = await session.scalar(
        select(Document).where(Document.kb_id == kb_id, Document.file_hash.in_(seen_hashes))
    )
    if existing is not None:
        raise ApiError("document_duplicate", "该文件已存在", 409)

    documents: list[Document] = []
    tasks: list[TaskPendingOp] = []
    for filename, ext, content, file_hash in prepared:
        document = Document(
            kb_id=kb_id,
            filename=filename,
            file_hash=file_hash,
            file_path="",
            file_size=len(content),
            status="pending",
            error_message=None,
            chunk_count=0,
            created_by=actor_id,
            created_by_username=actor_username,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(document)
        await session.flush()

        upload_dir = settings.upload_dir / kb_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{document.id}{ext}"
        target.write_bytes(content)
        document.file_path = str(target)

        for tag in tags:
            session.add(DocumentTag(document_id=document.id, tag_id=tag.id))

        task = TaskPendingOp(
            kb_id=kb_id,
            task_type="document_process",
            status="pending",
            stage="pending",
            progress=0,
            payload={"document_id": document.id, "filename": filename},
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(task)
        await session.flush()
        documents.append(document)
        tasks.append(task)

    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="document.upload",
        resource_type="document",
        resource_id=documents[0].id if len(documents) == 1 else None,
        details={"kb_id": kb_id, "document_ids": [item.id for item in documents]},
    )
    await session.commit()

    for task, document in zip(tasks, documents, strict=True):
        await enqueue_process_document(task.id, document.id)

    return DocumentUploadResponse(
        documents=[await document_out(session, document) for document in documents],
        task_ids=[task.id for task in tasks],
    )


async def list_documents(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str,
    q: str | None,
    tag_id: str | None,
    status: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> DocumentPage:
    await require_source_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    conditions: list[Any] = [Document.kb_id == kb_id]
    if q:
        conditions.append(Document.filename.ilike(f"%{q}%"))
    if status:
        conditions.append(Document.status == status)
    query = select(Document).where(*conditions)
    count_query = select(func.count()).select_from(Document).where(*conditions)
    if tag_id:
        query = query.join(DocumentTag, DocumentTag.document_id == Document.id).where(
            DocumentTag.tag_id == tag_id
        )
        count_query = count_query.join(
            DocumentTag,
            DocumentTag.document_id == Document.id,
        ).where(DocumentTag.tag_id == tag_id)

    order_map = {
        "created_at_asc": Document.created_at.asc(),
        "filename_asc": Document.filename.asc(),
        "filename_desc": Document.filename.desc(),
        "created_at_desc": Document.created_at.desc(),
    }
    total = await session.scalar(count_query)
    result = await session.execute(
        query.order_by(order_map.get(sort, Document.created_at.desc()))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    documents = list(result.scalars())
    grouped = await tags_for_documents(session, [item.id for item in documents])
    items = [
        DocumentOut(
            id=document.id,
            kb_id=document.kb_id,
            filename=document.filename,
            file_hash=document.file_hash,
            file_size=document.file_size,
            status=document.status,
            error_message=document.error_message,
            chunk_count=document.chunk_count,
            tags=grouped.get(document.id, []),
            created_by=document.created_by,
            created_by_username=document.created_by_username,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )
        for document in documents
    ]
    return DocumentPage(items=items, total=int(total or 0), page=page, page_size=page_size)


async def get_document_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: str,
    document_id: str,
) -> Document:
    document = await session.scalar(
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(Document.id == document_id, KnowledgeBase.workspace_id == workspace_id)
    )
    if document is None:
        raise ApiError("not_found", "文档不存在", 404)
    return document


async def get_document_detail(
    session: AsyncSession,
    *,
    workspace_id: str,
    document_id: str,
) -> DocumentDetail:
    document = await get_document_for_workspace(session, workspace_id=workspace_id, document_id=document_id)
    result = await session.execute(
        select(ChunkModel)
        .where(ChunkModel.document_id == document.id)
        .order_by(ChunkModel.seq.asc())
    )
    chunks = [ChunkOut.model_validate(chunk) for chunk in result.scalars()]
    content = Path(document.file_path).read_text(encoding="utf-8", errors="replace")
    base = await document_out(session, document)
    return DocumentDetail(**base.model_dump(), content=content, chunks=chunks)


async def delete_document(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    document_id: str,
) -> None:
    document = await get_document_for_workspace(session, workspace_id=workspace_id, document_id=document_id)
    await session.execute(delete(ChunkModel).where(ChunkModel.document_id == document.id))
    await session.execute(delete(DocumentTag).where(DocumentTag.document_id == document.id))
    await session.delete(document)
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="document.delete",
        resource_type="document",
        resource_id=document.id,
        details={"kb_id": document.kb_id, "filename": document.filename},
    )
    await session.commit()
    try:
        Path(document.file_path).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("document_file_delete_failed", document_id=document.id, error=str(exc))


async def retry_document(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    document_id: str,
) -> TaskAcceptedResponse:
    document = await get_document_for_workspace(session, workspace_id=workspace_id, document_id=document_id)
    if document.status != "failed":
        raise ApiError("conflict", "只有失败文档可重试", 409)
    await session.execute(delete(ChunkModel).where(ChunkModel.document_id == document.id))
    document.status = "pending"
    document.error_message = None
    document.chunk_count = 0
    document.updated_at = now_utc()
    task = TaskPendingOp(
        kb_id=document.kb_id,
        task_type="document_process",
        status="pending",
        stage="pending",
        progress=0,
        payload={"document_id": document.id, "filename": document.filename, "retry": True},
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(task)
    await session.flush()
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="document.retry",
        resource_type="document",
        resource_id=document.id,
        details={"task_id": task.id},
    )
    await session.commit()
    await enqueue_process_document(task.id, document.id)
    return TaskAcceptedResponse(task_id=task.id)


async def list_tags(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str,
) -> list[TagOut]:
    await require_source_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    result = await session.execute(select(Tag).where(Tag.kb_id == kb_id).order_by(Tag.name))
    return [TagOut.model_validate(tag) for tag in result.scalars()]


async def create_tag(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    kb_id: str,
    name: str,
) -> TagOut:
    await require_source_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    existing = await session.scalar(select(Tag).where(Tag.kb_id == kb_id, Tag.name == name))
    if existing is not None:
        raise ApiError("conflict", "标签已存在", 409)
    tag = Tag(kb_id=kb_id, name=name)
    session.add(tag)
    await session.flush()
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="tag.create",
        resource_type="tag",
        resource_id=tag.id,
        details={"kb_id": kb_id, "name": name},
    )
    await session.commit()
    return TagOut.model_validate(tag)


async def update_tag(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    kb_id: str,
    tag_id: str,
    name: str,
) -> TagOut:
    await require_source_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    tag = await session.scalar(select(Tag).where(Tag.kb_id == kb_id, Tag.id == tag_id))
    if tag is None:
        raise ApiError("not_found", "标签不存在", 404)
    conflict = await session.scalar(
        select(Tag).where(Tag.kb_id == kb_id, Tag.name == name, Tag.id != tag_id)
    )
    if conflict is not None:
        raise ApiError("conflict", "标签已存在", 409)
    tag.name = name
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="tag.update",
        resource_type="tag",
        resource_id=tag.id,
        details={"kb_id": kb_id, "name": name},
    )
    await session.commit()
    return TagOut.model_validate(tag)


async def delete_tag(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_id: str,
    kb_id: str,
    tag_id: str,
) -> None:
    await require_source_kb(session, workspace_id=workspace_id, kb_id=kb_id)
    tag = await session.scalar(select(Tag).where(Tag.kb_id == kb_id, Tag.id == tag_id))
    if tag is None:
        raise ApiError("not_found", "标签不存在", 404)
    await session.execute(delete(DocumentTag).where(DocumentTag.tag_id == tag.id))
    await session.delete(tag)
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="tag.delete",
        resource_type="tag",
        resource_id=tag.id,
        details={"kb_id": kb_id, "name": tag.name},
    )
    await session.commit()


def chunker_for(content_type: str, config: ChunkingConfig):
    kwargs = {"chunk_size": config.chunk_size, "chunk_overlap": config.chunk_overlap}
    return MarkdownChunker(**kwargs) if content_type == "markdown" else TextChunker(**kwargs)


def preview_chunks(
    *,
    content: str,
    content_type: str,
    config: ChunkingConfig,
) -> list[ChunkPreviewItem]:
    chunks = chunker_for(content_type, config).split(content)
    return [
        ChunkPreviewItem(
            content=chunk.content,
            header_path=chunk.header_path,
            seq=chunk.seq,
            start_pos=chunk.start_pos,
            end_pos=chunk.end_pos,
            char_count=len(chunk.content),
        )
        for chunk in chunks
    ]


async def latest_task_for_document(session: AsyncSession, document_id: str) -> TaskPendingOp | None:
    return await session.scalar(
        select(TaskPendingOp)
        .where(
            TaskPendingOp.task_type == "document_process",
            TaskPendingOp.payload["document_id"].as_string() == document_id,
        )
        .order_by(TaskPendingOp.created_at.desc())
    )


def embed_input(header_path: list[str], content: str) -> str:
    prefix = " > ".join(header_path)
    return f"{prefix}\n{content}" if prefix else content


async def insert_document_chunks(
    session: AsyncSession,
    *,
    document: Document,
    chunks: list[Any],
    embeddings: list[list[float]],
) -> None:
    created_at = now_utc()
    if session.bind and session.bind.dialect.name == "postgresql":
        await session.execute(
            text(
                """
                INSERT INTO chunks (
                    id, document_id, kb_id, content, header_path, seq,
                    start_pos, end_pos, embedding, search_text, chunk_type,
                    source_page_id, created_at
                )
                VALUES (
                    :id, :document_id, :kb_id, :content, CAST(:header_path AS jsonb),
                    :seq, :start_pos, :end_pos, CAST(:embedding AS vector),
                    :search_text, :chunk_type, :source_page_id, :created_at
                )
                """
            ),
            [
                {
                    "id": new_uuid(),
                    "document_id": document.id,
                    "kb_id": document.kb_id,
                    "content": chunk.content,
                    "header_path": json.dumps(chunk.header_path, ensure_ascii=True),
                    "seq": chunk.seq,
                    "start_pos": chunk.start_pos,
                    "end_pos": chunk.end_pos,
                    "embedding": vector_literal(embedding),
                    "search_text": embed_input(chunk.header_path, chunk.content).replace("\n", " "),
                    "chunk_type": "text",
                    "source_page_id": None,
                    "created_at": created_at,
                }
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ],
        )
        return

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        session.add(
            ChunkModel(
                document_id=document.id,
                kb_id=document.kb_id,
                content=chunk.content,
                header_path=chunk.header_path,
                seq=chunk.seq,
                start_pos=chunk.start_pos,
                end_pos=chunk.end_pos,
                embedding=embedding,
                search_text=embed_input(chunk.header_path, chunk.content).replace("\n", " "),
                chunk_type="text",
                created_at=created_at,
            )
        )


async def process_document_job(
    session: AsyncSession,
    *,
    settings: Settings,
    client: OllamaClient,
    document_id: str,
) -> None:
    document = await session.get(Document, document_id)
    if document is None:
        raise ApiError("not_found", "文档不存在", 404)
    kb = await session.get(KnowledgeBase, document.kb_id)
    model_settings: ModelSetting = await get_or_create_settings(session, settings)
    task = await latest_task_for_document(session, document_id)
    if task is None:
        task = TaskPendingOp(
            kb_id=document.kb_id,
            task_type="document_process",
            status="pending",
            stage="pending",
            progress=0,
            payload={"document_id": document.id, "filename": document.filename},
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        session.add(task)
        await session.flush()

    observability = Observability(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )
    trace = observability.trace(
        name="document_process",
        metadata={
            "workspace_id": kb.workspace_id if kb else None,
            "kb_id": document.kb_id,
            "document_id": document.id,
        },
    )
    payload = {**task.payload, "trace_id": trace.id}
    trace_level = "DEFAULT"
    trace_status_message = "completed"

    try:
        document.status = "running"
        document.error_message = None
        document.updated_at = now_utc()
        task.status = "running"
        task.stage = "chunking"
        task.progress = 20
        task.payload = payload
        task.updated_at = now_utc()
        await session.commit()

        content = Path(document.file_path).read_text(encoding="utf-8", errors="replace")
        config = ChunkingConfig.model_validate(kb.chunking_config if kb and kb.chunking_config else {})
        content_type = "markdown" if Path(document.filename).suffix.lower() == ".md" else "text"
        with trace.span(name="chunking"):
            chunks = chunker_for(content_type, config).split(content)

        task.stage = "embedding"
        task.progress = 60
        task.updated_at = now_utc()
        await session.commit()

        embedding_model = kb.embedding_model_tag if kb else settings.ollama_embed_model
        expected_dim = kb.embedding_dim if kb else 1024
        provider = OllamaEmbeddingProvider(
            client=client,
            base_url=model_settings.ollama_base_url,
            tag=embedding_model,
        )
        inputs = [embed_input(chunk.header_path, chunk.content) for chunk in chunks]
        with trace.span(
            name="embedding",
            metadata={
                "chunk_count": len(chunks),
                "model": embedding_model,
                "embedding_dim": expected_dim,
            },
        ):
            embeddings = await provider.embed(inputs)
        for embedding in embeddings:
            if len(embedding) != expected_dim:
                raise ApiError("embedding_incompatible", "Embedding 维度与知识库不匹配", 409)

        task.stage = "indexing"
        task.progress = 85
        task.updated_at = now_utc()
        await session.commit()

        with trace.span(name="indexing", metadata={"chunk_count": len(chunks)}):
            await session.execute(delete(ChunkModel).where(ChunkModel.document_id == document.id))
            await insert_document_chunks(session, document=document, chunks=chunks, embeddings=embeddings)
        document.status = "completed"
        document.chunk_count = len(chunks)
        document.updated_at = now_utc()
        task.status = "completed"
        task.stage = "completed"
        task.progress = 100
        task.error = None
        task.updated_at = now_utc()
        await session.commit()
    except Exception as exc:
        trace_level = "ERROR"
        trace_status_message = str(exc)
        await session.rollback()
        document = await session.get(Document, document_id)
        task = await latest_task_for_document(session, document_id)
        if document is not None:
            document.status = "failed"
            document.error_message = str(exc)
            document.updated_at = now_utc()
        if task is not None:
            task.status = "failed"
            task.stage = "failed"
            task.progress = 100
            task.error = {"code": getattr(exc, "code", "document_process_failed"), "message": str(exc)}
            task.updated_at = now_utc()
        await session.commit()
        raise
    finally:
        trace.finish(level=trace_level, status_message=trace_status_message)
