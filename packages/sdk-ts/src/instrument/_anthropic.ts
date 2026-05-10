/** Patch @anthropic-ai/sdk's messages.create. */

import { type Unpatch, wrapMethod } from './_common.js';

// biome-ignore lint/suspicious/noExplicitAny: foreign SDK shape
export function instrumentAnthropic(anthropic: any): Unpatch | null {
  // The SDK exposes `Messages` as a class (`anthropic.Messages`) and
  // also `client.messages` as a constructed instance. Patching the
  // prototype catches every instance.
  // biome-ignore lint/suspicious/noExplicitAny: foreign type
  const Messages = (anthropic?.Messages ?? anthropic?.resources?.messages?.Messages) as any;
  if (!Messages?.prototype) return null;

  return wrapMethod(Messages.prototype, 'create', {
    spanName: 'anthropic.messages',
    system: 'anthropic',
    extractModel: (args) => String((args[0] as { model?: string })?.model ?? ''),
    extractMessages: (args) => (args[0] as { messages?: unknown })?.messages,
    extractUsage: (r) => {
      const u = r?.usage ?? {};
      return { input_tokens: u.input_tokens, output_tokens: u.output_tokens };
    },
  });
}
