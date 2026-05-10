"""Scoring strategies + length + self-enhancement guard."""

from __future__ import annotations

from typing import Any

import pytest
from judge_workers.judge import (
    apply_length_control,
    model_family,
    score_pairwise,
    score_pointwise,
    self_enhancement,
)
from judge_workers.judge.parser import ScoreParseError
from judge_workers.judge.router import JudgeOutcome


class _Recorder:
    """Stand-in for call_judge: returns canned text in order, records calls."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[str] = []

    async def __call__(self, prompt: str, judge_config: dict[str, Any]) -> JudgeOutcome:
        self.calls.append(prompt)
        text = self._replies.pop(0)
        return JudgeOutcome(
            text=text,
            model=judge_config.get("model", "anthropic/claude-sonnet-4-6"),
            provider="anthropic",
            input_tokens=10,
            output_tokens=20,
            latency_ms=100,
            cost_usd=0.001,
            fallback_used=False,
        )


# ---- pointwise ----------------------------------------------------------

async def test_score_pointwise_normalizes() -> None:
    judge = _Recorder(["Reasoning.\nScore: 4"])
    out = await score_pointwise(
        prompt_template="rate {{x}}",
        prompt_vars={"x": "y"},
        judge_config={},
        scale_min=1,
        scale_max=5,
        call_judge=judge,
    )
    assert out.score == 0.75  # (4-1)/(5-1)
    assert out.reasoning == "Reasoning."
    assert out.error_attr == ""
    assert len(judge.calls) == 1


async def test_score_pointwise_parse_error_recovers() -> None:
    judge = _Recorder(["no number here"])
    out = await score_pointwise(
        prompt_template="rate {{x}}",
        prompt_vars={"x": "y"},
        judge_config={},
        scale_min=1,
        scale_max=5,
        call_judge=judge,
    )
    assert out.error_attr == "parse_error"
    assert out.score == 0.0


# ---- pairwise -----------------------------------------------------------

async def test_score_pairwise_decisive_a_wins() -> None:
    # Pass 1: judge picks A. Pass 2 (b/a swapped): judge picks B (i.e.
    # the original A in slot B). Consistent → A wins.
    judge = _Recorder(["Verdict: A", "Verdict: B"])
    out = await score_pairwise(
        prompt_template="compare {{output_a}} vs {{output_b}}",
        prompt_vars={"output_a": "good", "output_b": "bad"},
        judge_config={},
        call_judge=judge,
    )
    assert out.label == "A"
    assert out.score == 1.0
    assert out.consistency == 1.0
    assert out.position_swapped == 1
    assert len(judge.calls) == 2
    # Both calls must contain the original substrings (swap shows up by
    # virtue of being passed to render twice).
    assert "good" in judge.calls[0]
    assert "bad" in judge.calls[0]
    assert "good" in judge.calls[1]
    assert "bad" in judge.calls[1]


async def test_score_pairwise_position_bias_collapses_to_tie() -> None:
    # Both passes pick "slot A" → judge always picks first → tie.
    judge = _Recorder(["Verdict: A", "Verdict: A"])
    out = await score_pairwise(
        prompt_template="{{output_a}}{{output_b}}",
        prompt_vars={"output_a": "x", "output_b": "y"},
        judge_config={},
        call_judge=judge,
    )
    assert out.label == "tie"
    assert out.score == 0.5
    assert out.consistency == 0.0


async def test_score_pairwise_missing_inputs_raises() -> None:
    judge = _Recorder([])
    with pytest.raises(ScoreParseError):
        await score_pairwise(
            prompt_template="x",
            prompt_vars={"output_a": "only A here"},
            judge_config={},
            call_judge=judge,
        )


async def test_score_pairwise_costs_are_summed() -> None:
    judge = _Recorder(["Verdict: A", "Verdict: B"])
    out = await score_pairwise(
        prompt_template="{{output_a}}{{output_b}}",
        prompt_vars={"output_a": "x", "output_b": "y"},
        judge_config={},
        call_judge=judge,
    )
    assert out.cost_usd == pytest.approx(0.002)
    assert out.latency_ms == 200
    assert out.input_tokens == 20


# ---- length control -----------------------------------------------------

def test_length_control_off_is_identity() -> None:
    adj = apply_length_control(0.8, "x" * 400, {"mode": "off"})
    assert adj.score == 0.8
    assert adj.delta == 0.0


def test_length_control_penalty_subtracts() -> None:
    # 400 chars / 4 = 100 tokens; rate 0.1 → -0.1.
    adj = apply_length_control(
        0.8, "x" * 400, {"mode": "penalty", "penalty_per_100_tokens": 0.1}
    )
    assert adj.score == pytest.approx(0.7, abs=1e-6)
    assert adj.delta == pytest.approx(-0.1, abs=1e-6)


def test_length_control_penalty_clamps_floor() -> None:
    adj = apply_length_control(
        0.05, "x" * 4000, {"mode": "penalty", "penalty_per_100_tokens": 0.5}
    )
    assert adj.score == 0.0  # clamped


def test_length_control_matched_sample_tags_only() -> None:
    adj = apply_length_control(0.8, "x" * 400, {"mode": "matched_sample"})
    assert adj.score == 0.8
    assert adj.mode == "matched_sample"
    assert adj.tokens_estimate == 100


# ---- self-enhancement guard --------------------------------------------

def test_model_family_litellm_format() -> None:
    assert model_family("anthropic/claude-sonnet-4-6") == "anthropic"
    assert model_family("openai/gpt-4o-mini") == "openai"


def test_model_family_bare_strings() -> None:
    assert model_family("claude-3-opus") == "anthropic"
    assert model_family("gemini-1.5-pro") == "google"
    assert model_family("llama-3-70b") == "meta"


def test_model_family_unknown() -> None:
    assert model_family("totally-novel-model") == "unknown"
    assert model_family("") == "unknown"


def test_self_enhancement_same_family() -> None:
    assert self_enhancement("anthropic/claude-sonnet-4-6", "claude-3-opus") is True


def test_self_enhancement_different_family() -> None:
    assert (
        self_enhancement("anthropic/claude-sonnet-4-6", "openai/gpt-4o-mini") is False
    )


def test_self_enhancement_unknown_is_no_warning() -> None:
    # Conservative: unknown models don't trigger the warning.
    assert self_enhancement("anthropic/claude-sonnet-4-6", "novel-model") is False
