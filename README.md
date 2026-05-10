# LLM Judge

Open-source LLM-as-a-Judge platform. Two product surfaces from one codebase: **offline experimentation** and **production observability**, plus calibrated, bias-corrected judges with measured human-agreement.

> Status: pre-release. Repo scaffolding in progress. Targeting public alpha at end of Phase 1 (~6 months from kickoff).

## Why

Most LLM evaluation tools wrap a frontier model in a prompt and call it a judge. Few publish human-agreement scores, position-bias deltas, or verbosity correlations for the metrics they ship. The wedge here is **judge quality as a first-class product feature** — every built-in metric ships with a Bias Report, and every user can calibrate judges against their own labeled data.

## Repo Layout

```
apps/
  web/                  # Next.js 15 + shadcn/ui + Tremor
  docs/                 # Docs site
services/
  ingest/               # Go: OTLP + REST trace ingest
  api/                  # Python FastAPI: app + admin + read API
  workers/              # Python Arq: eval runners + scheduled jobs
packages/
  sdk-python/           # MIT — published to PyPI
  sdk-ts/               # MIT — published to npm
  proto/                # Shared schemas (OTel + internal)
  ui/                   # Shared React components
deploy/
  docker-compose.yml    # Local + simple self-host
  helm/                 # k8s self-host
  terraform/            # Reference cloud deploys (P2)
eval-bench/             # Internal: golden datasets + Bias Report runners
```

## Reading

- `.docs/SPEC.md` — what to build
- `.docs/implementation-guide.md` — how and when
- `.docs/Architecture.md` — end-of-phase diagrams

## Quickstart

The stack runs locally via `docker-compose`. Below covers M1 (trace
hello-world) and M2 (faithfulness eval run) end-to-end.

### 0. Prerequisites

- Docker + docker-compose
- Python 3.12, [`uv`](https://docs.astral.sh/uv/)
- Node 20, [`pnpm`](https://pnpm.io/)
- One of: `ANTHROPIC_API_KEY` (preferred — Sonnet 4.6 is the default
  judge), or `OPENAI_API_KEY` (fallback path uses GPT-4o-mini). BYOM
  endpoints work via per-metric `judge_config.api_base`.

### 1. Bring up infrastructure

```bash
make bootstrap                    # uv + pnpm installs
docker compose -f deploy/docker-compose.yml up -d \
    postgres clickhouse minio redis
uv run judge-cli migrate-pg       # alembic up to 0002
uv run judge-cli migrate-ch       # ClickHouse DDL (spans, scores, ...)
uv run judge-cli bootstrap        # creates default org + 'demo' project,
                                  # prints API key once
```

Export the printed key as `JUDGE_API_KEY` if you want SDK auth (not yet
enforced in M1/M2 ingest path; required from M5 onward).

### 2. Start the services

In separate terminals (or `docker compose up ingest api workers web`):

```bash
# Go ingest on :4318
make dev-ingest

# Python API on :4000
uv run judge-api

# Workers (trace consumer + eval consumer)
uv run judge-workers

# Web on :3000
pnpm --filter @llm-judge/web dev
```

### 3. M1 — trace hello-world

```bash
uv run python packages/sdk-python/examples/hello.py
```

Trace lands in <5 s at `http://localhost:3000`. Click through to the
trace detail.

### 4. M2 — score a dataset (`faithfulness` v1)

```bash
export ANTHROPIC_API_KEY=sk-...
uv run judge run --suite eval-bench/suites/faithfulness.yaml
```

The CLI registers the metric IR, uploads the 20-record seed dataset,
kicks off a run, and tails progress until done. Scores appear at
`http://localhost:3000/runs`; per-record reasoning, cost, and latency
render on `/runs/{id}`.

To run against your own dataset, point the suite YAML at a JSONL where
each line has `input` + optional `expected_output` + optional `context`.

## License

- Server (apps, services, deploy, eval-bench): **AGPL-3.0-or-later**
- SDKs (`packages/sdk-python`, `packages/sdk-ts`): **MIT**
- Commercial license available on request — `abhayxcode@gmail.com`

See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Security disclosures: [SECURITY.md](./SECURITY.md).
