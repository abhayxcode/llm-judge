"""Metric IR + loaders.

The IR is the canonical, language-agnostic representation of a metric
definition. YAML files, Python decorators, and the (future) UI builder
all compile to this shape. Same content → same hash → same `id@version`.
"""

from __future__ import annotations

from judge_api.metrics.ir import (
    JudgeConfig,
    LengthControl,
    MetricIR,
    Scale,
    ScoringType,
    canonical_hash,
)
from judge_api.metrics.loader import load_yaml

__all__ = [
    "JudgeConfig",
    "LengthControl",
    "MetricIR",
    "Scale",
    "ScoringType",
    "canonical_hash",
    "load_yaml",
]
