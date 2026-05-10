"""Hash-based content addressing of MetricIR + YAML loader."""

from __future__ import annotations

import pytest
from judge_api.metrics import MetricIR, ScoringType, load_yaml
from judge_api.metrics.loader import MetricLoadError


def _ir(prompt: str = "rate {{x}}") -> MetricIR:
    return MetricIR(
        id="faithfulness",
        name="Faithfulness",
        scoring_type=ScoringType.POINTWISE,
        prompt_template=prompt,
    )


def test_same_content_same_hash() -> None:
    a = _ir()
    b = _ir()
    assert a.content_hash() == b.content_hash()


def test_different_prompt_different_hash() -> None:
    assert _ir("a").content_hash() != _ir("b").content_hash()


def test_field_order_irrelevant() -> None:
    """Hash must be stable regardless of dict key insertion order."""
    a = MetricIR(
        id="m",
        name="M",
        scoring_type=ScoringType.POINTWISE,
        prompt_template="x",
        scale={"min": 1, "max": 5},  # type: ignore[arg-type]
        judge_config={"model": "anthropic/claude-sonnet-4-6", "temperature": 0.0},  # type: ignore[arg-type]
    )
    b = MetricIR(
        id="m",
        name="M",
        scoring_type=ScoringType.POINTWISE,
        prompt_template="x",
        judge_config={"temperature": 0.0, "model": "anthropic/claude-sonnet-4-6"},  # type: ignore[arg-type]
        scale={"max": 5, "min": 1},  # type: ignore[arg-type]
    )
    assert a.content_hash() == b.content_hash()


def test_load_yaml_string() -> None:
    text = """
id: faithfulness
name: Faithfulness
scoring_type: pointwise
scale:
  min: 1
  max: 5
prompt_template: |
  Rate {{ x }}
"""
    ir = load_yaml(text)
    assert ir.id == "faithfulness"
    assert ir.scoring_type == ScoringType.POINTWISE
    assert ir.scale.min == 1
    assert ir.scale.max == 5


def test_load_yaml_invalid() -> None:
    with pytest.raises(MetricLoadError):
        load_yaml("not: [a yaml mapping at top level: ya]: x")


def test_load_yaml_missing_field() -> None:
    with pytest.raises(MetricLoadError):
        load_yaml("id: x\nname: X\nscoring_type: pointwise\n")  # no prompt_template
