/** Shared wrap helpers for TS auto-instrument. */

import { span as judgeSpan } from '../trace.js';

export type Unpatch = () => void;

const MAX_ATTR_CHARS = 4_000;

export function truncate(s: string): string {
  if (s.length <= MAX_ATTR_CHARS) return s;
  return `${s.slice(0, MAX_ATTR_CHARS)}...[+${s.length - MAX_ATTR_CHARS} chars]`;
}

export interface SpanShape {
  spanName: string;
  system: string;
  // biome-ignore lint/suspicious/noExplicitAny: free-form kwargs
  extractModel: (args: any[]) => string;
  // biome-ignore lint/suspicious/noExplicitAny: free-form kwargs
  extractMessages: (args: any[]) => unknown;
  // biome-ignore lint/suspicious/noExplicitAny: foreign response shape
  extractUsage: (response: any) => { input_tokens?: number; output_tokens?: number };
}

/**
 * Wrap one method on `target` with a judge-span. Returns the un-patcher.
 *
 * Works on prototype methods (the OpenAI/Anthropic SDK pattern) and on
 * loose function exports (Vercel AI SDK).
 */
// biome-ignore lint/suspicious/noExplicitAny: target is a foreign object
export function wrapMethod(target: any, methodName: string, shape: SpanShape): Unpatch {
  const original = target[methodName];
  if (typeof original !== 'function') {
    return () => {};
  }

  // biome-ignore lint/suspicious/noExplicitAny: bound to instance
  async function wrappedAsync(this: any, ...args: any[]): Promise<unknown> {
    const model = shape.extractModel(args) || 'unknown';
    const s = judgeSpan(`${shape.spanName}.${model}`, { 'gen_ai.system': shape.system });
    s.log({
      'gen_ai.system': shape.system,
      'gen_ai.request.model': model,
      method: methodName,
    });
    const messages = shape.extractMessages(args);
    if (messages !== undefined) {
      try {
        s.log({ 'gen_ai.request.messages': truncate(JSON.stringify(messages)) });
      } catch {
        // serialization may fail on circular refs; ignore
      }
    }
    try {
      const result = await original.apply(this, args);
      try {
        const usage = shape.extractUsage(result) || {};
        if (typeof usage.input_tokens === 'number') {
          s.log({ 'gen_ai.usage.input_tokens': usage.input_tokens });
        }
        if (typeof usage.output_tokens === 'number') {
          s.log({ 'gen_ai.usage.output_tokens': usage.output_tokens });
        }
        const respModel = (result as { model?: string })?.model;
        if (respModel) s.log({ 'gen_ai.response.model': respModel });
      } catch {
        // never break user code on telemetry errors
      }
      s.end();
      return result;
    } catch (err) {
      s.end();
      s.status = 'error';
      s.error = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
      throw err;
    }
  }

  target[methodName] = wrappedAsync;
  return () => {
    target[methodName] = original;
  };
}
