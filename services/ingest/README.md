# judge-ingest

Go HTTP service that accepts traces from SDKs and OTel exporters, writes them to a Redis Stream, and (in workers) batches into ClickHouse.

## Endpoints (M1 skeleton — stubs)

| Method | Path                | Status                            |
| ------ | ------------------- | --------------------------------- |
| GET    | `/health`           | liveness probe                    |
| GET    | `/ready`            | readiness probe (stubbed)         |
| POST   | `/v1/traces`        | REST trace ingest (stubbed → 202) |
| POST   | `/v1/otlp/traces`   | OTLP/HTTP ingest (stubbed → 202)  |

Real Redis + ClickHouse wiring lands in subsequent commits.

## Run locally

```bash
cd services/ingest
go run ./cmd/ingest
```

Or via the workspace stack:

```bash
make dev    # brings up storage; ingest service entry added once persistence wired
```

## Test

```bash
go test ./...
```
