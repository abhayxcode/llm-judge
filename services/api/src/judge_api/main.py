"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from judge_api import __version__
from judge_api.config import Settings, get_settings
from judge_api.routes import health

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    log.info("api.startup", version=__version__)
    yield
    log.info("api.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="LLM Judge API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(health.router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "judge_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.env == "local",
        log_level="info",
    )


if __name__ == "__main__":
    run()
