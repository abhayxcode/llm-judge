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

Coming soon. Right now the repo is a scaffold; nothing runs end-to-end yet.

## License

- Server (apps, services, deploy, eval-bench): **AGPL-3.0-or-later**
- SDKs (`packages/sdk-python`, `packages/sdk-ts`): **MIT**
- Commercial license available on request — `abhayxcode@gmail.com`

See [LICENSE](./LICENSE) and [NOTICE](./NOTICE).

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Security disclosures: [SECURITY.md](./SECURITY.md).
