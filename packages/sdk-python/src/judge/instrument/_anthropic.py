"""Patch the `anthropic` SDK's messages.create method."""

from __future__ import annotations

from typing import Any

from judge.instrument._common import wrap_sync

_unpatchers: list[Any] = []


def _request_model(kwargs: dict[str, Any]) -> str:
    return str(kwargs.get("model", ""))


def _request_messages(kwargs: dict[str, Any]) -> Any:
    return kwargs.get("messages")


def _usage(response: Any) -> dict[str, int]:
    u = getattr(response, "usage", None)
    if u is None:
        return {}
    out: dict[str, int] = {}
    in_tokens = getattr(u, "input_tokens", None)
    out_tokens = getattr(u, "output_tokens", None)
    if in_tokens is not None:
        out["input_tokens"] = int(in_tokens)
    if out_tokens is not None:
        out["output_tokens"] = int(out_tokens)
    return out


def install() -> bool:
    try:
        from anthropic.resources.messages import Messages  # type: ignore[import-not-found]
    except Exception:
        return False

    _unpatchers.append(
        wrap_sync(
            Messages,
            "create",
            span_name="anthropic.messages",
            system="anthropic",
            extract_model=_request_model,
            extract_messages=_request_messages,
            extract_usage=_usage,
        )
    )
    return True


def uninstall() -> None:
    while _unpatchers:
        _unpatchers.pop()()
