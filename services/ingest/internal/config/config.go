package config

import (
	"errors"
	"os"
)

// Config is the runtime configuration for the ingest service.
// Loaded from environment variables.
type Config struct {
	ListenAddr string
	Env        string
}

// Load reads configuration from the environment with sensible defaults
// for local development.
func Load() (*Config, error) {
	cfg := &Config{
		ListenAddr: getEnv("INGEST_LISTEN_ADDR", ":4318"),
		Env:        getEnv("INGEST_ENV", "local"),
	}
	if cfg.ListenAddr == "" {
		return nil, errors.New("INGEST_LISTEN_ADDR is required")
	}
	return cfg, nil
}

func getEnv(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return fallback
}
