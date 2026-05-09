import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { init, resetForTests } from '../src/config.js';
import { span, trace } from '../src/trace.js';

interface CapturedRequest {
  url: string;
  body: unknown;
  headers: Record<string, string>;
}

function setupFetchMock(): { calls: CapturedRequest[]; restore: () => void } {
  const calls: CapturedRequest[] = [];
  const original = globalThis.fetch;
  const mock = vi.fn(async (input: RequestInfo | URL, opts?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    const body = opts?.body ? JSON.parse(String(opts.body)) : null;
    const headers = (opts?.headers ?? {}) as Record<string, string>;
    calls.push({ url, body, headers });
    return new Response(JSON.stringify({ accepted: true }), {
      status: 202,
      headers: { 'content-type': 'application/json' },
    });
  });
  globalThis.fetch = mock as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}

async function flush(): Promise<void> {
  // Let microtasks run so the fire-and-forget sendTrace lands.
  await new Promise((r) => setImmediate(r));
}

describe('trace + span', () => {
  let mock: ReturnType<typeof setupFetchMock>;

  beforeEach(() => {
    resetForTests();
    init({ apiKey: 'test-key', endpoint: 'http://ingest.local:4318', project: 'p' });
    mock = setupFetchMock();
  });

  afterEach(() => {
    mock.restore();
    resetForTests();
  });

  it('sends a payload for a wrapped sync function', async () => {
    const wrapped = trace('my_chain', (x: number) => {
      const s = span('step', { kind: 'compute' });
      s.log({ value: x * 2 });
      s.end();
      return x + 1;
    });
    expect(wrapped(3)).toBe(4);
    await flush();
    expect(mock.calls.length).toBe(1);
    const body = mock.calls[0]?.body as { name: string; status: string; spans: { name: string }[] };
    expect(body.name).toBe('my_chain');
    expect(body.status).toBe('ok');
    expect(body.spans.map((s) => s.name)).toEqual(expect.arrayContaining(['my_chain', 'step']));
  });

  it('records error status when wrapped function throws', async () => {
    const wrapped = trace('boom', () => {
      throw new Error('nope');
    });
    expect(() => wrapped()).toThrow('nope');
    await flush();
    const body = mock.calls[0]?.body as {
      status: string;
      spans: { error: string | null }[];
    };
    expect(body.status).toBe('error');
    expect(body.spans[0]?.error).toContain('nope');
  });

  it('handles async functions', async () => {
    const wrapped = trace('async_chain', async (x: number) => {
      const s = span('inner');
      s.end();
      return x * 10;
    });
    await expect(wrapped(4)).resolves.toBe(40);
    await flush();
    expect(mock.calls.length).toBe(1);
  });

  it('does not break user code if ingest fails', async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error('connect refused');
    }) as typeof fetch;
    const wrapped = trace('resilient', () => 42);
    expect(wrapped()).toBe(42);
  });

  it('span outside a trace still returns a span object', () => {
    const s = span('orphan');
    expect(s.name).toBe('orphan');
    expect(s.span_id).toMatch(/^[0-9A-Z]{26}$/);
  });
});
