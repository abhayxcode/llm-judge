import pytest
from judge_workers.jobs.ping import ping


@pytest.mark.asyncio
async def test_ping_default() -> None:
    result = await ping({})
    assert result["message"] == "pong"
    assert "time" in result


@pytest.mark.asyncio
async def test_ping_custom_message() -> None:
    result = await ping({}, message="hello")
    assert result["message"] == "hello"
