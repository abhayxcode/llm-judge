"""Trace + span primitives.

M1 skeleton: in-memory accumulation, one POST per finished trace. The
public shape (``@trace`` decorator + ``span()`` context manager) is the
contract callers depend on; internals can grow underneath without
breaking that contract.
"""

from __future__ import annotations

import contextvars
import functools
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, ParamSpec, TypeVar

from judge._client import send_trace
from judge._ulid import new_ulid

P = ParamSpec("P")
R = TypeVar("R")

_current_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar(
    "judge_current_trace", default=None
)
_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "judge_current_span", default=None
)


@dataclass
class Span:
    """A unit of work within a trace."""

    span_id: str
    name: str
    parent_id: str | None = None
    start_ms: int = 0
    end_ms: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None

    def log(self, **kwargs: Any) -> None:
        """Attach key/value attributes to this span."""
        self.attributes.update(kwargs)

    def __enter__(self) -> Span:
        self.start_ms = _now_ms()
        self._token = _current_span.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.end_ms = _now_ms()
        if exc is not None:
            self.status = "error"
            self.error = f"{exc_type.__name__ if exc_type else 'Error'}: {exc}"
        _current_span.reset(self._token)


@dataclass
class Trace:
    """A trace = a tree of spans rooted at one operation."""

    trace_id: str
    name: str
    start_ms: int = 0
    end_ms: int | None = None
    spans: list[Span] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"

    def to_payload(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "status": self.status,
            "attributes": self.attributes,
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_id": s.parent_id,
                    "name": s.name,
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "status": s.status,
                    "error": s.error,
                    "attributes": s.attributes,
                }
                for s in self.spans
            ],
        }


def span(name: str, **attributes: Any) -> Span:
    """Open a child span under the current trace.

    If no trace is active, the span is still returned but it will not be
    flushed (caller is responsible for opening a trace via ``@trace`` or
    explicit construction).
    """
    parent = _current_span.get()
    s = Span(
        span_id=new_ulid(),
        name=name,
        parent_id=parent.span_id if parent else None,
        attributes=dict(attributes),
    )
    t = _current_trace.get()
    if t is not None:
        t.spans.append(s)
    return s


def trace(name: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator: wraps the function in a trace and flushes on exit."""

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        trace_name = name or fn.__qualname__

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            t = Trace(trace_id=new_ulid(), name=trace_name, start_ms=_now_ms())
            t_token = _current_trace.set(t)
            root = Span(span_id=new_ulid(), name=trace_name, start_ms=t.start_ms)
            t.spans.append(root)
            s_token = _current_span.set(root)
            try:
                result = fn(*args, **kwargs)
                root.end_ms = _now_ms()
                t.end_ms = root.end_ms
                t.status = "ok"
                return result
            except Exception as e:
                root.end_ms = _now_ms()
                root.status = "error"
                root.error = f"{type(e).__name__}: {e}"
                t.end_ms = root.end_ms
                t.status = "error"
                raise
            finally:
                _current_span.reset(s_token)
                _current_trace.reset(t_token)
                send_trace(t.to_payload())

        return wrapper

    return decorator


def _now_ms() -> int:
    return int(time.time() * 1000)
