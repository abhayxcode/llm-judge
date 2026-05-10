"""Hello-world demo: send a trace using the SDK.

Run after `make dev` is up, ingest is bound to :4318, and workers are
consuming the stream. Then:

    uv run --package judge python packages/sdk-python/examples/hello.py

Refresh http://localhost:3000 — the trace should appear within a few seconds.
"""

from __future__ import annotations

import time

import judge

judge.init(
    api_key="local-dev",
    endpoint="http://localhost:4318",
    project="demo",
)


@judge.trace(name="hello_world")
def answer(query: str) -> str:
    with judge.span("retrieve") as s:
        s.log(query=query, retrieved=["doc-1", "doc-2"])
        time.sleep(0.05)
    with judge.span("generate") as s:
        s.log(model="claude-sonnet-4-6", prompt_chars=len(query))
        time.sleep(0.1)
    return f"answer-to-{query}"


def main() -> None:
    out = answer("what is the capital of France?")
    print(f"sdk -> {out}")
    print("trace pushed. visit http://localhost:3000/")


if __name__ == "__main__":
    main()
