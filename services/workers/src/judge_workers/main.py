"""Arq worker entrypoint."""

from __future__ import annotations

from typing import Any

import structlog
from arq.connections import RedisSettings

from judge_workers.config import get_settings
from judge_workers.jobs.ping import ping

log = structlog.get_logger()


async def startup(_ctx: dict[str, Any]) -> None:
    log.info("workers.startup")


async def shutdown(_ctx: dict[str, Any]) -> None:
    log.info("workers.shutdown")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """Arq worker configuration. Loaded by `arq judge_workers.main.WorkerSettings`."""

    functions: list[Any] = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    queue_name = get_settings().queue_name
    max_jobs = 10
    job_timeout = 60


def run() -> None:
    from arq import run_worker

    run_worker(WorkerSettings)


if __name__ == "__main__":
    run()
