"""Judge model invocation: prompt rendering, routing, response parsing.

The router wraps litellm so we get one API across providers (Anthropic,
OpenAI, BYOM OpenAI-compatible). Cost is computed locally from a small
pricing table — litellm's own cost map is also fine but we want a stable
rate across upgrades.
"""

from __future__ import annotations

from judge_workers.judge.parser import ParsedScore, parse_pointwise_response
from judge_workers.judge.pricing import estimate_cost_usd
from judge_workers.judge.prompt import render_prompt
from judge_workers.judge.router import JudgeOutcome, JudgeRouter

__all__ = [
    "JudgeOutcome",
    "JudgeRouter",
    "ParsedScore",
    "estimate_cost_usd",
    "parse_pointwise_response",
    "render_prompt",
]
