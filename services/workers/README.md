# judge-workers

Arq workers for async eval runs, kappa recompute, active learning sampling, scheduled jobs.

## M1 status

Skeleton only — single `ping` smoke job. Real jobs land in M2+:

- `eval_record(metric_id@v, record_id, run_id)` — primary eval job
- `kappa_recompute(metric_id@v, project_id)` — incremental on label arrival
- `active_learning_sample(project_id)` — refresh queue
- `bias_report_run(metric_id@v)` — nightly + on metric change

## Run locally

```bash
cd services/workers
uv sync
uv run judge-workers
```

## Test

```bash
uv run pytest
```
