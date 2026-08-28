from app.config import get_settings
from app.database import AsyncSessionLocal
from app.services.document_service import process_document_job
from app.services.model_service import HttpOllamaClient


async def process_document(ctx: dict[str, object], doc_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await process_document_job(
            session,
            settings=get_settings(),
            client=HttpOllamaClient(),
            document_id=doc_id,
        )


async def wiki_ingest(ctx: dict[str, object], kb_id: str) -> None:
    raise NotImplementedError


async def wiki_ingest_debounced(ctx: dict[str, object], kb_id: str) -> None:
    raise NotImplementedError
