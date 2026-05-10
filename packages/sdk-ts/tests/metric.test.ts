import { afterEach, describe, expect, it, vi } from 'vitest';
import { init, resetForTests } from '../src/config.js';
import { metric, registerMetric } from '../src/metric.js';

describe('metric()', () => {
  it('round-trips the spec', () => {
    const spec = metric({
      id: 'faithfulness',
      name: 'Faithfulness',
      scoring_type: 'pointwise',
      prompt_template: 'rate {{x}}\nScore: <int>',
      scale: { min: 1, max: 5 },
    });
    expect(spec.id).toBe('faithfulness');
    expect(spec.scoring_type).toBe('pointwise');
  });
});

describe('registerMetric()', () => {
  afterEach(() => {
    resetForTests();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('POSTs to /v1/metrics with project + ir', async () => {
    init({ project: 'demo', apiEndpoint: 'http://api.test' });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'mv1',
          metric_id: 'm1',
          metric_slug: 'faithfulness',
          version: 1,
          hash: 'abcd',
          ir: {},
          created_at: '2026-05-10T00:00:00Z',
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const out = await registerMetric({
      id: 'faithfulness',
      name: 'Faithfulness',
      scoring_type: 'pointwise',
      prompt_template: 'x',
    });
    expect(out.version).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/v1/metrics',
      expect.objectContaining({ method: 'POST' }),
    );
    const reqInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = JSON.parse(reqInit.body as string);
    expect(body.project).toBe('demo');
    expect(body.ir.id).toBe('faithfulness');
  });

  it('throws when project is missing', async () => {
    init({ project: null });
    await expect(
      registerMetric({
        id: 'x',
        name: 'X',
        scoring_type: 'pointwise',
        prompt_template: 'p',
      }),
    ).rejects.toThrow(/project/);
  });

  it('throws when API returns non-2xx', async () => {
    init({ project: 'demo' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })));
    await expect(
      registerMetric({
        id: 'x',
        name: 'X',
        scoring_type: 'pointwise',
        prompt_template: 'p',
      }),
    ).rejects.toThrow(/registerMetric failed/);
  });
});
