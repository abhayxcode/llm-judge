"""Global SDK configuration."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field


@dataclass
class Config:
    """Runtime configuration. Set once via :func:`init`."""

    api_key: str | None = None
    endpoint: str = "http://localhost:4318"
    project: str | None = None
    sample_rate: float = 1.0
    telemetry: bool = False
    timeout_s: float = 5.0
    extra: dict[str, str] = field(default_factory=dict)


_lock = threading.RLock()
_config = Config()


def init(
    *,
    api_key: str | None = None,
    endpoint: str | None = None,
    project: str | None = None,
    sample_rate: float | None = None,
    telemetry: bool | None = None,
    timeout_s: float | None = None,
) -> Config:
    """Configure the SDK globally.

    Falls back to env vars when args are omitted:

    - ``JUDGE_API_KEY``
    - ``JUDGE_ENDPOINT``
    - ``JUDGE_PROJECT``
    """
    global _config
    with _lock:
        _config = Config(
            api_key=api_key if api_key is not None else os.getenv("JUDGE_API_KEY"),
            endpoint=endpoint or os.getenv("JUDGE_ENDPOINT") or _config.endpoint,
            project=project if project is not None else os.getenv("JUDGE_PROJECT"),
            sample_rate=sample_rate if sample_rate is not None else _config.sample_rate,
            telemetry=telemetry if telemetry is not None else _config.telemetry,
            timeout_s=timeout_s if timeout_s is not None else _config.timeout_s,
        )
    return _config


def get_config() -> Config:
    with _lock:
        return _config


def reset_for_tests() -> None:
    """Reset global state. Test-only helper."""
    global _config
    with _lock:
        _config = Config()
