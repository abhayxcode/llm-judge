import { apiUrl, listTraces } from '@/lib/api';
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

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ project?: string }>;
}) {
  const params = await searchParams;
  const project = params.project ?? 'demo';
  const traces = await listTraces(project, 50);

  return (
    <main
      style={{
        padding: '3rem 2rem',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        maxWidth: 1100,
        margin: '0 auto',
      }}
    >
      <header
        style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '2rem' }}
      >
        <h1 style={{ fontSize: '1.75rem', margin: 0 }}>LLM Judge</h1>
        <span style={{ color: '#888' }}>
          project: <code>{project}</code>
        </span>
        <span style={{ marginLeft: 'auto', color: '#888', fontSize: '0.875rem' }}>
          api: <code>{apiUrl}</code>
        </span>
      </header>

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
