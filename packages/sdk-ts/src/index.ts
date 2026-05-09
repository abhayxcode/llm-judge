/**
 * LLM Judge SDK for TypeScript.
 *
 * Public API:
 *
 * ```ts
 * import { init, trace, span } from '@llm-judge/sdk';
 *
 * init({ apiKey: '...', endpoint: 'http://localhost:4318', project: 'my-app' });
 *
 * const handler = trace('rag_chain', async (q: string) => {
 *   const s = span('retrieve', { query: q });
 *   s.log({ retrieved: ['doc-1'] });
 *   s.end();
 *   return 'answer';
 * });
 * ```
 *
 * M1 skeleton. Batched send, redaction, auto-instrument, OTel exporter
 * land in subsequent commits.
 */

export { init, getConfig, resetForTests } from './config.js';
export type { Config, InitOptions } from './config.js';
export { trace, span } from './trace.js';
export type { Span, Trace } from './trace.js';
export { VERSION } from './version.js';
