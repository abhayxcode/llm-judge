"""Judge model invocation: prompt rendering, routing, response parsing.

The router wraps litellm so we get one API across providers (Anthropic,
OpenAI, BYOM OpenAI-compatible). Cost is computed locally from a small
pricing table — litellm's own cost map is also fine but we want a stable
rate across upgrades.
"""

from __future__ import annotations

from judge_workers.judge.guards import model_family, self_enhancement
from judge_workers.judge.length import LengthAdjustment, apply_length_control
from judge_workers.judge.parser import (
    ParsedScore,
    ParsedVerdict,
    consistent_verdict,
    pairwise_score,
    parse_pairwise_response,
    parse_pointwise_response,
)
from judge_workers.judge.pricing import estimate_cost_usd
from judge_workers.judge.prompt import render_prompt
from judge_workers.judge.router import JudgeOutcome, JudgeRouter, call_judge
from judge_workers.judge.scorer import ScoreOutcome, score_pairwise, score_pointwise

__all__ = [
    "JudgeOutcome",
    "JudgeRouter",
    "LengthAdjustment",
    "ParsedScore",
    "ParsedVerdict",
    "ScoreOutcome",
    "apply_length_control",
    "call_judge",
    "consistent_verdict",
    "estimate_cost_usd",
    "model_family",
    "pairwise_score",
    "parse_pairwise_response",
    "parse_pointwise_response",
    "render_prompt",
    "score_pairwise",
    "score_pointwise",
    "self_enhancement",
]
