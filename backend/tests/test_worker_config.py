from pathlib import Path

import pytest

from app.workers.config import WorkerRuntimeConfig, load_worker_config


def test_load_worker_config_reads_default_pool(tmp_path: Path) -> None:
    config_path = tmp_path / "worker.toml"
    config_path.write_text(
        """
[worker.pools.default]
queue_name = "arq:queue"
job_timeout_seconds = 1800
max_jobs = 4
""".strip(),
        encoding="utf-8",
    )

    config = load_worker_config(config_path)

    assert config == WorkerRuntimeConfig(
        queue_name="arq:queue",
        job_timeout_seconds=1800,
        max_jobs=4,
    )


def test_load_worker_config_rejects_invalid_max_jobs(tmp_path: Path) -> None:
    config_path = tmp_path / "worker.toml"
    config_path.write_text(
        """
[worker.pools.default]
max_jobs = 0
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="max_jobs"):
        load_worker_config(config_path)
