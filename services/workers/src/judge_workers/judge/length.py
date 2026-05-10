"""Length-bias mitigation knobs.

Modes:
- `off` — no adjustment (default).
- `penalty` — subtract `penalty_per_100_tokens * tokens / 100` from the
  normalized score; clamp to [0, 1]. Cheap, deterministic.
- `matched_sample` — record-level tag only. Calibration (M4) buckets
  records by token count so judge-vs-human comparisons stay fair.

Token estimate uses a 4-chars-per-token heuristic when no tokenizer is
available. Real tokenization comes in M5 with the BYO tokenizer hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LengthAdjustment:
    score: float
    delta: float  # how much we moved the score (negative = penalty applied)
    mode: str
    tokens_estimate: int


def estimate_tokens(text: str) -> int:
    """Cheap heuristic: ~4 chars per token. Replaced in M5."""
    return max(0, len(text) // 4)


def apply_length_control(
    score: float,
    output_text: str,
    length_control: dict[str, Any] | None,
) -> LengthAdjustment:
    mode = (length_control or {}).get("mode", "off")
    tokens = estimate_tokens(output_text)
    if mode == "penalty":
        rate = float((length_control or {}).get("penalty_per_100_tokens", 0.0))
        penalty = rate * tokens / 100.0
        adjusted = max(0.0, min(1.0, score - penalty))
        return LengthAdjustment(score=adjusted, delta=adjusted - score, mode=mode, tokens_estimate=tokens)
    # `matched_sample` and `off` both leave the score alone; the tag is
    # propagated via attributes so calibration can pick it up later.
    return LengthAdjustment(score=score, delta=0.0, mode=mode, tokens_estimate=tokens)
