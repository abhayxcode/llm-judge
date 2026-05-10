"""Worker entrypoint.

M1: runs the Redis Streams consumer that drains ingest into ClickHouse.
M2+: will additionally run an Arq worker for batch eval jobs (kappa
recompute, active learning sample, scheduled bias-report regen).
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import structlog

from judge_workers.ch_writer import ClickHouseWriter
from judge_workers.config import get_settings
from judge_workers.eval_consumer import EvalConsumer
from judge_workers.stream_consumer import StreamConsumer

log = structlog.get_logger()


async def _amain() -> None:
    settings = get_settings()
    trace_writer = ClickHouseWriter(settings)
    eval_writer = ClickHouseWriter(settings)
    trace_consumer = StreamConsumer(settings, trace_writer)
    eval_consumer = EvalConsumer(settings, eval_writer)

    loop = asyncio.get_running_loop()

    def _shutdown(sig: signal.Signals) -> None:
        log.info("workers.signal", signal=sig.name)
        trace_consumer.stop()
        eval_consumer.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown, sig)
        except NotImplementedError:
            # Windows or non-main thread; let KeyboardInterrupt unwind.
            pass

    log.info("workers.startup", env=settings.env)
    await asyncio.gather(trace_consumer.start(), eval_consumer.start())
    log.info("workers.shutdown")


def run() -> None:
    asyncio.run(_amain())


# Stand-by Arq config for future eval jobs (kept for M2). Not executed
# by `judge-workers` today; consumed by `arq judge_workers.main:ArqWorker`
# when that surface lands.
class ArqWorker:
    """Arq worker placeholder for batched eval jobs (M2)."""

    functions: list[Any] = []
    queue_name = "judge-default"
    max_jobs = 10
    job_timeout = 60


if __name__ == "__main__":
    run()
