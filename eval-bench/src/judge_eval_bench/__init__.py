"""Built-in metric + dataset registry."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
METRICS_DIR = ROOT / "metrics"
DATASETS_DIR = ROOT / "datasets"


def metric_path(slug_at_version: str) -> Path:
    """`faithfulness@v1` -> .../metrics/faithfulness.v1.yaml"""
    if "@" in slug_at_version:
        slug, ver = slug_at_version.split("@", 1)
        ver = ver.lstrip("v")
        return METRICS_DIR / f"{slug}.v{ver}.yaml"
    return METRICS_DIR / f"{slug_at_version}.yaml"


def dataset_path(slug_at_version: str) -> Path:
    """`faithfulness_seed@v1` -> .../datasets/faithfulness_seed.v1.jsonl"""
    if "@" in slug_at_version:
        slug, ver = slug_at_version.split("@", 1)
        ver = ver.lstrip("v")
        return DATASETS_DIR / f"{slug}.v{ver}.jsonl"
    return DATASETS_DIR / f"{slug_at_version}.jsonl"
