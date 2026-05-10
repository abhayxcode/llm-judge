"""Metric IR — the internal, content-addressed representation of a metric.

Design notes:
- IR is JSON-serializable; same definition → same canonical JSON → same sha256.
- `MetricIR.hash` is computed deterministically over the *content* fields
  (id, scoring_type, scale, prompt_template, judge_config, length_control).
  `version` is *not* part of the hash — it is assigned by the server when a
  new content hash is observed for a given metric.
- Pointwise + reference modes ship in M2. Pairwise + length-control land
  in M3 (fields are present here so persisted IR can roll forward.)
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScoringType(StrEnum):
    POINTWISE = "pointwise"
    PAIRWISE = "pairwise"
    REFERENCE = "reference"
    CLASSIFICATION = "classification"


class Scale(BaseModel):
    """Numeric range or classification labels.

    For pointwise/reference: `min` + `max` define the integer scale that
    the judge prompt asks for; we normalize to 0.0-1.0 internally.
    For classification: `labels` enumerates allowed labels.
    """

    model_config = ConfigDict(extra="forbid")

    min: float | None = None
    max: float | None = None
    labels: list[str] | None = None


class JudgeConfig(BaseModel):
    """How to invoke the judge model.

    `model` follows litellm's provider/model naming (e.g.
    `anthropic/claude-sonnet-4-6`, `openai/gpt-4o-mini`,
    `openai/<model>` with a custom `api_base` for BYOM).
    """

    model_config = ConfigDict(extra="forbid")

    model: str = "anthropic/claude-sonnet-4-6"
    fallback_model: str | None = "openai/gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 1024
    api_base: str | None = None  # BYOM OpenAI-compatible endpoint
    timeout_s: float = 60.0


class LengthControl(BaseModel):
    """Length-bias mitigation knob. Only `off` is honored in M2; the rest
    are wired in M3."""

    model_config = ConfigDict(extra="forbid")

    mode: str = "off"  # off | matched_sample | penalty
    penalty_per_100_tokens: float = 0.0


class MetricIR(BaseModel):
    """Canonical metric definition. Hashable; hash drives versioning."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Slug, e.g. 'faithfulness'")
    name: str = Field(..., description="Human-readable name")
    description: str = ""
    scoring_type: ScoringType
    scale: Scale = Field(default_factory=Scale)
    prompt_template: str = Field(..., description="Judge prompt; placeholders use {{var}}")
    judge_config: JudgeConfig = Field(default_factory=JudgeConfig)
    length_control: LengthControl = Field(default_factory=LengthControl)

    def canonical_dict(self) -> dict[str, Any]:
        """Subset of fields that participate in the content hash."""
        return {
            "id": self.id,
            "scoring_type": self.scoring_type.value,
            "scale": self.scale.model_dump(),
            "prompt_template": self.prompt_template,
            "judge_config": self.judge_config.model_dump(),
            "length_control": self.length_control.model_dump(),
        }

    def content_hash(self) -> str:
        return canonical_hash(self.canonical_dict())


def canonical_hash(payload: dict[str, Any]) -> str:
    """sha256 hex of canonical JSON (sorted keys, no whitespace).

    Independent of input dict ordering, so two semantically identical
    metric defs always hash the same.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
