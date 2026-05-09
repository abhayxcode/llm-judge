export default function HomePage() {
  return (
    <main
      style={{
        padding: '4rem 2rem',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        maxWidth: 720,
        margin: '0 auto',
      }}
    >
      <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>LLM Judge</h1>
      <p style={{ color: '#555', marginBottom: '2rem' }}>
        Pre-release. M1 skeleton. Real UI lands in M3.
      </p>
      <ul style={{ lineHeight: 1.8 }}>
        <li>
          API:{' '}
          <a href="http://localhost:4000/health" rel="noreferrer">
            http://localhost:4000/health
          </a>
        </li>
        <li>
          Ingest:{' '}
          <a href="http://localhost:4318/health" rel="noreferrer">
            http://localhost:4318/health
          </a>
        </li>
        <li>MinIO console: http://localhost:9001</li>
      </ul>
    </main>
  );
}
