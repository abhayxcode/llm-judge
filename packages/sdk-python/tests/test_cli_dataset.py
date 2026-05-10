"""Tests for `judge dataset` CSV/JSONL handling and split.

Network calls are not exercised here — `import` is run with --dry-run so
no judge API is required.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from judge.cli import main


def _runner() -> CliRunner:
    return CliRunner()


def test_dataset_import_csv_dry_run(tmp_path: Path) -> None:
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text(
        "question,answer,expected_output,context\n"
        "what is 2+2,4,4,\"{\"\"hint\"\":\"\"math\"\"}\"\n"
        "capital of France,Paris,Paris,\n",
        encoding="utf-8",
    )
    r = _runner().invoke(
        main,
        [
            "dataset",
            "import",
            str(csv_path),
            "--project",
            "demo",
            "--slug",
            "qa",
            "--dry-run",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "parsed 2 rows" in r.output
    assert "csv" in r.output


def test_dataset_import_jsonl_dry_run(tmp_path: Path) -> None:
    p = tmp_path / "rows.jsonl"
    p.write_text(
        '{"question": "x", "expected_output": "y"}\n'
        '{"question": "a", "context": {"src": "wiki"}}\n',
        encoding="utf-8",
    )
    r = _runner().invoke(
        main,
        [
            "dataset",
            "import",
            str(p),
            "--project",
            "demo",
            "--slug",
            "qa",
            "--dry-run",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "parsed 2 rows" in r.output
    assert "jsonl" in r.output


def test_dataset_split_writes_three_files(tmp_path: Path) -> None:
    p = tmp_path / "all.jsonl"
    p.write_text(
        "\n".join(json.dumps({"i": i}) for i in range(10)) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "splits"
    r = _runner().invoke(
        main,
        [
            "dataset",
            "split",
            str(p),
            "--out-dir",
            str(out),
            "--train",
            "0.7",
            "--dev",
            "0.2",
            "--test",
            "0.1",
            "--seed",
            "0",
        ],
    )
    assert r.exit_code == 0, r.output
    train_lines = (out / "all.train.jsonl").read_text().strip().splitlines()
    dev_lines = (out / "all.dev.jsonl").read_text().strip().splitlines()
    test_lines = (out / "all.test.jsonl").read_text().strip().splitlines()
    assert len(train_lines) + len(dev_lines) + len(test_lines) == 10
    assert len(train_lines) == 7
    assert len(dev_lines) == 2
    assert len(test_lines) == 1


def test_dataset_split_rejects_bad_ratios(tmp_path: Path) -> None:
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\n')
    r = _runner().invoke(
        main,
        [
            "dataset",
            "split",
            str(p),
            "--out-dir",
            str(tmp_path / "out"),
            "--train",
            "0.5",
            "--dev",
            "0.3",
            "--test",
            "0.3",
        ],
    )
    assert r.exit_code != 0
    assert "must sum to 1.0" in r.output
