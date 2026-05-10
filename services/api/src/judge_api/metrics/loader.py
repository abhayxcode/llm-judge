"""YAML → MetricIR loader.

Schema (minimal, M2):

    id: faithfulness
    name: Faithfulness
    description: Are claims in the answer supported by the context?
    scoring_type: pointwise
    scale:
      min: 1
      max: 5
    prompt_template: |
      You are a strict grader. ...
      {{input}} {{output}} {{context}}
    judge_config:
      model: anthropic/claude-sonnet-4-6
      fallback_model: openai/gpt-4o-mini
      temperature: 0
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from judge_api.metrics.ir import MetricIR


class MetricLoadError(ValueError):
    pass


def load_yaml(source: str | Path) -> MetricIR:
    """Parse a YAML file (or string) into a MetricIR.

    `source` may be a Path-like (file is read) or a str containing YAML.
    """
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).exists()):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = source

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MetricLoadError(f"invalid yaml: {exc}") from exc

    if not isinstance(raw, dict):
        raise MetricLoadError("metric yaml must be a mapping at the top level")

    try:
        return MetricIR.model_validate(raw)
    except ValidationError as exc:
        raise MetricLoadError(f"invalid metric: {exc}") from exc
