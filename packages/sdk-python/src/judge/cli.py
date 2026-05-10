"""`judge` command-line interface.

Subcommands:

    judge run --suite ./evals.yaml [--watch]              (M2)
    judge dataset import <file> --project P --slug S      (M4)
    judge dataset split  --records FILE --train 0.7 ...   (M4)

The suite YAML points at one metric definition and one dataset; the
command registers both with the API, kicks off a run, and (with --watch)
polls progress until the run finishes.
"""

from __future__ import annotations

import csv
import json
import os
import random
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


@main.group("dataset")
def dataset_grp() -> None:
    """Dataset utilities: import, split."""


@dataset_grp.command("import")
@click.argument(
    "src", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--project", required=True, help="Project slug")
@click.option("--slug", required=True, help="Dataset slug")
@click.option("--name", default=None, help="Display name (defaults to slug)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["auto", "csv", "jsonl"]),
    default="auto",
    help="Force file format. 'auto' picks by extension.",
)
@click.option(
    "--api-endpoint",
    default=None,
    help="Override admin API base URL (default: $JUDGE_API_ENDPOINT or http://localhost:4000).",
)
@click.option("--api-key", default=None, help="Override API key.")
@click.option(
    "--dry-run", is_flag=True, help="Parse only, don't POST. Prints first row."
)
def dataset_import(
    src: Path,
    project: str,
    slug: str,
    name: str | None,
    fmt: str,
    api_endpoint: str | None,
    api_key: str | None,
    dry_run: bool,
) -> None:
    """Upload a CSV / JSONL file as a new dataset version."""
    actual_fmt = _detect_format(src, fmt)
    records = _load_dataset_csv(src) if actual_fmt == "csv" else _load_dataset_jsonl(src)
    click.echo(f"  parsed {len(records)} rows from {src.name} ({actual_fmt})")
    if dry_run:
        click.echo(f"  first row: {json.dumps(records[0])[:300]}")
        return

    base = (api_endpoint or os.getenv("JUDGE_API_ENDPOINT") or "http://localhost:4000").rstrip(
        "/"
    )
    key = api_key or os.getenv("JUDGE_API_KEY")
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{base}/v1/datasets",
            json={
                "project": project,
                "slug": slug,
                "name": name or slug,
                "records": records,
            },
            headers=headers,
        )
        resp.raise_for_status()
        d = resp.json()
        click.echo(
            f"  uploaded dataset={d['dataset_slug']} v{d['version']}  "
            f"records={d['record_count']}"
        )


@dataset_grp.command("split")
@click.argument(
    "src", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--out-dir", required=True, type=click.Path(path_type=Path))
@click.option("--train", type=float, default=0.7)
@click.option("--dev", type=float, default=0.15)
@click.option("--test", type=float, default=0.15)
@click.option("--seed", type=int, default=42)
def dataset_split(
    src: Path, out_dir: Path, train: float, dev: float, test: float, seed: int
) -> None:
    """Split a JSONL dataset into train/dev/test files."""
    if abs(train + dev + test - 1.0) > 1e-6:
        raise click.ClickException(
            f"train+dev+test must sum to 1.0 (got {train + dev + test})"
        )
    rows = [json.loads(line) for line in src.read_text().splitlines() if line.strip()]
    rng = random.Random(seed)
    rng.shuffle(rows)
    n = len(rows)
    n_train = int(n * train)
    n_dev = int(n * dev)
    splits = {
        "train": rows[:n_train],
        "dev": rows[n_train : n_train + n_dev],
        "test": rows[n_train + n_dev :],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in splits.items():
        path = out_dir / f"{src.stem}.{name}.jsonl"
        path.write_text(
            "".join(json.dumps(r) + "\n" for r in part), encoding="utf-8"
        )
        click.echo(f"  wrote {path.name} ({len(part)} rows)")


def _detect_format(path: Path, fmt: str) -> str:
    if fmt != "auto":
        return fmt
    ext = path.suffix.lower()
    if ext == ".csv":
        return "csv"
    if ext in {".jsonl", ".ndjson", ".json"}:
        return "jsonl"
    raise click.ClickException(
        f"cannot infer format from extension {ext!r}; pass --format"
    )


def _load_dataset_csv(path: Path) -> list[dict[str, Any]]:
    """CSV → dataset records.

    Convention: columns named `expected_output` and `context` are pulled
    out into top-level fields; `context` is JSON-decoded if it looks like
    one. Everything else lands under `input` so prompt templates pick
    fields by name.
    """
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for line_num, row in enumerate(reader, 2):
            expected = row.pop("expected_output", None)
            context_raw = row.pop("context", None)
            context: dict[str, Any] | None = None
            if context_raw:
                try:
                    parsed = json.loads(context_raw)
                    context = parsed if isinstance(parsed, dict) else {"value": parsed}
                except json.JSONDecodeError:
                    context = {"text": context_raw}
            input_payload: dict[str, Any] = {
                k: v for k, v in row.items() if v != ""
            }
            if not input_payload:
                raise click.ClickException(f"{path}:{line_num}: empty input row")
            out.append(
                {
                    "input": input_payload,
                    "expected_output": expected,
                    "context": context,
                }
            )
    if not out:
        raise click.ClickException(f"empty dataset: {path}")
    return out


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
