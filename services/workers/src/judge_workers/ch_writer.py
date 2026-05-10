"""ClickHouse writer for ingested spans.

Decomposes the SDK trace payload (one trace + N spans) into rows for the
`spans` table. M1 keeps everything synchronous on the consumer thread;
batching + async insert come in M2 alongside the eval engine when write
volume justifies the extra moving parts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import clickhouse_connect
import structlog

from judge_workers.config import Settings

log = structlog.get_logger()


# Column order must match the INSERT statement below.
_COLUMNS = (
    "org_id",
    "project_id",
    "trace_id",
    "span_id",
    "parent_span_id",
    "trace_name",
    "name",
    "start_ts",
    "end_ts",
    "status",
    "error",
    "gen_ai_system",
    "gen_ai_model",
    "input_tokens",
    "output_tokens",
    "attributes",
    "blob_refs",
    "sdk_version",
    "sdk_lang",
)


class ClickHouseWriter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = clickhouse_connect.get_client(
            host=settings.ch_host,
            port=settings.ch_http_port,
            username=settings.ch_user,
            password=settings.ch_password,
            database=settings.ch_db,
        )

    def write_trace(self, org_id: str, project_id: str, payload: dict[str, Any]) -> int:
        """Write all spans of one trace. Returns number of rows inserted."""
        trace_id = str(payload.get("trace_id", ""))
        if not trace_id:
            log.warning("trace.missing_id", payload_keys=list(payload.keys()))
            return 0

        trace_name = str(payload.get("name", "")) or "unnamed"
        sdk_lang = str(payload.get("sdk_lang", ""))
        sdk_version = str(payload.get("sdk_version", ""))

        rows: list[list[Any]] = []
        spans = payload.get("spans") or []
        if not isinstance(spans, list):
            log.warning("trace.spans_not_list", trace_id=trace_id)
            return 0

        for span in spans:
            if not isinstance(span, dict):
                continue
            rows.append(_span_to_row(org_id, project_id, trace_id, trace_name, sdk_version, sdk_lang, span))

        if not rows:
            return 0

        self._client.insert("spans", rows, column_names=list(_COLUMNS))
        return len(rows)

    def close(self) -> None:
        self._client.close()


def _span_to_row(
    org_id: str,
    project_id: str,
    trace_id: str,
    trace_name: str,
    sdk_version: str,
    sdk_lang: str,
    span: dict[str, Any],
) -> list[Any]:
    span_id = str(span.get("span_id", ""))
    parent_id = span.get("parent_id")
    name = str(span.get("name", trace_name))

    start_ts = _ms_to_dt(span.get("start_ms"))
    end_ts = _ms_to_dt(span.get("end_ms"))

    status = str(span.get("status", "ok")) or "ok"
    error = span.get("error")

    attrs = _stringify_attrs(span.get("attributes") or {})
    gen_ai_system = attrs.pop("gen_ai.system", "")
    gen_ai_model = attrs.pop("gen_ai.model", "")
    input_tokens = _safe_int(attrs.pop("gen_ai.usage.input_tokens", "0"))
    output_tokens = _safe_int(attrs.pop("gen_ai.usage.output_tokens", "0"))

    blob_refs: dict[str, str] = {}

    return [
        org_id,
        project_id,
        trace_id,
        span_id,
        parent_id,
        trace_name,
        name,
        start_ts,
        end_ts,
        status,
        error,
        gen_ai_system,
        gen_ai_model,
        input_tokens,
        output_tokens,
        attrs,
        blob_refs,
        sdk_version,
        sdk_lang,
    ]


def _ms_to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def _stringify_attrs(attrs: dict[str, Any]) -> dict[str, str]:
    """Map(String, String) requires string values. Non-strings are JSON-encoded."""
    import json

    out: dict[str, str] = {}
    for k, v in attrs.items():
        if isinstance(v, str):
            out[str(k)] = v
        else:
            out[str(k)] = json.dumps(v, default=str)
    return out


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
