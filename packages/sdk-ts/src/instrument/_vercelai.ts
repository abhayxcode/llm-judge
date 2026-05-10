/** Wrap Vercel AI SDK's generateText / streamText / generateObject.
 *
 * Unlike OpenAI / Anthropic, the Vercel AI SDK exposes loose function
 * exports rather than client classes. We patch the namespace object
 * directly — the caller passes us the imported namespace, e.g.:
 *
 * ```ts
 * import * as ai from 'ai';
 * import { auto } from '@llm-judge/sdk/instrument';
 * auto.install({ vercelAi: ai });
 * ```
 */

import { type Unpatch, wrapMethod } from './_common.js';

// biome-ignore lint/suspicious/noExplicitAny: foreign namespace
export function instrumentVercelAI(ai: any): Unpatch | null {
  if (!ai) return null;
  const targets: Array<[string, string]> = [
    ['generateText', 'vercel.generateText'],
    ['streamText', 'vercel.streamText'],
    ['generateObject', 'vercel.generateObject'],
    ['streamObject', 'vercel.streamObject'],
  ];
  const unpatchers: Unpatch[] = [];
  for (const [fnName, spanName] of targets) {
    if (typeof ai[fnName] !== 'function') continue;
    unpatchers.push(
      wrapMethod(ai, fnName, {
        spanName,
        system: 'vercel-ai',
        extractModel: (args) => {
          const model = (args[0] as { model?: { modelId?: string } | string })?.model;
          if (!model) return '';
          if (typeof model === 'string') return model;
          return String(model.modelId ?? '');
        },
        extractMessages: (args) => {
          const opts = args[0] as { messages?: unknown; prompt?: unknown };
          return opts?.messages ?? opts?.prompt;
        },
        extractUsage: (r) => {
          const u = r?.usage ?? {};
          // Vercel AI SDK uses promptTokens/completionTokens as of v3+
          return {
            input_tokens: u.promptTokens ?? u.inputTokens ?? u.input_tokens,
            output_tokens: u.completionTokens ?? u.outputTokens ?? u.output_tokens,
          };
        },
      }),
    );
  }
  if (unpatchers.length === 0) return null;
  return () => {
    for (const u of unpatchers) u();
  };
}
