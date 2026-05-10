/** Patch the OpenAI SDK's chat.completions.create + responses.create. */

import { type Unpatch, wrapMethod } from './_common.js';

// biome-ignore lint/suspicious/noExplicitAny: foreign SDK shape
export function instrumentOpenAI(openai: any): Unpatch | null {
  if (!openai) return null;
  const unpatchers: Unpatch[] = [];

  // OpenAI's TS SDK exposes resource classes a few ways depending on
  // version: as `Chat.Completions`, as `resources.chat.completions.
  // Completions`, or as bare exports. Try each.
  const Resources = {
    chatCompletions: openai?.Chat?.Completions ?? openai?.resources?.chat?.completions?.Completions,
    responses: openai?.Responses ?? openai?.resources?.responses?.Responses,
  };

  if (Resources.chatCompletions?.prototype) {
    unpatchers.push(
      wrapMethod(Resources.chatCompletions.prototype, 'create', {
        spanName: 'openai.chat.completions',
        system: 'openai',
        extractModel: (args) => String((args[0] as { model?: string })?.model ?? ''),
        extractMessages: (args) => (args[0] as { messages?: unknown })?.messages,
        extractUsage: (r) => {
          const u = r?.usage ?? {};
          return {
            input_tokens: u.prompt_tokens ?? u.input_tokens,
            output_tokens: u.completion_tokens ?? u.output_tokens,
          };
        },
      }),
    );
  }

  if (Resources.responses?.prototype) {
    unpatchers.push(
      wrapMethod(Resources.responses.prototype, 'create', {
        spanName: 'openai.responses',
        system: 'openai',
        extractModel: (args) => String((args[0] as { model?: string })?.model ?? ''),
        extractMessages: (args) => (args[0] as { input?: unknown })?.input,
        extractUsage: (r) => {
          const u = r?.usage ?? {};
          return { input_tokens: u.input_tokens, output_tokens: u.output_tokens };
        },
      }),
    );
  }

  if (unpatchers.length === 0) return null;
  return () => {
    for (const u of unpatchers) u();
  };
}
