import { getRun, getRunScores } from '@/lib/api';
import Link from 'next/link';
import { notFound } from 'next/navigation';

export const dynamic = 'force-dynamic';

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace('T', ' ').replace('Z', '');
}

function fmtMoney(n: number): string {
  return `$${n.toFixed(4)}`;
}

export default async function RunDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ project?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const project = sp.project ?? 'demo';

  const [run, scores] = await Promise.all([getRun(id), getRunScores(id)]);
  if (!run) notFound();

  const total = scores.length;
  const meanScore = total > 0 ? scores.reduce((a, s) => a + s.score, 0) / total : 0;
  const totalCost = scores.reduce((a, s) => a + s.cost_usd, 0);
  const avgLatency = total > 0 ? scores.reduce((a, s) => a + s.latency_ms, 0) / total : 0;

  return (
    <main
      style={{
        padding: '3rem 2rem',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        maxWidth: 1200,
        margin: '0 auto',
      }}
    >
      <header style={{ marginBottom: '2rem' }}>
        <Link
          href={{ pathname: '/runs', query: { project } }}
          style={{ color: '#0070f3', fontSize: '0.9rem' }}
        >
          ← runs
        </Link>
        <h1 style={{ fontSize: '1.5rem', margin: '0.5rem 0 0.25rem 0' }}>{run.name}</h1>
        <code style={{ color: '#888', fontSize: '0.85rem' }}>{run.id}</code>
      </header>

      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
          gap: '1rem',
          marginBottom: '2rem',
        }}
      >
        <Stat label="Status" value={run.status} />
        <Stat label="Progress" value={`${run.completed_count} / ${run.record_count}`} />
        <Stat
          label="Errors"
          value={String(run.error_count)}
          tone={run.error_count > 0 ? 'warn' : 'normal'}
        />
        <Stat
          label="Mean score"
          value={total > 0 ? meanScore.toFixed(3) : '—'}
          hint="normalized 0–1"
        />
        <Stat label="Total cost" value={fmtMoney(totalCost)} />
        <Stat label="Avg latency" value={total > 0 ? `${Math.round(avgLatency)} ms` : '—'} />
        <Stat label="Started" value={fmtTime(run.started_at)} />
        <Stat label="Finished" value={fmtTime(run.finished_at)} />
      </section>

      <h2 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Scores ({total})</h2>
      {total === 0 ? (
        <p style={{ color: '#888' }}>No scores recorded yet.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid #ddd' }}>
              <Th>Record</Th>
              <Th>Score</Th>
              <Th>Raw</Th>
              <Th>Judge</Th>
              <Th>Cost</Th>
              <Th>Latency</Th>
              <Th>Reasoning</Th>
            </tr>
          </thead>
          <tbody>
            {scores.map((s) => (
              <tr key={s.trace_id + (s.span_id ?? '')} style={{ borderBottom: '1px solid #eee' }}>
                <Td style={{ fontFamily: 'ui-monospace, monospace', color: '#666' }}>
                  {s.trace_id.slice(0, 10)}…
                </Td>
                <Td>
                  <ScorePill score={s.score} />
                </Td>
                <Td style={{ color: '#666' }}>{s.score_raw || '—'}</Td>
                <Td style={{ color: '#666' }}>{s.judge_model}</Td>
                <Td>{fmtMoney(s.cost_usd)}</Td>
                <Td style={{ color: '#666' }}>{s.latency_ms} ms</Td>
                <Td>
                  <ReasoningCell text={s.reasoning} />
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'warn' | 'normal';
}) {
  return (
    <div
      style={{
        padding: '0.75rem',
        border: '1px solid #eee',
        borderRadius: 8,
        background: '#fafafa',
      }}
    >
      <div style={{ fontSize: '0.75rem', color: '#888', textTransform: 'uppercase' }}>{label}</div>
      <div
        style={{
          fontSize: '1.1rem',
          fontWeight: 600,
          color: tone === 'warn' ? '#a13a2a' : '#222',
          marginTop: '0.15rem',
        }}
      >
        {value}
      </div>
      {hint ? (
        <div style={{ fontSize: '0.7rem', color: '#aaa', marginTop: '0.15rem' }}>{hint}</div>
      ) : null}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th style={{ padding: '0.5rem', fontWeight: 600, color: '#444' }}>{children}</th>;
}

function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <td style={{ padding: '0.5rem', verticalAlign: 'top', ...style }}>{children}</td>;
}

function ScorePill({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const good = score >= 0.7;
  const warn = score >= 0.4 && score < 0.7;
  const bg = good ? '#e6f7ec' : warn ? '#fff4d6' : '#fdecea';
  const fg = good ? '#1f7a3a' : warn ? '#7a5b00' : '#a13a2a';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.15rem 0.5rem',
        borderRadius: 999,
        background: bg,
        color: fg,
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {pct}%
    </span>
  );
}

function ReasoningCell({ text }: { text: string | null }) {
  if (!text) return <span style={{ color: '#bbb' }}>—</span>;
  return (
    <details>
      <summary style={{ cursor: 'pointer', color: '#0070f3' }}>show</summary>
      <pre
        style={{
          maxWidth: 600,
          whiteSpace: 'pre-wrap',
          background: '#f6f6f6',
          padding: '0.5rem',
          borderRadius: 6,
          marginTop: '0.4rem',
          fontSize: '0.8rem',
        }}
      >
        {text}
      </pre>
    </details>
  );
}
