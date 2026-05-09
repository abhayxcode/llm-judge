// Package server wires the HTTP routes for the ingest service.
package server

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/abhayxcode/llm-judge/services/ingest/internal/config"
)

// Server holds shared dependencies for HTTP handlers.
type Server struct {
	cfg    *config.Config
	logger *slog.Logger
}

// New constructs a Server.
func New(cfg *config.Config, logger *slog.Logger) *Server {
	return &Server{cfg: cfg, logger: logger}
}

// Routes returns the http.Handler for all ingest routes.
func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("GET /ready", s.handleReady)
	mux.HandleFunc("POST /v1/traces", s.handleTraces)
	mux.HandleFunc("POST /v1/otlp/traces", s.handleOTLPTraces)

	return s.requestLogger(mux)
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "ok",
		"time":   time.Now().UTC().Format(time.RFC3339),
		"env":    s.cfg.Env,
	})
}

func (s *Server) handleReady(w http.ResponseWriter, _ *http.Request) {
	// Stub: real readiness will check Redis Stream + ClickHouse connectivity.
	writeJSON(w, http.StatusOK, map[string]any{"ready": true})
}

func (s *Server) handleTraces(w http.ResponseWriter, _ *http.Request) {
	// Stub. Real implementation: validate, redact-respect, write to Redis stream,
	// async writer batches into ClickHouse.
	writeJSON(w, http.StatusAccepted, map[string]any{"accepted": true, "stub": true})
}

func (s *Server) handleOTLPTraces(w http.ResponseWriter, _ *http.Request) {
	// Stub for OTLP/HTTP. gRPC endpoint added later.
	writeJSON(w, http.StatusAccepted, map[string]any{"accepted": true, "stub": true})
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func (s *Server) requestLogger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rw, r)
		s.logger.Info(
			"http",
			"method", r.Method,
			"path", r.URL.Path,
			"status", rw.status,
			"duration_ms", time.Since(start).Milliseconds(),
		)
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}
