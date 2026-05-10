package config

import (
	"errors"
	"os"
	"strconv"
)

// Config is the runtime configuration for the ingest service.
// Loaded from environment variables.
type Config struct {
	ListenAddr        string
	Env               string
	RedisURL          string
	StreamName        string
	StreamMaxLen      int64
	MaxBodyBytes      int64
	DefaultProjectID  string
	DefaultOrgID      string
}

// Load reads configuration from the environment with sensible defaults
// for local development.
func Load() (*Config, error) {
	cfg := &Config{
		ListenAddr:       getEnv("INGEST_LISTEN_ADDR", ":4318"),
		Env:              getEnv("INGEST_ENV", "local"),
		RedisURL:         getEnv("REDIS_URL", "redis://localhost:6380/0"),
		StreamName:       getEnv("INGEST_STREAM", "judge:traces"),
		StreamMaxLen:     getEnvInt64("INGEST_STREAM_MAXLEN", 1_000_000),
		MaxBodyBytes:     getEnvInt64("INGEST_MAX_BODY_BYTES", 5*1024*1024), // 5 MB
		DefaultProjectID: getEnv("INGEST_DEFAULT_PROJECT", "demo"),
		DefaultOrgID:     getEnv("INGEST_DEFAULT_ORG", "default"),
	}
	if cfg.ListenAddr == "" {
		return nil, errors.New("INGEST_LISTEN_ADDR is required")
	}
	if cfg.RedisURL == "" {
		return nil, errors.New("REDIS_URL is required")
	}
	return cfg, nil
}

func getEnv(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return fallback
}

func getEnvInt64(key string, fallback int64) int64 {
	v, ok := os.LookupEnv(key)
	if !ok {
		return fallback
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		return fallback
	}
	return n
}
