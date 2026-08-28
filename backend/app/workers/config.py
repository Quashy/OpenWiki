from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib


DEFAULT_WORKER_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "worker.toml"


@dataclass(frozen=True, slots=True)
class WorkerRuntimeConfig:
    queue_name: str = "arq:queue"
    job_timeout_seconds: int = 1800
    max_jobs: int = 4


def load_worker_config(path: Path = DEFAULT_WORKER_CONFIG_PATH, pool_name: str = "default") -> WorkerRuntimeConfig:
    if not path.exists():
        return WorkerRuntimeConfig()

    with path.open("rb") as file:
        data = tomllib.load(file)

    pool = _pool_config(data, pool_name)
    return WorkerRuntimeConfig(
        queue_name=_string_value(pool.get("queue_name"), default="arq:queue"),
        job_timeout_seconds=_positive_int(
            pool.get("job_timeout_seconds"),
            default=1800,
            name="job_timeout_seconds",
        ),
        max_jobs=_positive_int(pool.get("max_jobs"), default=4, name="max_jobs"),
    )


def _pool_config(data: dict[str, Any], pool_name: str) -> dict[str, Any]:
    worker = data.get("worker")
    if not isinstance(worker, dict):
        return {}
    pools = worker.get("pools")
    if not isinstance(pools, dict):
        return {}
    pool = pools.get(pool_name)
    return pool if isinstance(pool, dict) else {}


def _positive_int(value: Any, *, default: int, name: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"worker config {name} must be a positive integer")
    return value


def _string_value(value: Any, *, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ValueError("worker config queue_name must be a non-empty string")
    return value
