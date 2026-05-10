// Package server wires the HTTP routes for the ingest service.
package server

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/abhayxcode/llm-judge/services/ingest/internal/config"
	"github.com/abhayxcode/llm-judge/services/ingest/internal/otlp"
	"github.com/abhayxcode/llm-judge/services/ingest/internal/queue"
)

// Publisher is the abstraction the server uses to publish traces.
// Allows tests to inject a fake.
type Publisher interface {
	PublishTrace(ctx context.Context, projectID, orgID string, payload []byte) (string, error)
	Ping(ctx context.Context) error
}

// realPublisher adapts queue.Publisher to the json.RawMessage-free interface.
type realPublisher struct{ inner *queue.Publisher }

func (r *realPublisher) PublishTrace(ctx context.Context, projectID, orgID string, payload []byte) (string, error) {
	return r.inner.PublishTrace(ctx, projectID, orgID, payload)
}

func (r *realPublisher) Ping(ctx context.Context) error { return r.inner.Ping(ctx) }

// Server holds shared dependencies for HTTP handlers.
type Server struct {
	cfg    *config.Config
	logger *slog.Logger
	pub    Publisher
}

// New constructs a Server with a real Redis publisher.
func New(ctx context.Context, cfg *config.Config, logger *slog.Logger) (*Server, error) {
	pub, err := queue.NewPublisher(ctx, cfg.RedisURL, cfg.StreamName, cfg.StreamMaxLen)
	if err != nil {
		return nil, err
	}
	return &Server{cfg: cfg, logger: logger, pub: &realPublisher{inner: pub}}, nil
}

// NewWithPublisher constructs a Server with an injected publisher.
// Used by tests + ops tooling.
func NewWithPublisher(cfg *config.Config, logger *slog.Logger, pub Publisher) *Server {
	return &Server{cfg: cfg, logger: logger, pub: pub}
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

func (s *Server) handleReady(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 1*time.Second)
	defer cancel()
	if err := s.pub.Ping(ctx); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"ready": false, "redis": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ready": true})
}

// handleTraces accepts the SDK's native trace payload and pushes it onto the
// Redis stream. Authentication is intentionally permissive in M1: any
// `Authorization: Bearer ...` header is accepted; project ID is taken from
// the `x-judge-project` header. Real PG-backed key validation lands in M2.
func (s *Server) handleTraces(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, s.cfg.MaxBodyBytes)
	body, err := io.ReadAll(r.Body)
	if err != nil {
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			writeJSON(w, http.StatusRequestEntityTooLarge, map[string]any{"error": "payload too large"})
			return
		}
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "read body: " + err.Error()})
		return
	}
	if !json.Valid(body) {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "invalid json"})
		return
	}

	projectID := strings.TrimSpace(r.Header.Get("x-judge-project"))
	if projectID == "" {
		projectID = s.cfg.DefaultProjectID
	}
	orgID := strings.TrimSpace(r.Header.Get("x-judge-org"))
	if orgID == "" {
		orgID = s.cfg.DefaultOrgID
	}

	id, err := s.pub.PublishTrace(r.Context(), projectID, orgID, body)
	if err != nil {
		s.logger.Error("publish failed", "err", err, "project_id", projectID)
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"error": "queue unavailable"})
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{
		"accepted":   true,
		"stream_id":  id,
		"project_id": projectID,
	})
}

// handleOTLPTraces accepts OTLP/HTTP JSON requests, translates them
// into our internal trace payload, and pushes one Redis-stream message
// per traceId observed. Protobuf encoding is not yet supported — most
// OTel exporters can fall back to JSON via OTEL_EXPORTER_OTLP_PROTOCOL=
// http/json. gRPC ingest is M3.b (separate listener).
func (s *Server) handleOTLPTraces(w http.ResponseWriter, r *http.Request) {
	contentType := r.Header.Get("Content-Type")
	if !strings.Contains(contentType, "json") {
		writeJSON(w, http.StatusUnsupportedMediaType, map[string]any{
			"error": "only application/json is supported in M3; bump OTEL_EXPORTER_OTLP_PROTOCOL=http/json",
		})
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, s.cfg.MaxBodyBytes)
	body, err := io.ReadAll(r.Body)
	if err != nil {
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			writeJSON(w, http.StatusRequestEntityTooLarge, map[string]any{"error": "payload too large"})
			return
		}
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "read body: " + err.Error()})
		return
	}

	traces, err := otlp.Translate(body)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "decode otlp: " + err.Error()})
		return
	}

	projectID := strings.TrimSpace(r.Header.Get("x-judge-project"))
	if projectID == "" {
		projectID = s.cfg.DefaultProjectID
	}
	orgID := strings.TrimSpace(r.Header.Get("x-judge-org"))
	if orgID == "" {
		orgID = s.cfg.DefaultOrgID
	}

	streamIDs := make([]string, 0, len(traces))
	for _, t := range traces {
		payload, err := json.Marshal(t)
		if err != nil {
			s.logger.Warn("otlp marshal", "err", err, "trace_id", t.TraceID)
			continue
		}
		id, err := s.pub.PublishTrace(r.Context(), projectID, orgID, payload)
		if err != nil {
			s.logger.Error("otlp publish", "err", err, "project_id", projectID)
			writeJSON(w, http.StatusServiceUnavailable, map[string]any{"error": "queue unavailable"})
			return
		}
		streamIDs = append(streamIDs, id)
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"accepted":   true,
		"traces":     len(streamIDs),
		"stream_ids": streamIDs,
	})
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
