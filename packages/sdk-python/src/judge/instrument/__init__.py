"""Auto-instrument popular LLM client libraries.

    from judge.instrument import auto
    auto.install()  # patches openai, anthropic if importable

Each patch wraps the relevant create-completion method, opens a span
under the active trace, captures gen_ai.* attributes per OTel semconv,
runs the underlying call, records token usage + the (truncated) output,
and ends the span. Errors are re-raised with the span flagged.

Idempotent: a second `install()` call is a no-op. `uninstall()` restores
the originals so tests can run hermetically.
"""

from __future__ import annotations

from judge.instrument import auto

__all__ = ["auto"]
