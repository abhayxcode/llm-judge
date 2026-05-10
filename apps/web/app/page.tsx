import { type TraceFilters, apiUrl, listTraces } from '@/lib/api';
import Link from 'next/link';

export const dynamic = 'force-dynamic';

function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace('T', ' ').replace('Z', '');
}

const SINCE_PRESETS: Record<string, number> = {
  '15m': 15,
  '1h': 60,
  '6h': 360,
  '24h': 1440,
};

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{
    project?: string;
    since?: string;
    name?: string;
    model?: string;
    status?: string;
    refresh?: string;
  }>;
}) {
  const params = await searchParams;
  const project = params.project ?? 'demo';
  const sinceKey = params.since && SINCE_PRESETS[params.since] ? params.since : '24h';
  const filters: TraceFilters = {
    sinceMinutes: SINCE_PRESETS[sinceKey],
    nameContains: params.name || undefined,
    model: params.model || undefined,
    status: params.status === 'ok' || params.status === 'error' ? params.status : undefined,
  };
  const refresh = params.refresh === '1';
  const traces = await listTraces(project, 50, filters);

  return (
    <main
      style={{
        padding: '2rem',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        maxWidth: 1100,
        margin: '0 auto',
      }}
    >
      {refresh ? <meta httpEquiv="refresh" content="5" /> : null}
      <header
        style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '1rem' }}
      >
        <h1 style={{ fontSize: '1.5rem', margin: 0 }}>LLM Judge</h1>
        <span style={{ color: '#888' }}>
          project: <code>{project}</code>
        </span>
        <Link
          href={{ pathname: '/observability', query: { project } }}
          style={{ color: '#0070f3' }}
        >
          observability →
        </Link>
        <Link href={{ pathname: '/runs', query: { project } }} style={{ color: '#0070f3' }}>
          runs →
        </Link>
        <Link href={{ pathname: '/labels', query: { project } }} style={{ color: '#0070f3' }}>
          labels →
        </Link>
        <span style={{ marginLeft: 'auto', color: '#888', fontSize: '0.875rem' }}>
          api: <code>{apiUrl}</code>
        </span>
      </header>

      <FilterBar
        project={project}
        sinceKey={sinceKey}
        name={params.name ?? ''}
        model={params.model ?? ''}
        status={params.status ?? ''}
        refresh={refresh}
      />

      {traces.length === 0 ? (
        <Empty />
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.95rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid #ddd' }}>
              <Th>Trace</Th>
              <Th>Name</Th>
              <Th>Started</Th>
              <Th>Duration</Th>
              <Th>Spans</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {traces.map((t) => (
              <tr key={t.trace_id} style={{ borderBottom: '1px solid #eee' }}>
                <Td>
                  <Link
                    href={{ pathname: `/traces/${t.trace_id}`, query: { project } }}
                    style={{ fontFamily: 'ui-monospace, monospace', color: '#0070f3' }}
                  >
                    {t.trace_id.slice(0, 12)}…
                  </Link>
                </Td>
                <Td>{t.name}</Td>
                <Td style={{ color: '#666' }}>{fmtTime(t.last_seen)}</Td>
                <Td>{fmtMs(t.duration_ms)}</Td>
                <Td>{t.span_count}</Td>
                <Td>
                  <StatusPill status={t.status} />
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

function FilterBar({
  project,
  sinceKey,
  name,
  model,
  status,
  refresh,
}: {
  project: string;
  sinceKey: string;
  name: string;
  model: string;
  status: string;
  refresh: boolean;
}) {
  return (
    <form
      method="GET"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        flexWrap: 'wrap',
        marginBottom: '1.25rem',
        padding: '0.75rem',
        background: '#fafafa',
        border: '1px solid #eee',
        borderRadius: 8,
        fontSize: '0.85rem',
      }}
    >
      <input type="hidden" name="project" value={project} />
      <span style={{ color: '#888' }}>since:</span>
      {Object.keys(SINCE_PRESETS).map((k) => (
        <label key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
          <input
            type="radio"
            name="since"
            value={k}
            defaultChecked={k === sinceKey}
            style={{ margin: 0 }}
          />
          {k}
        </label>
      ))}
      <input
        name="name"
        defaultValue={name}
        placeholder="name contains…"
        style={{ padding: '0.25rem 0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
      />
      <input
        name="model"
        defaultValue={model}
        placeholder="model"
        style={{ padding: '0.25rem 0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
      />
      <select
        name="status"
        defaultValue={status}
        style={{ padding: '0.25rem 0.5rem', border: '1px solid #ddd', borderRadius: 4 }}
      >
        <option value="">any status</option>
        <option value="ok">ok</option>
        <option value="error">error</option>
      </select>
      <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
        <input
          type="checkbox"
          name="refresh"
          value="1"
          defaultChecked={refresh}
          style={{ margin: 0 }}
        />
        live (5s)
      </label>
      <button
        type="submit"
        style={{
          padding: '0.3rem 0.8rem',
          background: '#0070f3',
          color: 'white',
          border: 0,
          borderRadius: 4,
          cursor: 'pointer',
        }}
      >
        Apply
      </button>
    </form>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th style={{ padding: '0.6rem 0.5rem', fontWeight: 600, color: '#444' }}>{children}</th>;
}

function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <td style={{ padding: '0.6rem 0.5rem', ...style }}>{children}</td>;
}

function StatusPill({ status }: { status: string }) {
  const ok = status === 'ok';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.15rem 0.5rem',
        borderRadius: 999,
        fontSize: '0.8rem',
        background: ok ? '#e6f7ec' : '#fdecea',
        color: ok ? '#1f7a3a' : '#a13a2a',
      }}
    >
      {status}
    </span>
  );
}

function Empty() {
  return (
    <div
      style={{
        padding: '2rem',
        border: '1px dashed #ccc',
        borderRadius: 8,
        color: '#666',
      }}
    >
      <p style={{ marginTop: 0 }}>
        <strong>No traces yet.</strong>
      </p>
      <p>
        Send one with the SDK: <code>judge.init(...)</code> + <code>@judge.trace</code>, point at{' '}
        <code>http://localhost:4318</code>.
      </p>
      <p style={{ marginBottom: 0, fontSize: '0.9rem' }}>
        Or POST a trace directly to <code>{'<api>/v1/traces'}</code>:
      </p>
      <pre
        style={{
          background: '#f6f6f6',
          padding: '0.75rem',
          borderRadius: 6,
          overflowX: 'auto',
          marginTop: '0.75rem',
          fontSize: '0.85rem',
        }}
      >
        {`curl -X POST http://localhost:4318/v1/traces \\
  -H 'content-type: application/json' \\
  -H 'x-judge-project: demo' \\
  -d '{"trace_id":"...","name":"hello","spans":[...]}'`}
      </pre>
    </div>
  );
}
