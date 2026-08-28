from app.workers.config import load_worker_config
from app.workers.settings import redis_settings
from app.workers.tasks import process_document, wiki_ingest, wiki_ingest_debounced

worker_config = load_worker_config()


class WorkerSettings:
    functions = [process_document, wiki_ingest, wiki_ingest_debounced]
    queue_name = worker_config.queue_name
    redis_settings = redis_settings()
    job_timeout = worker_config.job_timeout_seconds
    max_jobs = worker_config.max_jobs
