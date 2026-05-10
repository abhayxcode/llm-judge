import { getTrace } from '@/lib/api';
import Link from 'next/link';
import { notFound } from 'next/navigation';

export const dynamic = 'force-dynamic';

function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export default async function TracePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ project?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const project = sp.project ?? 'demo';
  const trace = await getTrace(id, project);
  if (trace === null) notFound();

  const { summary, spans } = trace;

  // Build a parent -> children index for tree rendering.
  const childrenOf = new Map<string | null, typeof spans>();
  for (const s of spans) {
    const list = childrenOf.get(s.parent_span_id) ?? [];
    list.push(s);
    childrenOf.set(s.parent_span_id, list);
  }

  return (
    <main
      style={{
        padding: '3rem 2rem',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        maxWidth: 1100,
        margin: '0 auto',
      }}
    >
      <Link
        href={{ pathname: '/', query: { project } }}
        style={{ color: '#0070f3', textDecoration: 'none' }}
      >
        ← all traces
      </Link>

      <h1 style={{ fontSize: '1.5rem', margin: '0.5rem 0 0.25rem' }}>{summary.name}</h1>
      <div style={{ color: '#666', fontFamily: 'ui-monospace, monospace', fontSize: '0.85rem' }}>
        {summary.trace_id}
      </div>

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
          gap: '0.5rem 1.5rem',
          margin: '1.25rem 0 2rem',
        }}
      >
        <Stat label="duration" value={fmtMs(summary.duration_ms)} />
        <Stat label="spans" value={String(summary.span_count)} />
        <Stat label="status" value={summary.status} />
        <Stat label="tokens" value={String(summary.total_tokens)} />
      </dl>

      <h2 style={{ fontSize: '1.1rem' }}>Spans</h2>
      <SpanTree spans={childrenOf.get(null) ?? []} childrenOf={childrenOf} depth={0} />
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt style={{ fontSize: '0.75rem', color: '#888', textTransform: 'uppercase' }}>{label}</dt>
      <dd style={{ margin: 0, fontSize: '1rem' }}>{value}</dd>
    </div>
  );
}

function SpanTree({
  spans,
  childrenOf,
  depth,
}: {
  spans: ReadonlyArray<{
    span_id: string;
    parent_span_id: string | null;
    name: string;
    duration_ms: number;
    status: string;
    error: string | null;
    attributes: Record<string, string>;
    gen_ai_model: string;
  }>;
  childrenOf: Map<string | null, typeof spans>;
  depth: number;
}) {
  return (
    <ul
      style={{
        listStyle: 'none',
        paddingLeft: depth === 0 ? 0 : '1.5rem',
        marginTop: 0,
        borderLeft: depth === 0 ? 'none' : '1px solid #eee',
      }}
    >
      {spans.map((s) => (
        <li key={s.span_id} style={{ padding: '0.5rem 0' }}>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'baseline' }}>
            <strong style={{ fontFamily: 'ui-monospace, monospace' }}>{s.name}</strong>
            <span style={{ color: '#888', fontSize: '0.85rem' }}>{fmtMs(s.duration_ms)}</span>
            {s.gen_ai_model ? (
              <span style={{ color: '#666', fontSize: '0.8rem' }}>{s.gen_ai_model}</span>
            ) : null}
            {s.status !== 'ok' ? (
              <span style={{ color: '#a13a2a', fontSize: '0.85rem' }}>{s.error ?? s.status}</span>
            ) : null}
          </div>
          {Object.keys(s.attributes).length > 0 ? (
            <pre
              style={{
                background: '#f6f6f6',
                padding: '0.5rem 0.75rem',
                marginTop: '0.4rem',
                marginBottom: 0,
                borderRadius: 6,
                fontSize: '0.8rem',
                overflowX: 'auto',
              }}
            >
              {JSON.stringify(s.attributes, null, 2)}
            </pre>
          ) : null}
          <SpanTree
            spans={childrenOf.get(s.span_id) ?? []}
            childrenOf={childrenOf}
            depth={depth + 1}
          />
        </li>
      ))}
    </ul>
  );
}
