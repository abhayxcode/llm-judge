# judge-api

FastAPI app/admin/read API. Reads PG (transactional metadata) and ClickHouse (traces, scores). Writes PG.

## Endpoints (M1 skeleton)

| Method | Path      | Status                                           |
| ------ | --------- | ------------------------------------------------ |
| GET    | `/health` | liveness probe                                   |
| GET    | `/ready`  | readiness probe (stubbed; will check PG/CH/Redis)|

## Run locally

```bash
cd services/api
uv sync
uv run judge-api
```

## Test

```bash
uv run pytest
```
