// Package queue wraps the Redis Streams writer used by the ingest service.
//
// At M1 we publish one stream entry per accepted trace. Workers consume the
// stream via XREADGROUP and write into ClickHouse. Backpressure is handled
// by stream MAXLEN: oldest entries are evicted approximately when the cap
// is exceeded.
package queue

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/redis/go-redis/v9"
)

// Publisher publishes traces to a Redis Stream.
type Publisher struct {
	client     *redis.Client
	streamName string
	maxLen     int64
}

// NewPublisher constructs a Publisher from a Redis URL and stream config.
func NewPublisher(ctx context.Context, redisURL, streamName string, maxLen int64) (*Publisher, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	client := redis.NewClient(opts)
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis ping: %w", err)
	}
	return &Publisher{client: client, streamName: streamName, maxLen: maxLen}, nil
}

// PublishTrace pushes a single trace payload onto the stream. The payload is
// stored as a JSON blob under the "payload" field so consumers can decode
// without inspecting the stream entry shape.
func (p *Publisher) PublishTrace(ctx context.Context, projectID, orgID string, payload json.RawMessage) (string, error) {
	res, err := p.client.XAdd(ctx, &redis.XAddArgs{
		Stream: p.streamName,
		MaxLen: p.maxLen,
		Approx: true,
		Values: map[string]any{
			"project_id": projectID,
			"org_id":     orgID,
			"payload":    string(payload),
		},
	}).Result()
	if err != nil {
		return "", fmt.Errorf("xadd: %w", err)
	}
	return res, nil
}

// Close releases the underlying Redis connection pool.
func (p *Publisher) Close() error {
	return p.client.Close()
}

// Ping checks Redis connectivity for readiness probes.
func (p *Publisher) Ping(ctx context.Context) error {
	return p.client.Ping(ctx).Err()
}
