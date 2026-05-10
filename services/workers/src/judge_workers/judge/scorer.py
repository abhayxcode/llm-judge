"""Scoring strategies — pointwise + pairwise.

Each strategy takes the rendered prompt vars + metric IR + a judge call
function and returns a ScoreOutcome the eval consumer can serialize.
Keeping the strategies in pure functions makes them easy to unit test
without spinning up Redis/PG.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from judge_workers.judge.parser import (
    ParsedScore,
    ParsedVerdict,
    ScoreParseError,
    consistent_verdict,
    normalize_pointwise,
    pairwise_score,
    parse_pairwise_response,
    parse_pointwise_response,
)
from judge_workers.judge.prompt import render_prompt
from judge_workers.judge.router import JudgeOutcome


@dataclass
class ScoreOutcome:
    score: float  # normalized 0-1
    score_raw: str  # original judge-emitted form
    reasoning: str
    label: str | None = None  # "A"|"B"|"tie" for pairwise, None otherwise
    position_swapped: int = 0
    consistency: float | None = None
    judge_model: str = ""
    judge_provider: str = ""
    cost_usd: float = 0.0
    latency_ms: int = 0
    fallback_used: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    error_attr: str = ""
    extra_attrs: dict[str, str] = field(default_factory=dict)


JudgeCall = Callable[[str, dict[str, Any]], Awaitable[JudgeOutcome]]


async def score_pointwise(
    *,
    prompt_template: str,
    prompt_vars: dict[str, Any],
    judge_config: dict[str, Any],
    scale_min: float,
    scale_max: float,
    call_judge: JudgeCall,
) -> ScoreOutcome:
    rendered = render_prompt(prompt_template, prompt_vars)
    outcome = await call_judge(rendered, judge_config)
    try:
        parsed: ParsedScore = parse_pointwise_response(outcome.text)
        return ScoreOutcome(
            score=normalize_pointwise(parsed.score_raw, scale_min, scale_max),
            score_raw=str(parsed.score_raw),
            reasoning=parsed.reasoning,
            judge_model=outcome.model,
            judge_provider=outcome.provider,
            cost_usd=outcome.cost_usd,
            latency_ms=outcome.latency_ms,
            fallback_used=outcome.fallback_used,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
        )
    except ScoreParseError as err:
        return ScoreOutcome(
            score=0.0,
            score_raw="",
            reasoning=f"PARSE_ERROR: {err}\n\n{outcome.text}",
            judge_model=outcome.model,
            judge_provider=outcome.provider,
            cost_usd=outcome.cost_usd,
            latency_ms=outcome.latency_ms,
            fallback_used=outcome.fallback_used,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            error_attr="parse_error",
        )


async def score_pairwise(
    *,
    prompt_template: str,
    prompt_vars: dict[str, Any],
    judge_config: dict[str, Any],
    call_judge: JudgeCall,
    a_key: str = "output_a",
    b_key: str = "output_b",
) -> ScoreOutcome:
    """Two-pass pairwise with mandatory position swap.

    Inputs must contain `{{output_a}}` and `{{output_b}}` (configurable
    via `a_key`/`b_key`). The second pass swaps them and re-renders;
    only verdicts that agree post-swap are decisive (per SPEC §6.3).
    Returns score from output_a's POV: A=1.0, tie=0.5, B=0.0.
    """
    if a_key not in prompt_vars or b_key not in prompt_vars:
        raise ScoreParseError(
            f"pairwise scoring requires '{a_key}' and '{b_key}' in record input"
        )

    first_rendered = render_prompt(prompt_template, prompt_vars)
    swapped_vars = {
        **prompt_vars,
        a_key: prompt_vars[b_key],
        b_key: prompt_vars[a_key],
    }
    swapped_rendered = render_prompt(prompt_template, swapped_vars)

    first = await call_judge(first_rendered, judge_config)
    swapped = await call_judge(swapped_rendered, judge_config)

    try:
        v1: ParsedVerdict = parse_pairwise_response(first.text)
        v2: ParsedVerdict = parse_pairwise_response(swapped.text)
        verdict, consistency = consistent_verdict(v1.verdict, v2.verdict)
        score = pairwise_score(verdict)
        reasoning = (
            f"Pass 1 (a/b): {v1.verdict}\n{v1.reasoning}\n\n"
            f"Pass 2 (b/a swapped): {v2.verdict}\n{v2.reasoning}"
        )
        error_attr = ""
        score_raw = f"v1={v1.verdict};v2={v2.verdict}"
    except ScoreParseError as err:
        verdict = "tie"
        consistency = 0.0
        score = 0.5
        reasoning = f"PARSE_ERROR: {err}\n\n--- pass 1 ---\n{first.text}\n\n--- pass 2 ---\n{swapped.text}"
        error_attr = "parse_error"
        score_raw = ""

    return ScoreOutcome(
        score=score,
        score_raw=score_raw,
        reasoning=reasoning,
        label=verdict,
        position_swapped=1,
        consistency=consistency,
        judge_model=first.model,
        judge_provider=first.provider,
        cost_usd=first.cost_usd + swapped.cost_usd,
        latency_ms=first.latency_ms + swapped.latency_ms,
        fallback_used=first.fallback_used or swapped.fallback_used,
        input_tokens=first.input_tokens + swapped.input_tokens,
        output_tokens=first.output_tokens + swapped.output_tokens,
        error_attr=error_attr,
    )
