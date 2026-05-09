import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getConfig, init, resetForTests } from '../src/config.js';

describe('init / config', () => {
  beforeEach(() => {
    resetForTests();
    vi.stubEnv('JUDGE_API_KEY', '');
    vi.stubEnv('JUDGE_ENDPOINT', '');
    vi.stubEnv('JUDGE_PROJECT', '');
  });

  afterEach(() => {
    resetForTests();
    vi.unstubAllEnvs();
  });

  it('returns defaults when called with no args', () => {
    const cfg = init();
    expect(cfg.endpoint).toBe('http://localhost:4318');
    expect(cfg.apiKey).toBeNull();
    expect(cfg.sampleRate).toBe(1.0);
    expect(cfg.telemetry).toBe(false);
  });

  it('respects explicit overrides', () => {
    const cfg = init({
      apiKey: 'k',
      endpoint: 'http://x:1/',
      project: 'p',
      telemetry: true,
    });
    expect(cfg.apiKey).toBe('k');
    expect(cfg.endpoint).toBe('http://x:1/');
    expect(cfg.project).toBe('p');
    expect(cfg.telemetry).toBe(true);
  });

  it('persists globally', () => {
    init({ apiKey: 'a' });
    expect(getConfig().apiKey).toBe('a');
  });

  it('falls back to env vars when args omitted', () => {
    vi.stubEnv('JUDGE_API_KEY', 'from-env');
    vi.stubEnv('JUDGE_ENDPOINT', 'http://env:1');
    vi.stubEnv('JUDGE_PROJECT', 'env-proj');
    const cfg = init();
    expect(cfg.apiKey).toBe('from-env');
    expect(cfg.endpoint).toBe('http://env:1');
    expect(cfg.project).toBe('env-proj');
  });
});
