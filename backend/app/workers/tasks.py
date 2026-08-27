async def process_document(ctx: dict[str, object], doc_id: str) -> None:
    raise NotImplementedError


async def wiki_ingest(ctx: dict[str, object], kb_id: str) -> None:
    raise NotImplementedError


async def wiki_ingest_debounced(ctx: dict[str, object], kb_id: str) -> None:
    raise NotImplementedError

