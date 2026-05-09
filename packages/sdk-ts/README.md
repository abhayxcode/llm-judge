# @llm-judge/sdk

LLM Judge SDK for TypeScript. **MIT licensed.**

```bash
pnpm add @llm-judge/sdk   # not yet published — pre-release
```

## Quickstart

```ts
import { init, trace, span } from '@llm-judge/sdk';

init({
  apiKey: '...',
  endpoint: 'http://localhost:4318', // default
  project: 'my-project',
});

const answer = trace('rag_chain', async (query: string) => {
  const s = span('retrieve', { query });
  s.log({ retrieved: ['doc-1', 'doc-2'] });
  s.end();

  // ... call your LLM ...
  return 'answer';
});

await answer('hi');
```

## M1 status

- `init({...})` — global config
- `trace(name, fn)` — wraps a function as a trace; supports sync + async
- `span(name, attrs?)` — child span with `.log({...})` and `.end()`
- One `fetch` per finished trace; failures swallowed

Coming soon: batched sender, redaction, auto-instrument, OTel exporter, edge runtime support.

## License

MIT. See [LICENSE](./LICENSE).
