-- ClickHouse schema for LLM Judge (M1)
--
-- Loaded automatically on a fresh `judge` database via ClickHouse's
-- /docker-entrypoint-initdb.d hook. For non-fresh DBs apply via:
--
--     uv run judge-api migrate-ch
--
-- Schema is polymorphic from day 1 (per SPEC §18.1):
--   - flat traces (RAG, Chat) and tree-shaped traces (Agents) coexist
--     because each span has a nullable parent_span_id; root span has parent=NULL.
--   - new metric surfaces (P2/P3) extend by adding columns or new tables;
--     never break this schema.

CREATE TABLE IF NOT EXISTS spans
(
    -- Tenant + addressing
    org_id        LowCardinality(String),
    project_id    LowCardinality(String),
    trace_id      String,
    span_id       String,
    parent_span_id Nullable(String),

    -- Identity
    trace_name    LowCardinality(String),
    name          LowCardinality(String),

    -- Timing (epoch ms; CH stores as DateTime64(3, 'UTC'))
    start_ts      DateTime64(3, 'UTC'),
    end_ts        Nullable(DateTime64(3, 'UTC')),
    duration_ms   Int64 MATERIALIZED if(end_ts IS NULL, 0, dateDiff('millisecond', start_ts, end_ts)),

    -- Status
    status        LowCardinality(String) DEFAULT 'ok',
    error         Nullable(String),

    -- Generator metadata (gen_ai.* if present)
    gen_ai_system   LowCardinality(String) DEFAULT '',
    gen_ai_model    LowCardinality(String) DEFAULT '',
    input_tokens    Int32 DEFAULT 0,
    output_tokens   Int32 DEFAULT 0,
    total_tokens    Int32 MATERIALIZED input_tokens + output_tokens,

    -- Free-form attributes; large fields externalized to S3 by ingest worker
    attributes    Map(String, String),
    blob_refs     Map(String, String),  -- key -> "s3://bucket/key"

    -- Bookkeeping
    is_root       UInt8 MATERIALIZED parent_span_id IS NULL,
    sdk_version   LowCardinality(String) DEFAULT '',
    sdk_lang      LowCardinality(String) DEFAULT '',
    received_at   DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(start_ts)
ORDER BY (project_id, start_ts, trace_id, span_id)
TTL toDateTime(start_ts) + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192;

-- Per-trace summary view. For dashboards we usually want one row per trace.
-- This is computed on read in M1 to keep ingestion simple; we can swap to
-- a materialized view once write-heavy patterns prove worth it.
CREATE OR REPLACE VIEW v_traces AS
SELECT
    org_id,
    project_id,
    trace_id,
    any(trace_name)                                            AS trace_name,
    min(start_ts)                                              AS first_seen,
    max(coalesce(end_ts, start_ts))                            AS last_seen,
    dateDiff('millisecond', min(start_ts), max(coalesce(end_ts, start_ts))) AS duration_ms,
    countIf(parent_span_id IS NULL)                            AS root_span_count,
    count()                                                    AS span_count,
    anyIf(status, parent_span_id IS NULL)                      AS status,
    anyIf(error, parent_span_id IS NULL AND error IS NOT NULL) AS error,
    sum(input_tokens)                                          AS input_tokens,
    sum(output_tokens)                                         AS output_tokens,
    sum(total_tokens)                                          AS total_tokens
FROM spans
GROUP BY org_id, project_id, trace_id;

-- Scores land in M2 alongside the eval engine; table created up-front so
-- downstream queries can JOIN against it without a follow-on migration.
CREATE TABLE IF NOT EXISTS scores
(
    org_id          LowCardinality(String),
    project_id      LowCardinality(String),
    trace_id        String,
    span_id         Nullable(String),  -- score may target a whole trace or one span

    metric_id       LowCardinality(String),
    metric_version  LowCardinality(String),

    score           Float32,
    score_raw       String,            -- stringified original (e.g. "4 / 5")
    reasoning       Nullable(String),
    label           Nullable(String),  -- e.g. winner=A in pairwise

    judge_model     LowCardinality(String),
    judge_provider  LowCardinality(String),
    cost_usd        Float32 DEFAULT 0,
    latency_ms      Int32   DEFAULT 0,

    -- Bias / calibration markers
    self_enhancement_warning UInt8 DEFAULT 0,
    position_swapped UInt8 DEFAULT 0,
    consistency      Nullable(Float32),

    computed_at     DateTime64(3, 'UTC') DEFAULT now64(3),
    attributes      Map(String, String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(computed_at)
ORDER BY (project_id, metric_id, computed_at, trace_id);

CREATE TABLE IF NOT EXISTS audit_log_ch
(
    org_id     LowCardinality(String),
    actor      String,
    action     LowCardinality(String),
    target     String,
    metadata   Map(String, String),
    created_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (org_id, created_at);
