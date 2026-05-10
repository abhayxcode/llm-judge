/**
 * Auto-instrument popular LLM client libraries (TS).
 *
 * ```ts
 * import { auto } from '@llm-judge/sdk/instrument';
 * auto.install({ openai, anthropic, vercelAi });
 * ```
 *
 * Unlike the Python side we cannot monkey-patch a globally-imported
 * module via `require`, since ESM bindings are immutable and the user
 * may import a fresh copy. Instead the user passes the SDK they want
 * patched and we mutate the prototype of its client classes. This also
 * keeps tree-shaking honest — bundlers only pull libs the caller named.
 */

import { instrumentAnthropic } from './_anthropic.js';
import type { Unpatch } from './_common.js';
import { instrumentOpenAI } from './_openai.js';
import { instrumentVercelAI } from './_vercelai.js';

export interface InstallOptions {
  // biome-ignore lint/suspicious/noExplicitAny: each lib's namespace is a foreign type
  openai?: any;
  // biome-ignore lint/suspicious/noExplicitAny: foreign type
  anthropic?: any;
  // biome-ignore lint/suspicious/noExplicitAny: foreign type — Vercel AI SDK's `generateText`/`streamText` exports
  vercelAi?: any;
}

const _unpatchers: Unpatch[] = [];

export function install(opts: InstallOptions): string[] {
  if (_unpatchers.length > 0) return [];
  const patched: string[] = [];
  if (opts.openai) {
    const u = instrumentOpenAI(opts.openai);
    if (u) {
      _unpatchers.push(u);
      patched.push('openai');
    }
  }
  if (opts.anthropic) {
    const u = instrumentAnthropic(opts.anthropic);
    if (u) {
      _unpatchers.push(u);
      patched.push('anthropic');
    }
  }
  if (opts.vercelAi) {
    const u = instrumentVercelAI(opts.vercelAi);
    if (u) {
      _unpatchers.push(u);
      patched.push('vercel-ai');
    }
  }
  return patched;
}

export function uninstall(): void {
  while (_unpatchers.length > 0) {
    const u = _unpatchers.pop();
    u?.();
  }
}

export const auto = { install, uninstall };
