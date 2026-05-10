"""LLM Judge SDK for Python.

Public API:

    import judge

    judge.init(api_key="...", endpoint="http://localhost:4318")

    @judge.trace(name="my_chain")
    def my_chain(query: str) -> str:
        with judge.span("retrieve") as s:
            s.log(retrieved=["doc-1"])
        return "answer"

This is the M1 skeleton. Batched sends, redaction, auto-instrument,
OTel exporter, async APIs all land in subsequent commits.
"""

from judge import instrument
from judge._config import Config, init
from judge._metric import MetricSpec, metric, metric_ir, register_metric
from judge._trace import Span, Trace, span, trace
from judge._version import __version__

__all__ = [
    "Config",
    "MetricSpec",
    "Span",
    "Trace",
    "__version__",
    "init",
    "instrument",
    "metric",
    "metric_ir",
    "register_metric",
    "span",
    "trace",
]
