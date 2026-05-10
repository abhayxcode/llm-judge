import { listRuns } from '@/lib/api';
import Link from 'next/link';

export const dynamic = 'force-dynamic';

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace('T', ' ').replace('Z', '');
}

export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ project?: string }>;
}) {
  const params = await searchParams;
  const project = params.project ?? 'demo';
  const runs = await listRuns(project, 100);

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
        <h1 style={{ fontSize: '1.75rem', margin: 0 }}>Runs</h1>
        <span style={{ color: '#888' }}>
          project: <code>{project}</code>
        </span>
        <Link
          href={{ pathname: '/', query: { project } }}
          style={{ marginLeft: 'auto', color: '#0070f3' }}
        >
          ← traces
        </Link>
      </header>

      {runs.length === 0 ? (
        <Empty />
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.95rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid #ddd' }}>
              <Th>Run</Th>
              <Th>Name</Th>
              <Th>Status</Th>
              <Th>Progress</Th>
              <Th>Errors</Th>
              <Th>Started</Th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} style={{ borderBottom: '1px solid #eee' }}>
                <Td>
                  <Link
                    href={{ pathname: `/runs/${r.id}`, query: { project } }}
                    style={{ fontFamily: 'ui-monospace, monospace', color: '#0070f3' }}
                  >
                    {r.id.slice(0, 12)}…
                  </Link>
                </Td>
                <Td>{r.name}</Td>
                <Td>
                  <StatusPill status={r.status} />
                </Td>
                <Td>
                  {r.completed_count}/{r.record_count}
                </Td>
                <Td style={{ color: r.error_count > 0 ? '#a13a2a' : '#666' }}>{r.error_count}</Td>
                <Td style={{ color: '#666' }}>{fmtTime(r.started_at)}</Td>
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
  const colors: Record<string, [string, string]> = {
    queued: ['#f0f0f0', '#555'],
    running: ['#fff4d6', '#7a5b00'],
    done: ['#e6f7ec', '#1f7a3a'],
    failed: ['#fdecea', '#a13a2a'],
  };
  const [bg, fg] = colors[status] ?? ['#eee', '#444'];
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.15rem 0.5rem',
        borderRadius: 999,
        fontSize: '0.8rem',
        background: bg,
        color: fg,
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
        <strong>No runs yet.</strong>
      </p>
      <p>
        Kick one off with the CLI:{' '}
        <code>judge run --suite eval-bench/suites/faithfulness.yaml</code>
      </p>
    </div>
  );
}
