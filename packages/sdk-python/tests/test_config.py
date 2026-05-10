import pytest
from judge import init
from judge._config import get_config, reset_for_tests


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_for_tests()


def test_init_defaults() -> None:
    cfg = init()
    assert cfg.endpoint == "http://localhost:4318"
    assert cfg.api_key is None
    assert cfg.sample_rate == 1.0
    assert cfg.telemetry is False


def test_init_overrides() -> None:
    cfg = init(api_key="k", endpoint="http://x:1/", project="p", telemetry=True)
    assert cfg.api_key == "k"
    assert cfg.endpoint == "http://x:1/"
    assert cfg.project == "p"
    assert cfg.telemetry is True


def test_init_persists_globally() -> None:
    init(api_key="a")
    assert get_config().api_key == "a"


def test_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUDGE_API_KEY", "from-env")
    monkeypatch.setenv("JUDGE_ENDPOINT", "http://env:1")
    monkeypatch.setenv("JUDGE_PROJECT", "env-proj")
    cfg = init()
    assert cfg.api_key == "from-env"
    assert cfg.endpoint == "http://env:1"
    assert cfg.project == "env-proj"
