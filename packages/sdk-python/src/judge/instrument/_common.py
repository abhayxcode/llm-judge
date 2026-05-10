"""Shared wrappers for sync + async LLM client method patches.

Captures OTel GenAI semconv attributes:
- gen_ai.system, gen_ai.request.model, gen_ai.response.model
- gen_ai.usage.input_tokens, gen_ai.usage.output_tokens

Outputs are truncated to keep span attribute size bounded; full bodies
land in S3 via blob_refs in M5 once the redaction pipeline is online.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from judge._trace import span as judge_span

_MAX_ATTR_CHARS = 4_000


def _truncate(s: str) -> str:
    if len(s) <= _MAX_ATTR_CHARS:
        return s
    return s[:_MAX_ATTR_CHARS] + f"...[+{len(s) - _MAX_ATTR_CHARS} chars]"


def _set_request_attrs(
    span_obj: Any,
    *,
    system: str,
    model: str,
    method: str,
    messages: Any,
) -> None:
    span_obj.log(**{"gen_ai.system": system, "gen_ai.request.model": model, "method": method})
    if messages is not None:
        try:
            payload = repr(messages)
            span_obj.log(**{"gen_ai.request.messages": _truncate(payload)})
        except Exception:
            pass


def _set_response_attrs(span_obj: Any, response: Any, *, extract_usage: Callable[[Any], dict[str, int]]) -> None:
    try:
        usage = extract_usage(response) or {}
    except Exception:
        usage = {}
    if "input_tokens" in usage:
        span_obj.log(**{"gen_ai.usage.input_tokens": int(usage["input_tokens"])})
    if "output_tokens" in usage:
        span_obj.log(**{"gen_ai.usage.output_tokens": int(usage["output_tokens"])})
    model = getattr(response, "model", None)
    if model is not None:
        span_obj.log(**{"gen_ai.response.model": str(model)})


def wrap_sync(
    target_cls: type,
    method_name: str,
    *,
    span_name: str,
    system: str,
    extract_model: Callable[[dict[str, Any]], str],
    extract_messages: Callable[[dict[str, Any]], Any],
    extract_usage: Callable[[Any], dict[str, int]],
) -> Callable[[], None]:
    """Patch a sync method on `target_cls`. Returns the un-patcher."""
    original = getattr(target_cls, method_name)

    @functools.wraps(original)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        model = extract_model(kwargs)
        with judge_span(f"{span_name}.{model or 'unknown'}", **{"gen_ai.system": system}) as s:
            _set_request_attrs(
                s,
                system=system,
                model=model,
                method=method_name,
                messages=extract_messages(kwargs),
            )
            response = original(self, *args, **kwargs)
            _set_response_attrs(s, response, extract_usage=extract_usage)
            return response

    setattr(target_cls, method_name, wrapped)

    def unpatch() -> None:
        setattr(target_cls, method_name, original)

    return unpatch
