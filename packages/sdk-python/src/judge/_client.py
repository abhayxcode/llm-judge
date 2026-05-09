"""HTTP client to the ingest service.

M1 skeleton: synchronous, one POST per trace, no batching, no retries.
M2+ adds an async batched sender on a background thread.
"""

from __future__ import annotations

from typing import Any

import httpx

from judge._config import get_config


def send_trace(payload: dict[str, Any]) -> None:
    cfg = get_config()
    headers = {"content-type": "application/json"}
    if cfg.api_key:
        headers["authorization"] = f"Bearer {cfg.api_key}"
    if cfg.project:
        headers["x-judge-project"] = cfg.project

    url = f"{cfg.endpoint.rstrip('/')}/v1/traces"
    try:
        with httpx.Client(timeout=cfg.timeout_s) as client:
            client.post(url, json=payload, headers=headers)
    except httpx.HTTPError:
        # Skeleton: swallow errors so user code never breaks because the SDK
        # can't reach the ingest service. Replaced by retry+queue in M2+.
        return
