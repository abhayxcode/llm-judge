export interface Config {
  apiKey: string | null;
  endpoint: string;
  apiEndpoint: string;
  project: string | null;
  sampleRate: number;
  telemetry: boolean;
  timeoutMs: number;
}

export interface InitOptions {
  apiKey?: string | null;
  endpoint?: string;
  apiEndpoint?: string;
  project?: string | null;
  sampleRate?: number;
  telemetry?: boolean;
  timeoutMs?: number;
}

const DEFAULT_CONFIG: Config = {
  apiKey: null,
  endpoint: 'http://localhost:4318',
  apiEndpoint: 'http://localhost:4000',
  project: null,
  sampleRate: 1.0,
  telemetry: false,
  timeoutMs: 5_000,
};

let current: Config = { ...DEFAULT_CONFIG };

function envFallback(): Partial<Config> {
  const env = typeof process !== 'undefined' ? process.env : ({} as NodeJS.ProcessEnv);
  const nonEmpty = (v: string | undefined): string | undefined =>
    v !== undefined && v !== '' ? v : undefined;
  return {
    apiKey: nonEmpty(env.JUDGE_API_KEY) ?? null,
    endpoint: nonEmpty(env.JUDGE_ENDPOINT),
    apiEndpoint: nonEmpty(env.JUDGE_API_ENDPOINT),
    project: nonEmpty(env.JUDGE_PROJECT) ?? null,
  };
}

/**
 * Configure the SDK globally. Falls back to JUDGE_API_KEY / JUDGE_ENDPOINT /
 * JUDGE_PROJECT environment variables when arguments are omitted.
 */
export function init(opts: InitOptions = {}): Config {
  const env = envFallback();
  current = {
    apiKey: opts.apiKey ?? env.apiKey ?? current.apiKey,
    endpoint: opts.endpoint ?? env.endpoint ?? current.endpoint,
    apiEndpoint: opts.apiEndpoint ?? env.apiEndpoint ?? current.apiEndpoint,
    project: opts.project ?? env.project ?? current.project,
    sampleRate: opts.sampleRate ?? current.sampleRate,
    telemetry: opts.telemetry ?? current.telemetry,
    timeoutMs: opts.timeoutMs ?? current.timeoutMs,
  };
  return current;
}

export function getConfig(): Config {
  return current;
}

/** Test helper: reset to defaults. */
export function resetForTests(): void {
  current = { ...DEFAULT_CONFIG };
}
