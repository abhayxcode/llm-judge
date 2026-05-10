/**
 * Metric IR builder + register() helper for TS.
 * Mirrors `judge.metric` / `judge.register_metric` in the Python SDK.
 */

import { getConfig } from './config.js';

export type ScoringType = 'pointwise' | 'pairwise' | 'reference' | 'classification';

export interface Scale {
  min?: number;
  max?: number;
  labels?: string[];
}

export interface JudgeConfig {
  model?: string;
  fallback_model?: string | null;
  temperature?: number;
  max_tokens?: number;
  api_base?: string | null;
  timeout_s?: number;
}

export interface LengthControl {
  mode?: 'off' | 'matched_sample' | 'penalty';
  penalty_per_100_tokens?: number;
}

export interface MetricSpec {
  id: string;
  name: string;
  description?: string;
  scoring_type: ScoringType;
  prompt_template: string;
  scale?: Scale;
  judge_config?: JudgeConfig;
  length_control?: LengthControl;
}

export function metric(spec: MetricSpec): MetricSpec {
  // The `id` exists; the function is here so users can write
  //   const m = metric({ id: 'faithfulness', ... });
  // and stay symmetric with the Python decorator form.
  return spec;
}

export interface RegisteredMetric {
  id: string;
  metric_id: string;
  metric_slug: string;
  version: number;
  hash: string;
  ir: Record<string, unknown>;
  created_at: string;
}

export interface RegisterOptions {
  project?: string;
  apiEndpoint?: string;
  apiKey?: string | null;
  signal?: AbortSignal;
}

/**
 * POST the metric IR to the admin API. Returns the registered version
 * row (idempotent on content hash).
 */
export async function registerMetric(
  spec: MetricSpec,
  opts: RegisterOptions = {},
): Promise<RegisteredMetric> {
  const cfg = getConfig();
  const project = opts.project ?? cfg.project;
  if (!project) {
    throw new Error(
      'registerMetric requires a project; pass { project } or call init({ project }).',
    );
  }
  const base = (opts.apiEndpoint ?? cfg.apiEndpoint).replace(/\/$/, '');
  const apiKey = opts.apiKey ?? cfg.apiKey;
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (apiKey) headers.authorization = `Bearer ${apiKey}`;

  const resp = await fetch(`${base}/v1/metrics`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ project, ir: spec }),
    signal: opts.signal,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`registerMetric failed (${resp.status}): ${body}`);
  }
  return (await resp.json()) as RegisteredMetric;
}
