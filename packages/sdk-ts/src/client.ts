import { getConfig } from './config.js';
import type { TracePayload } from './trace.js';

/**
 * Send a trace payload to the ingest service.
 *
 * M1 skeleton: one fetch per finished trace, no batching, no retries.
 * Errors are swallowed so user code never breaks because the SDK can't
 * reach the ingest service.
 */
export async function sendTrace(payload: TracePayload): Promise<void> {
  const cfg = getConfig();
  const url = `${cfg.endpoint.replace(/\/$/, '')}/v1/traces`;

  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (cfg.apiKey) headers.authorization = `Bearer ${cfg.apiKey}`;
  if (cfg.project) headers['x-judge-project'] = cfg.project;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), cfg.timeoutMs);

  try {
    await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch {
    // Swallow — ingest unreachable must not break user code.
  } finally {
    clearTimeout(timer);
  }
}
