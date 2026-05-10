/**
 * Async context for the active trace + span stack.
 *
 * Prefers Node's `AsyncLocalStorage` when it's importable (Node ≥18,
 * Bun, or Cloudflare Workers with `nodejs_compat`). Falls back to a
 * single-slot global store on edge runtimes that lack it — fine for
 * one-trace-per-request handlers, which is the common case.
 */

export interface ContextStore<T> {
  run<R>(value: T, callback: () => R): R;
  get(): T | undefined;
}

class GlobalSlotStore<T> implements ContextStore<T> {
  private value: T | undefined;

  run<R>(value: T, callback: () => R): R {
    const prev = this.value;
    this.value = value;
    try {
      return callback();
    } finally {
      this.value = prev;
    }
  }

  get(): T | undefined {
    return this.value;
  }
}

// Resolved once at module load. Edge runtimes that lack
// 'node:async_hooks' fall through to the global-slot store.
// biome-ignore lint/suspicious/noExplicitAny: runtime feature detection
const _als: any = (() => {
  // biome-ignore lint/suspicious/noExplicitAny: runtime feature detection
  const g = globalThis as any;
  if (!g.process?.versions?.node) return null;
  try {
    // `new Function('...')` keeps esbuild/tsup from trying to resolve
    // 'node:async_hooks' on edge bundles where the module is absent.
    const req = new Function('m', 'return require(m)') as (m: string) => unknown;
    // biome-ignore lint/suspicious/noExplicitAny: dynamic module shape
    const ah = req('node:async_hooks') as any;
    return ah?.AsyncLocalStorage ?? null;
  } catch {
    return null;
  }
})();

export function createContextStore<T>(): ContextStore<T> {
  if (_als) {
    const als = new _als();
    return {
      run: (value, cb) => als.run(value, cb),
      get: () => als.getStore() as T | undefined,
    };
  }
  return new GlobalSlotStore<T>();
}
