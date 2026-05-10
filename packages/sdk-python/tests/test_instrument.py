"""Auto-instrument unit tests using a fake LLM client.

We don't import `openai` or `anthropic` here — instead we exercise the
shared `wrap_sync` helper against a stub class. This keeps the test
suite hermetic and verifies the span/attribute shape directly.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

import judge
from judge import instrument
from judge._config import reset_for_tests
from judge._trace import _current_span, _current_trace
from judge.instrument._common import wrap_sync


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _Response:
    model: str
    usage: _Usage


class _FakeChat:
    def create(self, *, model: str, messages: list[dict[str, str]], **_: Any) -> _Response:
        return _Response(model=model, usage=_Usage(prompt_tokens=10, completion_tokens=20))


def _openai_usage(r: _Response) -> dict[str, int]:
    return {"input_tokens": r.usage.prompt_tokens, "output_tokens": r.usage.completion_tokens}


def setup_function() -> None:
    reset_for_tests()


def teardown_function() -> None:
    instrument.auto.uninstall()
    reset_for_tests()


def test_wrap_sync_records_span_under_active_trace() -> None:
    @judge.trace(name="chat_chain")
    def go() -> _Response:
        client = _FakeChat()
        return client.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    unpatch = wrap_sync(
        _FakeChat,
        "create",
        span_name="openai.chat.completions",
        system="openai",
        extract_model=lambda kw: str(kw.get("model", "")),
        extract_messages=lambda kw: kw.get("messages"),
        extract_usage=_openai_usage,
    )
    captured: list[Any] = []

    def _capture(payload: dict[str, Any]) -> None:
        captured.append(payload)

    # Replace send_trace to avoid network IO.
    import judge._trace as t

    orig_send = t.send_trace
    t.send_trace = _capture  # type: ignore[assignment]
    try:
        resp = go()
        assert resp.model == "gpt-4o-mini"
    finally:
        t.send_trace = orig_send  # type: ignore[assignment]
        unpatch()

    assert len(captured) == 1
    spans = captured[0]["spans"]
    # Root span + 1 wrapped child.
    names = [s["name"] for s in spans]
    assert "chat_chain" in names
    assert "openai.chat.completions.gpt-4o-mini" in names

    child = next(s for s in spans if "openai" in s["name"])
    attrs = child["attributes"]
    assert attrs["gen_ai.system"] == "openai"
    assert attrs["gen_ai.request.model"] == "gpt-4o-mini"
    assert attrs["gen_ai.usage.input_tokens"] == 10
    assert attrs["gen_ai.usage.output_tokens"] == 20
    assert attrs["gen_ai.response.model"] == "gpt-4o-mini"
    assert "user" in attrs["gen_ai.request.messages"]


def test_unpatch_restores_original() -> None:
    original = _FakeChat.create
    unpatch = wrap_sync(
        _FakeChat,
        "create",
        span_name="x",
        system="x",
        extract_model=lambda _: "m",
        extract_messages=lambda _: None,
        extract_usage=_openai_usage,
    )
    assert _FakeChat.create is not original
    unpatch()
    assert _FakeChat.create is original


def test_wrap_propagates_exceptions_and_marks_span_error() -> None:
    class _BadChat:
        def create(self, **_: Any) -> _Response:
            raise RuntimeError("boom")

    captured: list[Any] = []
    import judge._trace as t

    orig_send = t.send_trace
    t.send_trace = lambda p: captured.append(p)  # type: ignore[assignment]
    unpatch = wrap_sync(
        _BadChat,
        "create",
        span_name="x",
        system="x",
        extract_model=lambda _: "m",
        extract_messages=lambda _: None,
        extract_usage=_openai_usage,
    )

    @judge.trace(name="root")
    def go() -> None:
        _BadChat().create()

    try:
        with contextlib.suppress(RuntimeError):
            go()
    finally:
        t.send_trace = orig_send  # type: ignore[assignment]
        unpatch()

    assert len(captured) == 1
    err_spans = [s for s in captured[0]["spans"] if s["status"] == "error"]
    assert err_spans
    assert any("RuntimeError" in (s["error"] or "") for s in err_spans)


def test_install_is_idempotent() -> None:
    # Neither openai nor anthropic are installed in the test env, so
    # both patchers return False and install() returns an empty list.
    # The important contract is that a second call doesn't blow up.
    instrument.auto.install()
    instrument.auto.install()  # must not raise
    instrument.auto.uninstall()


def test_install_returns_empty_when_no_libs_present(monkeypatch: Any) -> None:
    """If neither library is importable, install() returns []."""
    monkeypatch.setattr(instrument.auto, "install_openai", lambda: False)
    monkeypatch.setattr(instrument.auto, "install_anthropic", lambda: False)
    assert instrument.auto.install() == []


def test_active_context_is_clean_after_run() -> None:
    @judge.trace(name="root")
    def go() -> None:
        return None

    import judge._trace as t

    captured: list[Any] = []
    orig = t.send_trace
    t.send_trace = lambda p: captured.append(p)  # type: ignore[assignment]
    try:
        go()
    finally:
        t.send_trace = orig  # type: ignore[assignment]
    assert _current_trace.get() is None
    assert _current_span.get() is None
