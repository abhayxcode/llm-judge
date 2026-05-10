import {
  type AgreementSnapshot,
  type DatasetRecord,
  type HumanLabel,
  type MetricSummary,
  type QueueItem,
  getAgreement,
  getDatasetRecord,
  listLabels,
  listMetrics,
  listQueue,
} from '@/lib/api';
import Link from 'next/link';
import { refreshQueue, submitLabel } from './actions';

export const dynamic = 'force-dynamic';

export default async function LabelsPage({
  searchParams,
}: {
  searchParams: Promise<{
    project?: string;
    metric?: string;
    user?: string;
    queue?: string;
    done?: string;
    error?: string;
  }>;
}) {
  const sp = await searchParams;
  const project = sp.project ?? 'demo';
  const metrics = await listMetrics(project);
  const metricSlug = sp.metric ?? metrics[0]?.slug ?? '';
  const userEmail = sp.user ?? '';

  const [queue, agreement, recentLabels] = metricSlug
    ? await Promise.all([
        listQueue(project, metricSlug, 25),
        getAgreement(project, metricSlug),
        listLabels(project, metricSlug, 10),
      ])
    : [[] as QueueItem[], null, [] as HumanLabel[]];

  const head = queue.find((q) => q.id === sp.queue) ?? queue[0];
  const headRecord: DatasetRecord | null = head ? await getDatasetRecord(head.record_id) : null;

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
        style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '1rem' }}
      >
        <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Labels</h1>
        <span style={{ color: '#888' }}>
          project: <code>{project}</code>
        </span>
        <Link href={{ pathname: '/', query: { project } }} style={{ color: '#0070f3' }}>
          traces →
        </Link>
        <Link
          href={{ pathname: '/observability', query: { project } }}
          style={{ color: '#0070f3' }}
        >
          observability →
        </Link>
        <Link href={{ pathname: '/runs', query: { project } }} style={{ color: '#0070f3' }}>
          runs →
        </Link>
      </header>

      <MetricBar project={project} metrics={metrics} active={metricSlug} />

      {!metricSlug ? (
        <p style={{ color: '#888' }}>No metrics registered yet for this project.</p>
      ) : (
        <>
          <AgreementCard agreement={agreement} />

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '320px 1fr',
              gap: '1.5rem',
              marginTop: '1.5rem',
            }}
          >
            <QueuePanel project={project} metric={metricSlug} items={queue} activeId={head?.id} />
            {head && headRecord ? (
              <LabelPanel
                project={project}
                metric={metricSlug}
                queueId={head.id}
                userEmail={userEmail}
                record={headRecord}
                strategy={head.strategy}
                priority={head.priority}
                reason={head.reason}
                done={sp.done === '1'}
                error={sp.error ?? null}
              />
            ) : (
              <EmptyQueueState project={project} metric={metricSlug} />
            )}
          </div>

          <h2 style={{ marginTop: '2rem', fontSize: '1rem' }}>Recent labels</h2>
          <RecentLabels labels={recentLabels} />
        </>
      )}
    </main>
  );
}

function MetricBar({
  project,
  metrics,
  active,
}: { project: string; metrics: MetricSummary[]; active: string }) {
  if (metrics.length === 0) return null;
  return (
    <nav
      style={{
        display: 'flex',
        gap: '0.5rem',
        flexWrap: 'wrap',
        marginBottom: '1rem',
      }}
    >
      {metrics.map((m) => (
        <Link
          key={m.id}
          href={{ pathname: '/labels', query: { project, metric: m.slug } }}
          style={{
            padding: '0.25rem 0.7rem',
            borderRadius: 6,
            background: m.slug === active ? '#0070f3' : '#f0f0f0',
            color: m.slug === active ? 'white' : '#444',
            fontSize: '0.85rem',
            textDecoration: 'none',
          }}
        >
          {m.slug}
          <span style={{ opacity: 0.6, marginLeft: 6 }}>v{m.latest_version ?? '?'}</span>
        </Link>
      ))}
    </nav>
  );
}

function AgreementCard({ agreement }: { agreement: AgreementSnapshot | null }) {
  return (
    <section
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, minmax(0, 1fr))',
        gap: '0.75rem',
        padding: '0.75rem',
        background: '#fafafa',
        border: '1px solid #eee',
        borderRadius: 8,
      }}
    >
      <Stat label="Labels" value={agreement ? String(agreement.n_labels) : '0'} />
      <Stat
        label="Cohen κ"
        value={fmt(agreement?.cohen_kappa)}
        tone={tone(agreement?.cohen_kappa)}
      />
      <Stat
        label="Fleiss κ"
        value={fmt(agreement?.fleiss_kappa)}
        tone={tone(agreement?.fleiss_kappa)}
      />
      <Stat label="Pearson r" value={fmt(agreement?.pearson_r)} />
      <Stat label="Spearman ρ" value={fmt(agreement?.spearman_r)} />
    </section>
  );
}

function tone(v: number | null | undefined): 'warn' | 'normal' {
  if (v === null || v === undefined) return 'normal';
  if (v < 0.2) return 'warn';
  return 'normal';
}

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return v.toFixed(3);
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'warn' | 'normal' }) {
  return (
    <div>
      <div style={{ fontSize: '0.7rem', color: '#888', textTransform: 'uppercase' }}>{label}</div>
      <div
        style={{
          fontSize: '1.2rem',
          fontWeight: 600,
          color: tone === 'warn' ? '#a13a2a' : '#222',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </div>
    </div>
  );
}

function QueuePanel({
  project,
  metric,
  items,
  activeId,
}: {
  project: string;
  metric: string;
  items: QueueItem[];
  activeId: string | undefined;
}) {
  return (
    <aside
      style={{
        border: '1px solid #eee',
        borderRadius: 8,
        background: '#fafafa',
        padding: '0.75rem',
        height: 'fit-content',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ fontSize: '0.9rem', margin: 0 }}>Queue</h2>
        <form action={refreshQueue}>
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="metric" value={metric} />
          <input type="hidden" name="queue_size" value="50" />
          <button
            type="submit"
            style={{
              fontSize: '0.7rem',
              border: 0,
              background: '#0070f3',
              color: 'white',
              padding: '0.2rem 0.6rem',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            refresh
          </button>
        </form>
      </div>

      {items.length === 0 ? (
        <p style={{ color: '#888', fontSize: '0.85rem', marginTop: '0.75rem' }}>
          Queue empty. Click <em>refresh</em> after a run lands to seed candidates.
        </p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: '0.75rem 0 0' }}>
          {items.map((q) => (
            <li key={q.id}>
              <Link
                href={{ pathname: '/labels', query: { project, metric, queue: q.id } }}
                style={{
                  display: 'block',
                  padding: '0.4rem 0.5rem',
                  borderRadius: 4,
                  background: q.id === activeId ? '#e6f1ff' : 'transparent',
                  color: '#222',
                  textDecoration: 'none',
                  fontSize: '0.8rem',
                  borderBottom: '1px solid #f0f0f0',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <code style={{ color: '#888' }}>{q.record_id.slice(0, 10)}…</code>
                  <span style={{ color: '#666', fontVariantNumeric: 'tabular-nums' }}>
                    {q.priority.toFixed(2)}
                  </span>
                </div>
                <div style={{ color: '#666', fontSize: '0.7rem' }}>{q.strategy}</div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function EmptyQueueState({ project, metric }: { project: string; metric: string }) {
  return (
    <section
      style={{
        border: '1px dashed #ccc',
        borderRadius: 8,
        padding: '2rem',
        color: '#666',
      }}
    >
      <p style={{ marginTop: 0 }}>
        Queue empty for <code>{metric}</code>.
      </p>
      <p style={{ fontSize: '0.85rem' }}>
        Run a judge eval first (<code>judge run --suite ...</code>), then click
        <em> refresh</em> on the queue panel. The active-learning sampler will rank records that are
        uncertain or atypical.
      </p>
      <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
        Or label any record by ID via <code>POST /v1/labels</code> against{' '}
        <code>project={project}</code>.
      </p>
    </section>
  );
}

function LabelPanel({
  project,
  metric,
  queueId,
  userEmail,
  record,
  strategy,
  priority,
  reason,
  done,
  error,
}: {
  project: string;
  metric: string;
  queueId: string;
  userEmail: string;
  record: DatasetRecord;
  strategy: string;
  priority: number;
  reason: string | null;
  done: boolean;
  error: string | null;
}) {
  return (
    <section
      style={{
        border: '1px solid #eee',
        borderRadius: 8,
        padding: '1.25rem',
        background: 'white',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem' }}>
        <h2 style={{ fontSize: '1rem', margin: 0 }}>
          Label record
          <code style={{ marginLeft: 8, color: '#888', fontSize: '0.85em' }}>
            {record.id.slice(0, 12)}…
          </code>
        </h2>
        <span style={{ color: '#666', fontSize: '0.8rem' }}>
          {strategy} · priority {priority.toFixed(2)}
        </span>
      </div>
      {reason ? (
        <p style={{ color: '#888', fontSize: '0.85rem', margin: '0.25rem 0 1rem' }}>
          why surfaced: {reason}
        </p>
      ) : null}

      {done ? (
        <p style={{ color: '#1f7a3a', fontSize: '0.9rem' }}>
          ✓ saved. Pick the next item from the queue, or close.
        </p>
      ) : null}
      {error ? <p style={{ color: '#a13a2a', fontSize: '0.9rem' }}>! error: {error}</p> : null}

      <h3 style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase' }}>Input</h3>
      <KVList obj={record.input as Record<string, unknown>} />
      {record.expected_output ? (
        <>
          <h3 style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase' }}>
            Expected output
          </h3>
          <pre
            style={{
              background: '#f6f6f6',
              padding: '0.6rem',
              borderRadius: 4,
              whiteSpace: 'pre-wrap',
              fontSize: '0.85rem',
            }}
          >
            {record.expected_output}
          </pre>
        </>
      ) : null}
      {record.context ? (
        <>
          <h3 style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase' }}>
            Context
          </h3>
          <KVList obj={record.context as Record<string, unknown>} />
        </>
      ) : null}

      <form action={submitLabel} style={{ marginTop: '1rem' }}>
        <input type="hidden" name="project" value={project} />
        <input type="hidden" name="metric" value={metric} />
        <input type="hidden" name="record_id" value={record.id} />
        <input type="hidden" name="queue_id" value={queueId} />

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '120px 1fr',
            gap: '0.5rem 0.75rem',
            alignItems: 'center',
          }}
        >
          <label htmlFor="user_email">User email</label>
          <input
            id="user_email"
            name="user_email"
            type="email"
            required
            defaultValue={userEmail}
            placeholder="me@example.com"
            style={{ padding: '0.4rem', border: '1px solid #ddd', borderRadius: 4 }}
          />

          <label htmlFor="score">Score</label>
          <div style={{ display: 'flex', gap: '0.4rem' }}>
            {[1, 2, 3, 4, 5].map((n) => (
              <label
                key={n}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
              >
                <input type="radio" name="score" value={n} required style={{ margin: 0 }} />
                {n}
              </label>
            ))}
            <span style={{ color: '#888', fontSize: '0.8rem', marginLeft: '0.5rem' }}>
              (1 = bad, 5 = perfect)
            </span>
          </div>

          <label htmlFor="rationale">Rationale</label>
          <textarea
            id="rationale"
            name="rationale"
            rows={3}
            placeholder="why this score?"
            style={{ padding: '0.4rem', border: '1px solid #ddd', borderRadius: 4 }}
          />

          <label htmlFor="tags">Tags</label>
          <input
            id="tags"
            name="tags"
            placeholder="comma,separated,tags"
            style={{ padding: '0.4rem', border: '1px solid #ddd', borderRadius: 4 }}
          />
        </div>

        <button
          type="submit"
          style={{
            marginTop: '1rem',
            padding: '0.5rem 1rem',
            background: '#0070f3',
            color: 'white',
            border: 0,
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: '0.95rem',
          }}
        >
          Save label
        </button>
      </form>
    </section>
  );
}

function KVList({ obj }: { obj: Record<string, unknown> }) {
  return (
    <dl style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '0.4rem 0.75rem' }}>
      {Object.entries(obj).map(([k, v]) => (
        <KVRow key={k} k={k} v={v} />
      ))}
    </dl>
  );
}

function KVRow({ k, v }: { k: string; v: unknown }) {
  const text = typeof v === 'string' ? v : JSON.stringify(v);
  return (
    <>
      <dt style={{ color: '#666', fontSize: '0.85rem' }}>{k}</dt>
      <dd
        style={{
          margin: 0,
          fontSize: '0.9rem',
          whiteSpace: 'pre-wrap',
          overflowWrap: 'anywhere',
        }}
      >
        {text}
      </dd>
    </>
  );
}

function RecentLabels({ labels }: { labels: HumanLabel[] }) {
  if (labels.length === 0) {
    return <p style={{ color: '#888', fontSize: '0.85rem' }}>None yet.</p>;
  }
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
      <thead>
        <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
          <th style={{ padding: '0.4rem' }}>When</th>
          <th style={{ padding: '0.4rem' }}>User</th>
          <th style={{ padding: '0.4rem' }}>Record</th>
          <th style={{ padding: '0.4rem' }}>Score</th>
          <th style={{ padding: '0.4rem' }}>Rationale</th>
        </tr>
      </thead>
      <tbody>
        {labels.map((lab) => (
          <tr key={lab.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
            <td style={{ padding: '0.4rem', color: '#666' }}>
              {new Date(lab.created_at).toISOString().slice(0, 19).replace('T', ' ')}
            </td>
            <td style={{ padding: '0.4rem' }}>{lab.user_email}</td>
            <td style={{ padding: '0.4rem', fontFamily: 'ui-monospace, monospace', color: '#666' }}>
              {lab.record_id.slice(0, 10)}…
            </td>
            <td style={{ padding: '0.4rem', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
              {lab.score}
            </td>
            <td style={{ padding: '0.4rem', color: '#444' }}>{lab.rationale ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
