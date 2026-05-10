/**
 * Server-side fetcher for the LLM Judge admin API.
 *
 * Reads `NEXT_PUBLIC_API_URL` (or falls back to localhost:4000) so the
 * same code works in dev + Docker + cloud. All calls are uncached so the
 * traces list reflects new data without manual revalidation in M1.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:4000';

export interface TraceSummary {
  trace_id: string;
  org_id: string;
  project_id: string;
  name: string;
  first_seen: string;
  last_seen: string;
  duration_ms: number;
  span_count: number;
  root_span_count: number;
  status: string;
  error: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface SpanDetail {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  start_ts: string;
  end_ts: string | null;
  duration_ms: number;
  status: string;
  error: string | null;
  attributes: Record<string, string>;
  gen_ai_system: string;
  gen_ai_model: string;
  input_tokens: number;
  output_tokens: number;
}

export interface TraceDetail {
  summary: TraceSummary;
  spans: SpanDetail[];
}

export async function listTraces(project = 'demo', limit = 50): Promise<TraceSummary[]> {
  const url = new URL('/v1/traces', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('limit', String(limit));
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`api ${resp.status}`);
    return (await resp.json()) as TraceSummary[];
  } catch {
    return [];
  }
}

export async function getTrace(traceId: string, project = 'demo'): Promise<TraceDetail | null> {
  const url = new URL(`/v1/traces/${encodeURIComponent(traceId)}`, API_URL);
  url.searchParams.set('project', project);
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (resp.status === 404) return null;
    if (!resp.ok) throw new Error(`api ${resp.status}`);
    return (await resp.json()) as TraceDetail;
  } catch {
    return null;
  }
}

export const apiUrl = API_URL;
