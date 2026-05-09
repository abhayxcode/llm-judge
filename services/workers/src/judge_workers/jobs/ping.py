"""Smoke-test job. Replaced by real eval-runner / kappa / drift jobs in M2+."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger()


async def ping(_ctx: dict[str, Any], message: str = "pong") -> dict[str, str]:
    now = datetime.now(UTC).isoformat()
    log.info("ping", message=message, time=now)
    return {"message": message, "time": now}
