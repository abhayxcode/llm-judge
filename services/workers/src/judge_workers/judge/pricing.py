"""Per-model pricing table (USD per 1M tokens).

Kept small + hand-curated for M2; we'll plug in a richer source later.
Values reflect public pricing as of 2026-05; treat as stable across an
M-cycle so cost rollups don't move under our feet mid-run.

Anyone adding a model: add the row here. Unknown models cost 0 — the
worker logs a warning so misconfigured BYOM gateways stick out.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# (input_per_1m, output_per_1m). USD.
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "anthropic/claude-sonnet-4-6": (3.00, 15.00),
    "anthropic/claude-opus-4-7": (15.00, 75.00),
    "anthropic/claude-haiku-4-5": (1.00, 5.00),
    # OpenAI
    "openai/gpt-4o": (2.50, 10.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4.1-mini": (0.40, 1.60),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = PRICING.get(model)
    if rate is None:
        log.warning("pricing.unknown_model", extra={"model": model})
        return 0.0
    in_rate, out_rate = rate
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000.0
