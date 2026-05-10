"""Patch the `openai` SDK's chat-completion + responses methods.

Supports the v1 OpenAI Python SDK (the `openai>=1.0` rewrite). Older
v0 (`openai.ChatCompletion.create`) is not patched here — bump SDKs.
"""

from __future__ import annotations

from typing import Any

from judge.instrument._common import wrap_sync

_unpatchers: list[Any] = []


def _request_model(kwargs: dict[str, Any]) -> str:
    return str(kwargs.get("model", ""))


def _request_messages(kwargs: dict[str, Any]) -> Any:
    # Both chat.completions and responses APIs use `messages` / `input`.
    return kwargs.get("messages") or kwargs.get("input")


def _usage(response: Any) -> dict[str, int]:
    """Pull token counts from an OpenAI response object."""
    u = getattr(response, "usage", None)
    if u is None:
        return {}
    out: dict[str, int] = {}
    in_tokens = getattr(u, "prompt_tokens", None) or getattr(u, "input_tokens", None)
    out_tokens = getattr(u, "completion_tokens", None) or getattr(u, "output_tokens", None)
    if in_tokens is not None:
        out["input_tokens"] = int(in_tokens)
    if out_tokens is not None:
        out["output_tokens"] = int(out_tokens)
    return out


def install() -> bool:
    """Patch OpenAI client classes. Returns True if patched, False if
    `openai` is not importable."""
    try:
        from openai.resources.chat.completions import (  # type: ignore[import-not-found]
            Completions as ChatCompletions,
        )
    except Exception:
        return False

    _unpatchers.append(
        wrap_sync(
            ChatCompletions,
            "create",
            span_name="openai.chat.completions",
            system="openai",
            extract_model=_request_model,
            extract_messages=_request_messages,
            extract_usage=_usage,
        )
    )

    # Newer SDKs also expose `Responses`; patch when present.
    try:
        from openai.resources.responses import (  # type: ignore[import-not-found]
            Responses,
        )

        _unpatchers.append(
            wrap_sync(
                Responses,
                "create",
                span_name="openai.responses",
                system="openai",
                extract_model=_request_model,
                extract_messages=_request_messages,
                extract_usage=_usage,
            )
        )
    except Exception:
        pass

    return True


def uninstall() -> None:
    while _unpatchers:
        _unpatchers.pop()()
