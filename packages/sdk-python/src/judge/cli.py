"""`judge` command-line interface.

Subcommands (M2):

    judge run --suite ./evals.yaml [--watch]

The suite YAML points at one metric definition and one dataset; the
command registers both with the API, kicks off a run, and (with --watch)
polls progress until the run finishes.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import click
import httpx
import yaml

from judge import __version__


@click.group()
@click.version_option(version=__version__, prog_name="judge")
def main() -> None:
    """LLM Judge command-line interface."""


@main.command("run")
@click.option(
    "--suite",
    "suite_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the suite YAML.",
)
@click.option(
    "--api-endpoint",
    default=None,
    help="Override admin API base URL (default: $JUDGE_API_ENDPOINT or http://localhost:4000).",
)
@click.option(
    "--api-key",
    default=None,
    help="Override API key (default: $JUDGE_API_KEY).",
)
@click.option("--watch/--no-watch", default=True, help="Tail run progress until done.")
@click.option(
    "--poll-interval",
    type=float,
    default=2.0,
    help="Seconds between progress polls when --watch is set.",
)
def run_cmd(
    suite_path: Path,
    api_endpoint: str | None,
    api_key: str | None,
    watch: bool,
    poll_interval: float,
) -> None:
    """Execute an eval suite end-to-end."""
    suite = _load_suite(suite_path)
    base = (api_endpoint or os.getenv("JUDGE_API_ENDPOINT") or "http://localhost:4000").rstrip(
        "/"
    )
    key = api_key or os.getenv("JUDGE_API_KEY")
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"

    project = suite["project"]
    metric_path = (suite_path.parent / suite["metric"]).resolve()
    dataset_block = suite["dataset"]
    dataset_records_path = (suite_path.parent / dataset_block["records"]).resolve()
    run_name = suite.get("run_name") or f"{metric_path.stem} run"

    with httpx.Client(timeout=30.0) as client:
        click.echo(f"→ registering metric: {metric_path.name}")
        metric_ir = _load_metric_yaml(metric_path)
        m_resp = client.post(
            f"{base}/v1/metrics",
            json={"project": project, "ir": metric_ir},
            headers=headers,
        )
        m_resp.raise_for_status()
        m = m_resp.json()
        click.echo(f"  metric={m['metric_slug']} v{m['version']}  hash={m['hash'][:8]}")

        click.echo(f"→ uploading dataset: {dataset_records_path.name}")
        records = _load_dataset_jsonl(dataset_records_path)
        d_resp = client.post(
            f"{base}/v1/datasets",
            json={
                "project": project,
                "slug": dataset_block["slug"],
                "name": dataset_block.get("name", dataset_block["slug"]),
                "records": records,
            },
            headers=headers,
        )
        d_resp.raise_for_status()
        d = d_resp.json()
        click.echo(
            f"  dataset={d['dataset_slug']} v{d['version']}  records={d['record_count']}"
        )

        click.echo("→ creating run")
        r_resp = client.post(
            f"{base}/v1/runs",
            json={
                "project": project,
                "name": run_name,
                "metric_slug": m["metric_slug"],
                "metric_version": m["version"],
                "dataset_slug": d["dataset_slug"],
                "dataset_version": d["version"],
            },
            headers=headers,
        )
        r_resp.raise_for_status()
        run = r_resp.json()
        click.echo(f"  run_id={run['id']} status={run['status']}")

        if not watch:
            return

        click.echo("→ watching progress (ctrl-c to detach)…")
        while True:
            poll = client.get(f"{base}/v1/runs/{run['id']}", headers=headers)
            poll.raise_for_status()
            run = poll.json()
            click.echo(
                f"  status={run['status']} "
                f"completed={run['completed_count']}/{run['record_count']} "
                f"errors={run['error_count']}"
            )
            if run["status"] in {"done", "failed"}:
                break
            time.sleep(poll_interval)

        click.echo("→ scores")
        s_resp = client.get(f"{base}/v1/runs/{run['id']}/scores", headers=headers)
        s_resp.raise_for_status()
        scores = s_resp.json()
        if not scores:
            click.echo("  (no scores returned)")
            return
        avg = sum(s["score"] for s in scores) / len(scores)
        cost = sum(s["cost_usd"] for s in scores)
        click.echo(f"  n={len(scores)}  mean={avg:.3f}  total_cost=${cost:.4f}")


def _load_suite(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise click.ClickException(f"suite must be a mapping: {path}")
    for key in ("project", "metric", "dataset"):
        if key not in raw:
            raise click.ClickException(f"suite missing required key '{key}': {path}")
    if "records" not in raw["dataset"] or "slug" not in raw["dataset"]:
        raise click.ClickException("suite.dataset must include 'slug' and 'records'")
    return raw


def _load_metric_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise click.ClickException(f"metric YAML must be a mapping: {path}")
    return raw


def _load_dataset_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"{path}:{line_num}: invalid JSON ({exc})") from exc
        if not isinstance(obj, dict):
            raise click.ClickException(f"{path}:{line_num}: expected object")
        # Pull `expected_output` and `context` out of the row; everything
        # else stays under `input` so the metric prompt template can pick
        # what it needs.
        expected_output = obj.pop("expected_output", None)
        context = obj.pop("context", None)
        out.append({"input": obj, "expected_output": expected_output, "context": context})
    if not out:
        raise click.ClickException(f"empty dataset: {path}")
    return out


if __name__ == "__main__":
    main()
    sys.exit(0)
