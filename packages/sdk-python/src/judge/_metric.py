"""@metric decorator + register() helper.

Two ways to define a metric in code:

    @judge.metric(
        id="my_metric",
        name="My Metric",
        scoring_type="pointwise",
        scale={"min": 1, "max": 5},
        prompt_template="...",
    )
    def my_metric():
        pass

    judge.register_metric(my_metric)  # POSTs IR to admin API

Or build the IR by hand and register:

    ir = judge.metric_ir(id="m", scoring_type="pointwise", ...)
    judge.register_metric(ir)

The IR shape mirrors `services/api/src/judge_api/metrics/ir.py`. We do
not import the server module from the SDK (the SDK ships standalone) —
the dict is validated server-side on POST.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from judge._config import get_config


@dataclass
class MetricSpec:
    id: str
    name: str
    scoring_type: str
    prompt_template: str
    description: str = ""
    scale: dict[str, Any] = field(default_factory=dict)
    judge_config: dict[str, Any] = field(default_factory=dict)
    length_control: dict[str, Any] = field(default_factory=lambda: {"mode": "off"})

    def to_ir(self) -> dict[str, Any]:
        d = asdict(self)
        # Server expects nested objects, not flat dicts; pass through.
        return d


def metric(
    *,
    id: str,
    name: str,
    scoring_type: str,
    prompt_template: str,
    description: str = "",
    scale: dict[str, Any] | None = None,
    judge_config: dict[str, Any] | None = None,
    length_control: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], MetricSpec]:
    """Decorator that turns a function stub into a MetricSpec.

    The function body is intentionally ignored — the metric is *defined*
    by the decorator args; the stub exists for IDE discoverability.
    """

    def _wrap(_fn: Callable[..., Any]) -> MetricSpec:
        return MetricSpec(
            id=id,
            name=name,
            scoring_type=scoring_type,
            prompt_template=prompt_template,
            description=description,
            scale=scale or {},
            judge_config=judge_config or {},
            length_control=length_control or {"mode": "off"},
        )

    return _wrap


def metric_ir(**kwargs: Any) -> MetricSpec:
    """Imperative builder, equivalent to the decorator without the stub."""
    return MetricSpec(**kwargs)


def register_metric(spec: MetricSpec, *, project: str | None = None) -> dict[str, Any]:
    """POST the metric IR to the admin API. Returns the registered version."""
    cfg = get_config()
    proj = project or cfg.project
    if proj is None:
        raise RuntimeError(
            "register_metric requires a project; pass `project=` or call judge.init(project=...)"
        )
    url = f"{cfg.api_endpoint.rstrip('/')}/v1/metrics"
    headers = {"content-type": "application/json"}
    if cfg.api_key:
        headers["authorization"] = f"Bearer {cfg.api_key}"
    body = {"project": proj, "ir": spec.to_ir()}
    with httpx.Client(timeout=cfg.timeout_s) as client:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
