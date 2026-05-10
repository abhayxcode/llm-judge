# judge-eval-bench

Internal package: ships the canonical built-in metric YAMLs (`metrics/`)
and golden datasets (`datasets/`) used to compute Bias Reports. The CI
Bias Report job (M5) reads this directory.

## Layout

- `metrics/<slug>.v<n>.yaml` — metric IR sources. Hashed + versioned by
  the API on register; same content → same `id@version`.
- `datasets/<slug>.v<n>.jsonl` — one JSON object per line, with `input`
  + optional `expected_output` + optional `context`.
- `suites/<slug>.yaml` — top-level configs for `judge run` that bind a
  metric file to a dataset file.

## Running a suite (M2)

Spin the stack (see root README §1–2), then:

```bash
export ANTHROPIC_API_KEY=sk-...    # or OPENAI_API_KEY for fallback path
uv run judge run --suite eval-bench/suites/faithfulness.yaml
```

What happens:

1. CLI POSTs the metric YAML to `/v1/metrics`. New content → new
   version; same content → idempotent (returns existing version).
2. CLI POSTs the dataset JSONL to `/v1/datasets`. Each upload creates
   an immutable version.
3. CLI POSTs `/v1/runs`; the API fans out one Redis-stream message per
   record onto `judge:evals`.
4. Workers drain the stream, render the prompt template per record,
   call the judge via litellm, normalize the score to 0–1, and write
   one row per record to ClickHouse `scores`. `runs.completed_count` is
   bumped atomically.
5. CLI tails `/v1/runs/{id}` until status flips to `done`, then prints
   mean score and total cost.

## Adding a metric

1. Drop a YAML at `metrics/<slug>.v<n>.yaml`. Use the schema in
   `services/api/src/judge_api/metrics/ir.py` (or copy
   `faithfulness.v1.yaml`).
2. End the prompt with the literal line `Score: <integer>` so the
   pointwise parser picks it up.
3. Add a unit test in `tests/test_metric_yaml.py` (the parametrized
   loader test will pick up the new file automatically).
