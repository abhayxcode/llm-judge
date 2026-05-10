"""Sanity-check the built-in metric YAMLs against the API's MetricIR loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from judge_api.metrics import MetricIR, ScoringType, load_yaml

METRICS_DIR = Path(__file__).resolve().parents[1] / "metrics"


@pytest.mark.parametrize("path", sorted(METRICS_DIR.glob("*.yaml")))
def test_builtin_metric_yaml_parses(path: Path) -> None:
    ir = load_yaml(path)
    assert isinstance(ir, MetricIR)
    assert ir.id
    assert ir.prompt_template
    # Hash must be deterministic across calls.
    assert ir.content_hash() == ir.content_hash()


def test_faithfulness_v1_shape() -> None:
    ir = load_yaml(METRICS_DIR / "faithfulness.v1.yaml")
    assert ir.id == "faithfulness"
    assert ir.scoring_type == ScoringType.POINTWISE
    assert ir.scale.min == 1
    assert ir.scale.max == 5
    # CoT-before-score requires a literal 'Score:' instruction in the prompt.
    assert "Score:" in ir.prompt_template
