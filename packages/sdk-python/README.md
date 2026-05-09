# judge

LLM Judge SDK for Python. **MIT licensed.**

```bash
pip install judge   # not yet published — pre-release
```

## Quickstart

```python
import judge

judge.init(
    api_key="...",
    endpoint="http://localhost:4318",  # default
    project="my-project",
)

@judge.trace(name="rag_chain")
def answer(query: str) -> str:
    with judge.span("retrieve") as s:
        s.log(query=query, retrieved=["doc-1", "doc-2"])
    with judge.span("generate"):
        ...
    return "answer"
```

## M1 status

- `judge.init(...)` — global config
- `@judge.trace(name=...)` — wraps a function as a trace
- `judge.span(name, **attrs)` — child span context manager + `.log(**kv)` on the span
- Sends one synchronous POST per finished trace to the ingest service. Failures swallowed so user code is never broken.

Coming soon:

- Async / batched sender on a background thread
- Client-side redaction
- Auto-instrumentation for OpenAI, Anthropic, LangChain, LlamaIndex, LiteLLM
- OTel exporter

## License

MIT. See [LICENSE](./LICENSE).
