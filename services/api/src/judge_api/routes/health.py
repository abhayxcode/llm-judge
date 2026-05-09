from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from judge_api import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    time: str
    version: str
    env: str


class ReadyResponse(BaseModel):
    ready: bool


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        time=datetime.now(UTC).isoformat(),
        version=__version__,
        env=request.app.state.settings.env,
    )


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    # Stub: real readiness will check PG + CH + Redis connectivity.
    return ReadyResponse(ready=True)
