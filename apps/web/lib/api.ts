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

export interface TraceFilters {
  sinceMinutes?: number;
  nameContains?: string;
  model?: string;
  status?: 'ok' | 'error';
}

export async function listTraces(
  project = 'demo',
  limit = 50,
  filters: TraceFilters = {},
): Promise<TraceSummary[]> {
  const url = new URL('/v1/traces', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('limit', String(limit));
  if (filters.sinceMinutes) url.searchParams.set('since_minutes', String(filters.sinceMinutes));
  if (filters.nameContains) url.searchParams.set('name_contains', filters.nameContains);
  if (filters.model) url.searchParams.set('model', filters.model);
  if (filters.status) url.searchParams.set('status', filters.status);
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`api ${resp.status}`);
    return (await resp.json()) as TraceSummary[];
  } catch {
    return [];
  }
}

export interface ObservabilityStats {
  project: string;
  since_minutes: number;
  trace_count: number;
  error_count: number;
  p50_ms: number;
  p95_ms: number;
  input_tokens: number;
  output_tokens: number;
}

export interface TimeseriesPoint {
  ts: string;
  count: number;
  error_count: number;
  p50_ms: number;
  p95_ms: number;
}

export interface Timeseries {
  bucket: string;
  project: string;
  points: TimeseriesPoint[];
}

export interface ScoreBucket {
  metric_id: string;
  bucket: string;
  count: number;
}

export async function getStats(
  project = 'demo',
  sinceMinutes = 60,
): Promise<ObservabilityStats | null> {
  const url = new URL('/v1/observability/stats', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('since_minutes', String(sinceMinutes));
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return null;
    return (await resp.json()) as ObservabilityStats;
  } catch {
    return null;
  }
}

export async function getTimeseries(
  project = 'demo',
  bucket: '1m' | '5m' | '1h' = '1m',
  sinceMinutes = 60,
): Promise<Timeseries | null> {
  const url = new URL('/v1/observability/timeseries', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('bucket', bucket);
  url.searchParams.set('since_minutes', String(sinceMinutes));
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return null;
    return (await resp.json()) as Timeseries;
  } catch {
    return null;
  }
}

export async function getScoreDistribution(
  project = 'demo',
  sinceMinutes = 60 * 24,
): Promise<ScoreBucket[]> {
  const url = new URL('/v1/observability/score_distribution', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('since_minutes', String(sinceMinutes));
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return [];
    return (await resp.json()) as ScoreBucket[];
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

export interface RunSummary {
  id: string;
  project_id: string;
  name: string;
  status: string;
  metric_version_id: string;
  dataset_version_id: string;
  record_count: number;
  completed_count: number;
  error_count: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ScoreRow {
  trace_id: string;
  span_id: string | null;
  score: number;
  score_raw: string;
  reasoning: string | null;
  label: string | null;
  judge_model: string;
  judge_provider: string;
  cost_usd: number;
  latency_ms: number;
  computed_at: string;
}

export async function listRuns(project = 'demo', limit = 50): Promise<RunSummary[]> {
  const url = new URL('/v1/runs', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('limit', String(limit));
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`api ${resp.status}`);
    return (await resp.json()) as RunSummary[];
  } catch {
    return [];
  }
}

export async function getRun(runId: string): Promise<RunSummary | null> {
  const url = new URL(`/v1/runs/${encodeURIComponent(runId)}`, API_URL);
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (resp.status === 404) return null;
    if (!resp.ok) throw new Error(`api ${resp.status}`);
    return (await resp.json()) as RunSummary;
  } catch {
    return null;
  }
}

export async function getRunScores(runId: string): Promise<ScoreRow[]> {
  const url = new URL(`/v1/runs/${encodeURIComponent(runId)}/scores`, API_URL);
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`api ${resp.status}`);
    return (await resp.json()) as ScoreRow[];
  } catch {
    return [];
  }
}

export interface MetricSummary {
  id: string;
  slug: string;
  name: string;
  scoring_type: string;
  latest_version: number | null;
  latest_hash: string | null;
}

export interface DatasetRecord {
  id: string;
  row_index: number;
  input: Record<string, unknown>;
  expected_output: string | null;
  context: Record<string, unknown> | null;
}

export interface AgreementSnapshot {
  project_id: string;
  metric_id: string;
  metric_slug: string;
  metric_version_id: string;
  metric_version: number;
  n_labels: number;
  cohen_kappa: number | null;
  fleiss_kappa: number | null;
  pearson_r: number | null;
  spearman_r: number | null;
  computed_at: string;
}

export interface QueueItem {
  id: string;
  project_id: string;
  metric_id: string;
  record_id: string;
  strategy: string;
  priority: number;
  reason: string | null;
  claimed_by: string | null;
  claimed_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface HumanLabel {
  id: string;
  project_id: string;
  metric_id: string;
  metric_version_id: string;
  record_id: string;
  user_id: string;
  user_email: string;
  score: number;
  label: string | null;
  rationale: string | null;
  tags: string[];
  created_at: string;
}

export async function listMetrics(project = 'demo'): Promise<MetricSummary[]> {
  const url = new URL('/v1/metrics', API_URL);
  url.searchParams.set('project', project);
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return [];
    return (await resp.json()) as MetricSummary[];
  } catch {
    return [];
  }
}

export async function getAgreement(
  project: string,
  metric: string,
): Promise<AgreementSnapshot | null> {
  const url = new URL('/v1/agreement', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('metric', metric);
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return null;
    const body = await resp.json();
    return body as AgreementSnapshot | null;
  } catch {
    return null;
  }
}

export async function listQueue(project: string, metric: string, limit = 50): Promise<QueueItem[]> {
  const url = new URL('/v1/queue', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('metric', metric);
  url.searchParams.set('limit', String(limit));
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return [];
    return (await resp.json()) as QueueItem[];
  } catch {
    return [];
  }
}

export async function getDatasetRecord(recordId: string): Promise<DatasetRecord | null> {
  const url = new URL(`/v1/datasets/records/${encodeURIComponent(recordId)}`, API_URL);
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return null;
    return (await resp.json()) as DatasetRecord;
  } catch {
    return null;
  }
}

export async function listLabels(
  project: string,
  metric: string,
  limit = 200,
): Promise<HumanLabel[]> {
  const url = new URL('/v1/labels', API_URL);
  url.searchParams.set('project', project);
  url.searchParams.set('metric', metric);
  url.searchParams.set('limit', String(limit));
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) return [];
    return (await resp.json()) as HumanLabel[];
  } catch {
    return [];
  }
}

export const apiUrl = API_URL;
