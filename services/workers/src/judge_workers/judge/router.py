"""Judge router — calls the configured model via litellm with fallback.

Inputs: a fully-rendered prompt + JudgeConfig dict.
Outputs: JudgeOutcome with raw text, token counts, latency, cost.

Retry policy (M2):
- Single retry on transient errors (429/5xx/timeout) before falling back.
- After the second failure on the primary, try `fallback_model` once.
- Any further failure raises and the worker writes an error score row.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import litellm  # type: ignore[import-untyped]

from judge_workers.judge.pricing import estimate_cost_usd

log = logging.getLogger(__name__)


@dataclass
class JudgeOutcome:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    fallback_used: bool


class JudgeRouter:
    """Thin wrapper around litellm.acompletion with one fallback."""

    async def call(
        self,
        prompt: str,
        *,
        judge_config: dict[str, Any],
    ) -> JudgeOutcome:
        primary = judge_config.get("model", "anthropic/claude-sonnet-4-6")
        fallback = judge_config.get("fallback_model")
        temperature = float(judge_config.get("temperature", 0.0))
        max_tokens = int(judge_config.get("max_tokens", 1024))
        api_base = judge_config.get("api_base")
        timeout_s = float(judge_config.get("timeout_s", 60.0))

        try:
            return await self._invoke(
                primary, prompt, temperature, max_tokens, api_base, timeout_s, fallback_used=False
            )
        except Exception as exc:
            log.warning("judge.primary_failed", extra={"model": primary, "error": str(exc)})
            if not fallback:
                raise
        return await self._invoke(
            fallback, prompt, temperature, max_tokens, None, timeout_s, fallback_used=True
        )

    async def _invoke(
        self,
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        api_base: str | None,
        timeout_s: float,
        *,
        fallback_used: bool,
    ) -> JudgeOutcome:
        start = time.monotonic()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout_s,
            "num_retries": 1,
        }
        if api_base:
            kwargs["api_base"] = api_base

        resp = await litellm.acompletion(**kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)

        choice = resp["choices"][0]
        text = choice["message"]["content"] or ""
        usage = resp.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        provider = model.split("/", 1)[0] if "/" in model else "unknown"
        cost = estimate_cost_usd(model, input_tokens, output_tokens)

        return JudgeOutcome(
            text=text,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            fallback_used=fallback_used,
        )


_default = JudgeRouter()


async def call_judge(prompt: str, judge_config: dict[str, Any]) -> JudgeOutcome:
    return await _default.call(prompt, judge_config=judge_config)


# Convenience: synchronous helper for tests + scripts that don't already
# have a running event loop.
def call_judge_sync(prompt: str, judge_config: dict[str, Any]) -> JudgeOutcome:
    return asyncio.run(_default.call(prompt, judge_config=judge_config))
