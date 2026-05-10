/**
 * Hello-world demo: send a trace using the TypeScript SDK.
 *
 * Run after `make dev` is up, ingest is bound to :4318:
 *
 *     pnpm --filter @llm-judge/sdk build
 *     node --experimental-strip-types packages/sdk-ts/examples/hello.ts
 *
 * Or with tsx:
 *     pnpm dlx tsx packages/sdk-ts/examples/hello.ts
 */

import { init, span, trace } from '../src/index.js';

init({
  apiKey: 'local-dev',
  endpoint: 'http://localhost:4318',
  project: 'demo',
});

const answer = trace('hello_world_ts', async (query: string) => {
  const s1 = span('retrieve', { query });
  s1.log({ retrieved: ['doc-1', 'doc-2'] });
  await new Promise((r) => setTimeout(r, 50));
  s1.end();

  const s2 = span('generate', { model: 'claude-sonnet-4-6' });
  await new Promise((r) => setTimeout(r, 100));
  s2.end();

  return `answer-to-${query}`;
});

answer('what is the capital of France?').then((out) => {
  console.log(`sdk(ts) -> ${out}`);
  console.log('trace pushed. visit http://localhost:3000/');
});
