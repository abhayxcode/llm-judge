import { getScoreDistribution, getStats, getTimeseries } from '@/lib/api';
import Link from 'next/link';

export const dynamic = 'force-dynamic';

const VALID_WINDOWS: Record<string, number> = {
  '15m': 15,
  '1h': 60,
  '6h': 360,
  '24h': 1440,
};

export default async function ObservabilityPage({
  searchParams,
}: {
  searchParams: Promise<{ project?: string; window?: string }>;
}) {
  const sp = await searchParams;
  const project = sp.project ?? 'demo';
  const windowKey = sp.window && VALID_WINDOWS[sp.window] ? sp.window : '1h';
  const sinceMinutes = VALID_WINDOWS[windowKey] ?? 60;

  const bucket: '1m' | '5m' | '1h' = sinceMinutes <= 60 ? '1m' : sinceMinutes <= 360 ? '5m' : '1h';

  const [stats, ts, scoreDist] = await Promise.all([
    getStats(project, sinceMinutes),
    getTimeseries(project, bucket, sinceMinutes),
    getScoreDistribution(project, sinceMinutes),
  ]);

  return (
    <main
      style={{
        padding: '2rem',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        maxWidth: 1200,
        margin: '0 auto',
      }}
    >
      <header
        style={{ marginBottom: '2rem', display: 'flex', alignItems: 'baseline', gap: '1rem' }}
      >
        <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Observability</h1>
        <span style={{ color: '#888' }}>
          project: <code>{project}</code>
        </span>
        <nav style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem' }}>
          {Object.keys(VALID_WINDOWS).map((k) => (
            <Link
              key={k}
              href={{ pathname: '/observability', query: { project, window: k } }}
              style={{
                padding: '0.25rem 0.6rem',
                borderRadius: 6,
                background: k === windowKey ? '#0070f3' : '#f0f0f0',
                color: k === windowKey ? 'white' : '#444',
                fontSize: '0.85rem',
                textDecoration: 'none',
              }}
            >
              {k}
            </Link>
          ))}
        </nav>
        <Link href={{ pathname: '/', query: { project } }} style={{ color: '#0070f3' }}>
          traces →
        </Link>
      </header>

      {!stats ? (
        <p style={{ color: '#888' }}>API unreachable.</p>
      ) : (
        <>
          <section
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
              gap: '1rem',
              marginBottom: '2rem',
            }}
          >
            <Stat label="Traces" value={String(stats.trace_count)} />
            <Stat
              label="Errors"
              value={String(stats.error_count)}
              tone={stats.error_count > 0 ? 'warn' : 'normal'}
            />
            <Stat label="p50 latency" value={`${Math.round(stats.p50_ms)} ms`} />
            <Stat label="p95 latency" value={`${Math.round(stats.p95_ms)} ms`} />
            <Stat label="Input tokens" value={fmtCompact(stats.input_tokens)} />
            <Stat label="Output tokens" value={fmtCompact(stats.output_tokens)} />
          </section>

          <h2 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>Trace volume ({bucket})</h2>
          <Sparkline points={ts?.points ?? []} field="count" color="#0070f3" height={120} />

          <h2 style={{ fontSize: '1rem', margin: '1.5rem 0 0.5rem' }}>p95 latency (ms)</h2>
          <Sparkline points={ts?.points ?? []} field="p95_ms" color="#a13a2a" height={120} />

          <h2 style={{ fontSize: '1rem', margin: '1.5rem 0 0.5rem' }}>Score distribution</h2>
          <ScoreDistribution buckets={scoreDist} />
        </>
      )}
    </main>
  );
}

function fmtCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
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
      <div style={{ fontSize: '0.7rem', color: '#888', textTransform: 'uppercase' }}>{label}</div>
      <div
        style={{
          fontSize: '1.4rem',
          fontWeight: 600,
          color: tone === 'warn' ? '#a13a2a' : '#222',
          marginTop: '0.15rem',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </div>
    </div>
  );
}

function Sparkline({
  points,
  field,
  color,
  height,
}: {
  points: { ts: string; count: number; p95_ms: number }[];
  field: 'count' | 'p95_ms';
  color: string;
  height: number;
}) {
  if (points.length === 0) {
    return (
      <div
        style={{
          height,
          border: '1px dashed #ddd',
          borderRadius: 8,
          color: '#bbb',
          display: 'grid',
          placeItems: 'center',
        }}
      >
        no data in window
      </div>
    );
  }
  const values = points.map((p) => Number(p[field as keyof typeof p] ?? 0));
  const max = Math.max(1, ...values);
  return (
    <svg
      viewBox={`0 0 ${points.length * 12} ${height}`}
      style={{ width: '100%', height, background: '#fafafa', borderRadius: 8 }}
      preserveAspectRatio="none"
      role="img"
      aria-label={`sparkline of ${field}`}
    >
      {values.map((v, i) => {
        const h = (v / max) * (height - 8);
        return (
          <rect
            key={`${points[i]?.ts ?? i}-${i}`}
            x={i * 12}
            y={height - h}
            width={10}
            height={h}
            fill={color}
            opacity={0.85}
          />
        );
      })}
    </svg>
  );
}

function ScoreDistribution({
  buckets,
}: { buckets: { metric_id: string; bucket: string; count: number }[] }) {
  if (buckets.length === 0) {
    return <p style={{ color: '#888' }}>No scores yet in window.</p>;
  }
  const byMetric = buckets.reduce<Record<string, { bucket: string; count: number }[]>>((acc, b) => {
    const existing = acc[b.metric_id] ?? [];
    existing.push({ bucket: b.bucket, count: b.count });
    acc[b.metric_id] = existing;
    return acc;
  }, {});
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '1rem',
      }}
    >
      {Object.entries(byMetric).map(([metric, rows]) => {
        const max = Math.max(...rows.map((r) => r.count));
        return (
          <div
            key={metric}
            style={{
              border: '1px solid #eee',
              borderRadius: 8,
              padding: '0.75rem',
              background: '#fafafa',
            }}
          >
            <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              {metric}
            </div>
            {rows.map((r) => (
              <div
                key={r.bucket}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  fontSize: '0.75rem',
                }}
              >
                <span style={{ width: 56, color: '#666' }}>{r.bucket}</span>
                <div style={{ flex: 1, height: 10, background: '#eee', borderRadius: 4 }}>
                  <div
                    style={{
                      width: `${(r.count / max) * 100}%`,
                      height: '100%',
                      background: '#0070f3',
                      borderRadius: 4,
                    }}
                  />
                </div>
                <span style={{ width: 32, textAlign: 'right', color: '#666' }}>{r.count}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
