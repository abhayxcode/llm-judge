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


_VERDICT_RE = re.compile(
    r"(?im)^\s*(?:final\s+)?(?:verdict|winner|judgment)\s*[:=]\s*([A-Za-z]+)\s*$"
)
# Tokens we accept for each side. Anything else falls through to "tie".
_A_TOKENS = {"a", "A", "answer_a", "output_a", "first", "left"}
_B_TOKENS = {"b", "B", "answer_b", "output_b", "second", "right"}
_TIE_TOKENS = {"tie", "draw", "equal", "neither", "both"}


@dataclass
class ParsedVerdict:
    verdict: str  # "A" | "B" | "tie"
    reasoning: str
    matched_line: str


def parse_pairwise_response(raw: str) -> ParsedVerdict:
    """Extract a pairwise verdict.

    Prompt convention: judge emits reasoning first, then a final line
    like ``Verdict: A`` (also accepts Winner/Judgment, and tokens
    answer_a/first/etc). Anything we can't classify becomes a tie.
    """
    if not raw or not raw.strip():
        raise ScoreParseError("empty response")

    matches = list(_VERDICT_RE.finditer(raw))
    if not matches:
        # Loose fallback: scan the last few lines for a bare A/B token.
        tail = "\n".join(raw.strip().splitlines()[-3:]).lower()
        verdict = _classify_token(tail)
        return ParsedVerdict(verdict=verdict, reasoning=raw.strip(), matched_line="")

    last = matches[-1]
    token = last.group(1).strip().lower()
    verdict = _classify_token(token)
    reasoning = raw[: last.start()].strip()
    return ParsedVerdict(
        verdict=verdict, reasoning=reasoning, matched_line=last.group(0).strip()
    )


def _classify_token(token: str) -> str:
    t = token.strip().lower()
    if t in _TIE_TOKENS:
        return "tie"
    a_lower = {x.lower() for x in _A_TOKENS}
    b_lower = {x.lower() for x in _B_TOKENS}
    if t in a_lower:
        return "A"
    if t in b_lower:
        return "B"
    # Loose fallback for free-text tail: scan whitespace-separated words
    # for an exact A/B token. Avoids matching the "a" in "maybe".
    for word in re.findall(r"[A-Za-z_]+", t):
        if word in a_lower:
            return "A"
        if word in b_lower:
            return "B"
        if word in _TIE_TOKENS:
            return "tie"
    return "tie"


def consistent_verdict(first: str, swapped: str) -> tuple[str, float]:
    """Combine the two-pass pairwise verdicts.

    `first` is the verdict when output_a is in slot A; `swapped` is the
    verdict after we swapped slots, so an "A" answer there means the
    judge picked the *original* B. Per SPEC §6.3, only consistent
    verdicts are decisive; otherwise we record a tie with consistency=0.

    Returns (final_verdict, consistency) where final is "A"|"B"|"tie"
    referring to the *original* output_a / output_b ordering.
    """
    if first == "tie" or swapped == "tie":
        return "tie", 0.0
    # After swap: a "A" in `swapped` means the judge picked the new
    # slot-A, which corresponds to the *original* B.
    swapped_normalized = "B" if swapped == "A" else "A"
    if first == swapped_normalized:
        return first, 1.0
    return "tie", 0.0


def pairwise_score(verdict: str) -> float:
    """Map A=1.0, tie=0.5, B=0.0 — score from output_a's POV."""
    return {"A": 1.0, "B": 0.0, "tie": 0.5}.get(verdict, 0.5)
