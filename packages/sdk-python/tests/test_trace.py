from typing import Any

import httpx
import judge
import pytest
import respx
from judge._config import reset_for_tests


@pytest.fixture(autouse=True)
def _setup() -> None:
    reset_for_tests()
    judge.init(api_key="test-key", endpoint="http://ingest.local:4318", project="proj-x")


@respx.mock
def test_trace_decorator_sends_payload() -> None:
    route = respx.post("http://ingest.local:4318/v1/traces").respond(202, json={"accepted": True})

    @judge.trace(name="my_chain")
    def f(x: int) -> int:
        with judge.span("step", kind="compute") as s:
            s.log(value=x * 2)
        return x + 1

    assert f(3) == 4
    assert route.called
    import json

    body: dict[str, Any] = json.loads(route.calls.last.request.content)
    assert body["name"] == "my_chain"
    assert body["status"] == "ok"
    span_names = [s["name"] for s in body["spans"]]
    assert "my_chain" in span_names
    assert "step" in span_names


@respx.mock
def test_trace_records_exception() -> None:
    route = respx.post("http://ingest.local:4318/v1/traces").respond(202, json={"ok": True})

    @judge.trace(name="boom")
    def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        boom()
    assert route.called
    import json

    body = json.loads(route.calls.last.request.content)
    assert body["status"] == "error"
    assert any("ValueError: nope" in (s.get("error") or "") for s in body["spans"])


@respx.mock
def test_trace_swallows_ingest_failure() -> None:
    respx.post("http://ingest.local:4318/v1/traces").mock(
        side_effect=httpx.ConnectError("boom")
    )

    @judge.trace(name="resilient")
    def f() -> int:
        return 42

    # Failure to reach ingest must NOT break user code.
    assert f() == 42


def test_span_outside_trace_returns_span_without_flush() -> None:
    s = judge.span("orphan")
    assert s.name == "orphan"
    assert s.span_id  # still has an id
