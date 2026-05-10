import { afterEach, describe, expect, it, vi } from 'vitest';
import { resetForTests } from '../src/config.js';
import { wrapMethod } from '../src/instrument/_common.js';
import { auto } from '../src/instrument/index.js';
import { trace } from '../src/trace.js';

describe('wrapMethod', () => {
  afterEach(() => {
    auto.uninstall();
    resetForTests();
    vi.unstubAllGlobals();
  });

  it('wraps a method, records gen_ai attrs on the active trace', async () => {
    class FakeChat {
      async create({ model: _m, messages: _ms }: { model: string; messages: unknown }) {
        return { model: 'gpt-4o-mini', usage: { prompt_tokens: 10, completion_tokens: 20 } };
      }
    }
    const unpatch = wrapMethod(FakeChat.prototype, 'create', {
      spanName: 'openai.chat.completions',
      system: 'openai',
      extractModel: (args) => String((args[0] as { model?: string })?.model ?? ''),
      extractMessages: (args) => (args[0] as { messages?: unknown })?.messages,
      extractUsage: (r) => ({
        input_tokens: r?.usage?.prompt_tokens,
        output_tokens: r?.usage?.completion_tokens,
      }),
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const wrapped = trace('chain', async () => {
      const c = new FakeChat();
      return c.create({ model: 'gpt-4o-mini', messages: [{ role: 'user', content: 'hi' }] });
    });
    await wrapped();
    unpatch();

    // sendTrace was called once and the body has both spans.
    expect(fetchMock).toHaveBeenCalledOnce();
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = JSON.parse(init.body as string);
    const spans = body.spans as Array<{ name: string; attributes: Record<string, unknown> }>;
    const child = spans.find((s) => s.name.startsWith('openai.chat.completions'));
    expect(child).toBeDefined();
    expect(child?.attributes['gen_ai.system']).toBe('openai');
    expect(child?.attributes['gen_ai.request.model']).toBe('gpt-4o-mini');
    expect(child?.attributes['gen_ai.usage.input_tokens']).toBe(10);
    expect(child?.attributes['gen_ai.usage.output_tokens']).toBe(20);
  });

  it('unpatch restores original method', () => {
    class X {
      async create() {
        return null;
      }
    }
    const orig = X.prototype.create;
    const unpatch = wrapMethod(X.prototype, 'create', {
      spanName: 'x',
      system: 'x',
      extractModel: () => '',
      extractMessages: () => undefined,
      extractUsage: () => ({}),
    });
    expect(X.prototype.create).not.toBe(orig);
    unpatch();
    expect(X.prototype.create).toBe(orig);
  });

  it('propagates exceptions and marks span as error', async () => {
    class Bad {
      async create(): Promise<never> {
        throw new Error('boom');
      }
    }
    const unpatch = wrapMethod(Bad.prototype, 'create', {
      spanName: 'x',
      system: 'x',
      extractModel: () => 'm',
      extractMessages: () => undefined,
      extractUsage: () => ({}),
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const wrapped = trace('root', async () => {
      const b = new Bad();
      await b.create();
    });
    await expect(wrapped()).rejects.toThrow(/boom/);
    unpatch();

    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    const errSpan = body.spans.find(
      (s: { status: string; name: string }) => s.status === 'error' && s.name !== 'root',
    );
    expect(errSpan?.error).toMatch(/boom/);
  });
});

describe('auto.install', () => {
  afterEach(() => auto.uninstall());

  it('returns [] when no SDKs are passed', () => {
    expect(auto.install({})).toEqual([]);
  });

  it('is idempotent on a second call', () => {
    class FakeOpenAIChat {
      async create() {
        return {};
      }
    }
    const fakeOpenAI = { Chat: { Completions: FakeOpenAIChat } };
    expect(auto.install({ openai: fakeOpenAI })).toEqual(['openai']);
    expect(auto.install({ openai: fakeOpenAI })).toEqual([]);
  });
});
