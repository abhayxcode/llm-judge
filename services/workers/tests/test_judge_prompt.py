"""Prompt rendering + score parsing — pure functions, no IO."""

from __future__ import annotations

import pytest
from judge_workers.judge.parser import (
    ScoreParseError,
    normalize_pointwise,
    parse_pointwise_response,
)
from judge_workers.judge.pricing import estimate_cost_usd
from judge_workers.judge.prompt import PromptRenderError, render_prompt


def test_render_prompt_basic() -> None:
    out = render_prompt("hello {{name}}", {"name": "world"})
    assert out == "hello world"


def test_render_prompt_whitespace() -> None:
    out = render_prompt("hi {{ name }}!", {"name": "x"})
    assert out == "hi x!"


def test_render_prompt_missing_var_raises() -> None:
    with pytest.raises(PromptRenderError):
        render_prompt("{{a}} {{b}}", {"a": "x"})


def test_parse_pointwise_simple() -> None:
    raw = "Reasoning here.\nScore: 4"
    parsed = parse_pointwise_response(raw)
    assert parsed.score_raw == 4.0
    assert parsed.reasoning == "Reasoning here."


def test_parse_pointwise_with_scale() -> None:
    raw = "Some reasoning\nFinal score: 3 / 5"
    parsed = parse_pointwise_response(raw)
    assert parsed.score_raw == 3.0


def test_parse_pointwise_fallback_to_last_number() -> None:
    raw = "I'd say it deserves 4 out of 5"
    parsed = parse_pointwise_response(raw)
    assert parsed.score_raw == 4.0


def test_parse_pointwise_empty_raises() -> None:
    with pytest.raises(ScoreParseError):
        parse_pointwise_response("")


def test_parse_pointwise_no_number_raises() -> None:
    with pytest.raises(ScoreParseError):
        parse_pointwise_response("no numbers here")


def test_normalize_to_unit_interval() -> None:
    assert normalize_pointwise(3, 1, 5) == 0.5
    assert normalize_pointwise(1, 1, 5) == 0.0
    assert normalize_pointwise(5, 1, 5) == 1.0
    assert normalize_pointwise(10, 1, 5) == 1.0  # clamp


def test_pricing_unknown_model_zero() -> None:
    assert estimate_cost_usd("byom/unknown", 1000, 1000) == 0.0


def test_pricing_known_model() -> None:
    cost = estimate_cost_usd("openai/gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.15 + 0.60)
