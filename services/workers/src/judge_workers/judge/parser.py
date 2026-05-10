"""Parse judge model output into a structured score.

CoT-before-score (per SPEC §6.3): every built-in prompt instructs the
judge to produce reasoning first, then a final score on its own line in
the form ``Score: <number>``. We parse both fields here.

Liberal in what we accept:
- "Score: 4", "score = 4/5", "Final score: 4.5".
- Reasoning is everything before the score line, trimmed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SCORE_RE = re.compile(
    r"(?im)^\s*(?:final\s+)?score\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*[0-9.]+)?\s*$"
)


@dataclass
class ParsedScore:
    score_raw: float
    reasoning: str
    matched_line: str


class ScoreParseError(ValueError):
    pass


def parse_pointwise_response(raw: str) -> ParsedScore:
    """Extract `score` and reasoning from a CoT-before-score response.

    Returns the *raw* numeric score as the judge produced it (e.g. 1..5).
    Caller is responsible for normalizing to 0.0-1.0 against the metric's
    declared scale.
    """
    if not raw or not raw.strip():
        raise ScoreParseError("empty response")

    matches = list(_SCORE_RE.finditer(raw))
    if not matches:
        # Last resort: pull the last bare number from the last line.
        last_line = raw.strip().splitlines()[-1]
        m2 = re.search(r"(\d+(?:\.\d+)?)", last_line)
        if not m2:
            raise ScoreParseError("no score found in response")
        score = float(m2.group(1))
        reasoning = raw[: raw.rfind(last_line)].strip()
        return ParsedScore(score_raw=score, reasoning=reasoning, matched_line=last_line)

    last = matches[-1]
    score = float(last.group(1))
    reasoning = raw[: last.start()].strip()
    return ParsedScore(score_raw=score, reasoning=reasoning, matched_line=last.group(0).strip())


def normalize_pointwise(score_raw: float, scale_min: float, scale_max: float) -> float:
    if scale_max == scale_min:
        return 0.0
    clamped = max(scale_min, min(scale_max, score_raw))
    return (clamped - scale_min) / (scale_max - scale_min)
