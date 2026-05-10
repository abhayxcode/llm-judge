"""Redis Streams consumer that drains ingest entries into ClickHouse.

Single consumer-group reader. Acks on successful CH insert. Failed
inserts are left pending in the stream so a future consumer (or this
one after a restart) can retry via XAUTOCLAIM. Hardening (XAUTOCLAIM
loop, dead-letter, metrics) lands in M2 once we have more than a smoke
volume of traffic.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import redis.asyncio as redis
import structlog

from judge_workers.ch_writer import ClickHouseWriter
from judge_workers.config import Settings

log = structlog.get_logger()


class StreamConsumer:
    def __init__(self, settings: Settings, writer: ClickHouseWriter) -> None:
        self.settings = settings
        self.writer = writer
        self._client: redis.Redis | None = None
        self._running = False

    async def start(self) -> None:
        self._client = redis.from_url(self.settings.redis_url, decode_responses=True)
        await self._ensure_group()
        self._running = True
        log.info(
            "stream.consumer.start",
            stream=self.settings.stream_name,
            group=self.settings.consumer_group,
            consumer=self.settings.consumer_name,
        )
        try:
            await self._loop()
        finally:
            await self._client.close()
            self.writer.close()

    def stop(self) -> None:
        self._running = False

    async def _ensure_group(self) -> None:
        assert self._client is not None
        try:
            await self._client.xgroup_create(
                name=self.settings.stream_name,
                groupname=self.settings.consumer_group,
                id="0",
                mkstream=True,
            )
            log.info("stream.group.created", group=self.settings.consumer_group)
        except redis.ResponseError as err:
            if "BUSYGROUP" in str(err):
                return
            raise

    async def _loop(self) -> None:
        assert self._client is not None
        while self._running:
            try:
                entries = await self._client.xreadgroup(
                    groupname=self.settings.consumer_group,
                    consumername=self.settings.consumer_name,
                    streams={self.settings.stream_name: ">"},
                    count=self.settings.batch_size,
                    block=self.settings.block_ms,
                )
            except redis.RedisError as err:
                log.warning("stream.read_error", err=str(err))
                await asyncio.sleep(1.0)
                continue

            if not entries:
                continue

            for _stream, messages in entries:
                for message_id, fields in messages:
                    await self._handle(message_id, fields)

    async def _handle(self, message_id: str, fields: dict[str, str]) -> None:
        assert self._client is not None
        org_id = fields.get("org_id", "default")
        project_id = fields.get("project_id", "demo")
        raw = fields.get("payload", "{}")
        try:
            payload = cast(dict[str, Any], json.loads(raw))
        except json.JSONDecodeError as err:
            log.warning("stream.bad_json", id=message_id, err=str(err))
            await self._client.xack(self.settings.stream_name, self.settings.consumer_group, message_id)
            return

        try:
            inserted = await asyncio.to_thread(self.writer.write_trace, org_id, project_id, payload)
            await self._client.xack(self.settings.stream_name, self.settings.consumer_group, message_id)
            log.info(
                "stream.consumed",
                id=message_id,
                project_id=project_id,
                trace_id=str(payload.get("trace_id", ""))[:12] + "...",
                spans=inserted,
            )
        except Exception as err:  # noqa: BLE001 — log + leave pending for retry
            log.error("stream.insert_failed", id=message_id, err=str(err))
