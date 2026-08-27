from app.workers.settings import redis_settings
from app.workers.tasks import process_document, wiki_ingest, wiki_ingest_debounced


class WorkerSettings:
    functions = [process_document, wiki_ingest, wiki_ingest_debounced]
    redis_settings = redis_settings()

