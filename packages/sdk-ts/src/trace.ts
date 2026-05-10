import { sendTrace } from './client.js';
import { type ContextStore, createContextStore } from './context.js';
import { newUlid } from './ulid.js';

export interface SpanPayload {
  span_id: string;
  parent_id: string | null;
  name: string;
  start_ms: number;
  end_ms: number | null;
  status: 'ok' | 'error';
  error: string | null;
  attributes: Record<string, unknown>;
}

export interface TracePayload {
  trace_id: string;
  name: string;
  start_ms: number;
  end_ms: number | null;
  status: 'ok' | 'error';
  attributes: Record<string, unknown>;
  spans: SpanPayload[];
}

interface Context {
  trace: TraceImpl;
  spanStack: SpanImpl[];
}

const als: ContextStore<Context> = createContextStore<Context>();
const nowMs = (): number => Date.now();

class SpanImpl {
  span_id: string;
  parent_id: string | null;
  name: string;
  start_ms: number;
  end_ms: number | null = null;
  status: 'ok' | 'error' = 'ok';
  error: string | null = null;
  attributes: Record<string, unknown>;

  constructor(name: string, parentId: string | null, attributes: Record<string, unknown>) {
    this.span_id = newUlid();
    this.parent_id = parentId;
    this.name = name;
    this.start_ms = nowMs();
    this.attributes = { ...attributes };
  }

  log(attrs: Record<string, unknown>): void {
    Object.assign(this.attributes, attrs);
  }

  end(): void {
    if (this.end_ms === null) this.end_ms = nowMs();
  }

  toPayload(): SpanPayload {
    return {
      span_id: this.span_id,
      parent_id: this.parent_id,
      name: this.name,
      start_ms: this.start_ms,
      end_ms: this.end_ms,
      status: this.status,
      error: this.error,
      attributes: this.attributes,
    };
  }
}

class TraceImpl {
  trace_id: string;
  name: string;
  start_ms: number;
  end_ms: number | null = null;
  status: 'ok' | 'error' = 'ok';
  attributes: Record<string, unknown> = {};
  spans: SpanImpl[] = [];

  constructor(name: string) {
    this.trace_id = newUlid();
    this.name = name;
    this.start_ms = nowMs();
  }

  toPayload(): TracePayload {
    return {
      trace_id: this.trace_id,
      name: this.name,
      start_ms: this.start_ms,
      end_ms: this.end_ms,
      status: this.status,
      attributes: this.attributes,
      spans: this.spans.map((s) => s.toPayload()),
    };
  }
}

export type Span = SpanImpl;
export type Trace = TraceImpl;

/** Open a child span under the current trace. */
export function span(name: string, attributes: Record<string, unknown> = {}): Span {
  const ctx = als.get();
  const parentId = ctx?.spanStack[ctx.spanStack.length - 1]?.span_id ?? null;
  const s = new SpanImpl(name, parentId, attributes);
  if (ctx) {
    ctx.trace.spans.push(s);
    ctx.spanStack.push(s);
    // Auto-pop on end()
    const origEnd = s.end.bind(s);
    s.end = () => {
      origEnd();
      const top = ctx.spanStack[ctx.spanStack.length - 1];
      if (top === s) ctx.spanStack.pop();
    };
  }
  return s;
}

type AnyFn<TArgs extends unknown[], TRet> = (...args: TArgs) => TRet;

/**
 * Wrap a function as a trace. Works for sync and async.
 *
 * @example
 *   const wrapped = trace('rag_chain', async (q: string) => {
 *     ...
 *     return 'answer';
 *   });
 */
export function trace<TArgs extends unknown[], TRet>(
  name: string,
  fn: AnyFn<TArgs, TRet>,
): AnyFn<TArgs, TRet> {
  return ((...args: TArgs): TRet => {
    const t = new TraceImpl(name);
    const root = new SpanImpl(name, null, {});
    t.spans.push(root);
    const ctx: Context = { trace: t, spanStack: [root] };

    return als.run(ctx, () => {
      try {
        const result = fn(...args);
        if (result instanceof Promise) {
          return result.then(
            (val) => {
              finalize(t, root, 'ok');
              return val;
            },
            (err: unknown) => {
              finalize(t, root, 'error', err);
              throw err;
            },
          ) as TRet;
        }
        finalize(t, root, 'ok');
        return result;
      } catch (err) {
        finalize(t, root, 'error', err);
        throw err;
      }
    });
  }) as AnyFn<TArgs, TRet>;
}

function finalize(t: TraceImpl, root: SpanImpl, status: 'ok' | 'error', err?: unknown): void {
  root.end();
  root.status = status;
  if (err) {
    const message = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
    root.error = message;
  }
  t.end_ms = root.end_ms;
  t.status = status;
  // Fire and forget — never await user-visible.
  void sendTrace(t.toPayload());
}
