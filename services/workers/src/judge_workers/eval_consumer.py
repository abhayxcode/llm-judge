"""Eval-runner Redis stream consumer.

Each message on `judge:evals` carries `{run_id, record_id, row_index}`.
The consumer hydrates the run + metric IR + dataset record from PG,
calls the judge model, parses the response into a normalized score, and
writes the score row to ClickHouse.

Concurrency model: pulls N messages per XREADGROUP; processes them in
parallel via asyncio.gather. Each score insert is independent and the
runs table is updated atomically per record so partial progress is
visible immediately.

Failure handling: on judge error we still write a score row with a
`status='error'` attribute and bump `runs.error_count`. We do not retry
in M2 (litellm already retries inside `acompletion`); a future XAUTOCLAIM
loop can re-run stuck messages.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import redis.asyncio as redis
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from judge_workers.ch_writer import ClickHouseWriter
from judge_workers.config import Settings

log = structlog.get_logger()


# ---- DB rows we read by hand to avoid coupling to API's models ---------------
# (The two services share a database but ship their schemas via alembic in the
# API package; workers query via raw SQL to stay decoupled at module level.)


@dataclass
class _RunCtx:
    run_id: str
    project_id: str
    metric_slug: str
    metric_version: int
    metric_ir: dict[str, Any]
    record_count: int


@dataclass
class _Record:
    record_id: str
    row_index: int
    input: dict[str, Any]
    expected_output: str | None
    context: dict[str, Any] | None


class EvalConsumer:
    def __init__(self, settings: Settings, ch_writer: ClickHouseWriter) -> None:
        self.settings = settings
        self.ch_writer = ch_writer
        self._redis: redis.Redis | None = None
        self._engine = create_async_engine(settings.pg_async_url, pool_pre_ping=True)
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        self._running = False

    async def start(self) -> None:
        self._redis = redis.from_url(self.settings.redis_url, decode_responses=True)
        await self._ensure_group()
        self._running = True
        log.info(
            "eval.consumer.start",
            stream=self.settings.eval_stream_name,
            group=self.settings.eval_consumer_group,
            consumer=self.settings.eval_consumer_name,
        )
        try:
            await self._loop()
        finally:
            await self._redis.close()
            await self._engine.dispose()
            self.ch_writer.close()

    def stop(self) -> None:
        self._running = False

    async def _ensure_group(self) -> None:
        assert self._redis is not None
        try:
            await self._redis.xgroup_create(
                name=self.settings.eval_stream_name,
                groupname=self.settings.eval_consumer_group,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as err:
            if "BUSYGROUP" in str(err):
                return
            raise

    async def _loop(self) -> None:
        assert self._redis is not None
        sem = asyncio.Semaphore(self.settings.eval_concurrency)
        while self._running:
            try:
                entries = await self._redis.xreadgroup(
                    groupname=self.settings.eval_consumer_group,
                    consumername=self.settings.eval_consumer_name,
                    streams={self.settings.eval_stream_name: ">"},
                    count=self.settings.eval_concurrency,
                    block=self.settings.block_ms,
                )
            except redis.RedisError as err:
                log.warning("eval.read_error", err=str(err))
                await asyncio.sleep(1.0)
                continue

            if not entries:
                continue

            tasks: list[asyncio.Task[None]] = []
            for _stream, messages in entries:
                for message_id, fields in messages:
                    tasks.append(asyncio.create_task(self._handle(message_id, fields, sem)))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle(
        self, message_id: str, fields: dict[str, str], sem: asyncio.Semaphore
    ) -> None:
        assert self._redis is not None
        async with sem:
            raw = fields.get("payload", "{}")
            try:
                payload = cast(dict[str, Any], json.loads(raw))
            except json.JSONDecodeError as err:
                log.warning("eval.bad_json", id=message_id, err=str(err))
                await self._ack(message_id)
                return

            run_id = str(payload.get("run_id", ""))
            record_id = str(payload.get("record_id", ""))
            row_index = int(payload.get("row_index", 0))

            try:
                await self._process(run_id, record_id, row_index)
                await self._ack(message_id)
            except Exception as err:
                log.error(
                    "eval.process_failed",
                    id=message_id,
                    run_id=run_id,
                    record_id=record_id,
                    err=str(err),
                )

    async def _ack(self, message_id: str) -> None:
        assert self._redis is not None
        await self._redis.xack(
            self.settings.eval_stream_name,
            self.settings.eval_consumer_group,
            message_id,
        )

    async def _process(self, run_id: str, record_id: str, row_index: int) -> None:
        from judge_workers.judge import (
            call_judge,
            parse_pointwise_response,
            render_prompt,
        )
        from judge_workers.judge.parser import ScoreParseError, normalize_pointwise

        async with self._sessionmaker() as session:
            ctx = await self._load_run_ctx(session, run_id)
            record = await self._load_record(session, record_id)
            if ctx is None or record is None:
                log.warning(
                    "eval.missing_run_or_record", run_id=run_id, record_id=record_id
                )
                return

        prompt_vars: dict[str, Any] = {}
        prompt_vars.update(record.input or {})
        if record.expected_output is not None:
            prompt_vars.setdefault("expected_output", record.expected_output)
        if record.context is not None:
            prompt_vars.setdefault(
                "context",
                record.context if isinstance(record.context, str) else json.dumps(record.context),
            )

        scoring_type = ctx.metric_ir.get("scoring_type", "pointwise")
        scale = ctx.metric_ir.get("scale", {}) or {}
        scale_min = float(scale.get("min", 0))
        scale_max = float(scale.get("max", 1))
        judge_config = ctx.metric_ir.get("judge_config", {})
        prompt_template = ctx.metric_ir["prompt_template"]

        try:
            rendered = render_prompt(prompt_template, prompt_vars)
            outcome = await call_judge(rendered, judge_config)
            try:
                parsed = parse_pointwise_response(outcome.text)
                score_norm = normalize_pointwise(parsed.score_raw, scale_min, scale_max)
                score_raw_str = f"{parsed.score_raw}"
                reasoning = parsed.reasoning
                error_attr = ""
            except ScoreParseError as err:
                score_norm = 0.0
                score_raw_str = ""
                reasoning = f"PARSE_ERROR: {err}\n\n{outcome.text}"
                error_attr = "parse_error"

            score_row = {
                "org_id": "default",
                "project_id": ctx.project_id,
                "trace_id": record.record_id,  # offline runs key by record_id
                "span_id": None,
                "metric_id": ctx.metric_slug,
                "metric_version": str(ctx.metric_version),
                "score": float(score_norm),
                "score_raw": score_raw_str,
                "reasoning": reasoning,
                "label": None,
                "judge_model": outcome.model,
                "judge_provider": outcome.provider,
                "cost_usd": float(outcome.cost_usd),
                "latency_ms": int(outcome.latency_ms),
                "self_enhancement_warning": 0,
                "position_swapped": 0,
                "consistency": None,
                "computed_at": datetime.now(UTC),
                "attributes": {
                    "run_id": run_id,
                    "record_id": record_id,
                    "row_index": str(row_index),
                    "scoring_type": scoring_type,
                    **({"error": error_attr} if error_attr else {}),
                    **(
                        {"input_tokens": str(outcome.input_tokens)}
                        if outcome.input_tokens
                        else {}
                    ),
                    **(
                        {"output_tokens": str(outcome.output_tokens)}
                        if outcome.output_tokens
                        else {}
                    ),
                    **({"fallback_used": "1"} if outcome.fallback_used else {}),
                },
            }
            await asyncio.to_thread(self.ch_writer.write_score, score_row)
            had_error = bool(error_attr)
        except Exception as err:
            log.error("eval.judge_failed", run_id=run_id, record_id=record_id, err=str(err))
            error_row = {
                "org_id": "default",
                "project_id": ctx.project_id,
                "trace_id": record.record_id,
                "span_id": None,
                "metric_id": ctx.metric_slug,
                "metric_version": str(ctx.metric_version),
                "score": 0.0,
                "score_raw": "",
                "reasoning": f"JUDGE_ERROR: {err}",
                "label": None,
                "judge_model": "",
                "judge_provider": "",
                "cost_usd": 0.0,
                "latency_ms": 0,
                "self_enhancement_warning": 0,
                "position_swapped": 0,
                "consistency": None,
                "computed_at": datetime.now(UTC),
                "attributes": {
                    "run_id": run_id,
                    "record_id": record_id,
                    "row_index": str(row_index),
                    "scoring_type": scoring_type,
                    "error": "judge_error",
                },
            }
            await asyncio.to_thread(self.ch_writer.write_score, error_row)
            had_error = True

        await self._bump_progress(run_id, errored=had_error)

    async def _load_run_ctx(self, session: AsyncSession, run_id: str) -> _RunCtx | None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT r.id, r.project_id, r.record_count,
                           m.slug AS metric_slug, mv.version, mv.ir
                    FROM runs r
                    JOIN metric_versions mv ON mv.id = r.metric_version_id
                    JOIN metrics m ON m.id = mv.metric_id
                    WHERE r.id = :run_id
                    """
                ),
                {"run_id": run_id},
            )
        ).mappings().first()
        if row is None:
            return None
        ir = row["ir"]
        if isinstance(ir, str):
            ir = json.loads(ir)
        return _RunCtx(
            run_id=row["id"],
            project_id=row["project_id"],
            record_count=row["record_count"],
            metric_slug=row["metric_slug"],
            metric_version=row["version"],
            metric_ir=ir,
        )

    async def _load_record(self, session: AsyncSession, record_id: str) -> _Record | None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, row_index, input, expected_output, context
                    FROM dataset_records WHERE id = :rid
                    """
                ),
                {"rid": record_id},
            )
        ).mappings().first()
        if row is None:
            return None
        inp = row["input"]
        ctx = row["context"]
        if isinstance(inp, str):
            inp = json.loads(inp)
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        return _Record(
            record_id=row["id"],
            row_index=row["row_index"],
            input=inp or {},
            expected_output=row["expected_output"],
            context=ctx,
        )

    async def _bump_progress(self, run_id: str, *, errored: bool) -> None:
        """Atomically bump completed_count and flip status when done."""
        sql = """
            UPDATE runs
            SET
                completed_count = completed_count + 1,
                error_count = error_count + :err_inc,
                started_at = COALESCE(started_at, now()),
                status = CASE
                    WHEN completed_count + 1 >= record_count THEN 'done'
                    ELSE 'running'
                END,
                finished_at = CASE
                    WHEN completed_count + 1 >= record_count THEN now()
                    ELSE finished_at
                END
            WHERE id = :run_id
        """
        async with self._sessionmaker() as session:
            await session.execute(text(sql), {"run_id": run_id, "err_inc": 1 if errored else 0})
            await session.commit()
