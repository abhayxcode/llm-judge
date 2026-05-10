package server

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/abhayxcode/llm-judge/services/ingest/internal/config"
)

type fakePublisher struct {
	mu        sync.Mutex
	published []publishedRecord
	pingErr   error
	publishErr error
}

type publishedRecord struct {
	projectID string
	orgID     string
	payload   string
}

func (f *fakePublisher) PublishTrace(_ context.Context, projectID, orgID string, payload []byte) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.publishErr != nil {
		return "", f.publishErr
	}
	f.published = append(f.published, publishedRecord{
		projectID: projectID, orgID: orgID, payload: string(payload),
	})
	return "stream-id-1", nil
}

func (f *fakePublisher) Ping(_ context.Context) error { return f.pingErr }

func newTestServer(t *testing.T, pub *fakePublisher) *Server {
	t.Helper()
	cfg := &config.Config{
		ListenAddr:       ":0",
		Env:              "test",
		MaxBodyBytes:     1024 * 1024,
		DefaultProjectID: "demo",
		DefaultOrgID:     "default",
	}
	return NewWithPublisher(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), pub)
}

func TestHealth(t *testing.T) {
	t.Parallel()
	s := newTestServer(t, &fakePublisher{})
	rr := httptest.NewRecorder()
	s.Routes().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/health", nil))

	if rr.Code != http.StatusOK {
		t.Fatalf("want 200, got %d", rr.Code)
	}
	if !strings.Contains(rr.Body.String(), `"status":"ok"`) {
		t.Fatalf("unexpected body: %s", rr.Body.String())
	}
}

func TestReadyOK(t *testing.T) {
	t.Parallel()
	s := newTestServer(t, &fakePublisher{})
	rr := httptest.NewRecorder()
	s.Routes().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/ready", nil))
	if rr.Code != http.StatusOK {
		t.Fatalf("want 200, got %d", rr.Code)
	}
}

func TestReadyFailsWhenRedisDown(t *testing.T) {
	t.Parallel()
	s := newTestServer(t, &fakePublisher{pingErr: errors.New("connect refused")})
	rr := httptest.NewRecorder()
	s.Routes().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/ready", nil))
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("want 503, got %d", rr.Code)
	}
}

func TestTracesPublishesPayload(t *testing.T) {
	t.Parallel()
	pub := &fakePublisher{}
	s := newTestServer(t, pub)

	body := `{"trace_id":"abc","name":"hello","spans":[]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer ignored")
	req.Header.Set("x-judge-project", "demo")
	rr := httptest.NewRecorder()
	s.Routes().ServeHTTP(rr, req)

	if rr.Code != http.StatusAccepted {
		t.Fatalf("want 202, got %d (%s)", rr.Code, rr.Body.String())
	}
	if len(pub.published) != 1 {
		t.Fatalf("expected 1 publish, got %d", len(pub.published))
	}
	if pub.published[0].projectID != "demo" {
		t.Fatalf("project_id mismatch: %q", pub.published[0].projectID)
	}
	if pub.published[0].payload != body {
		t.Fatalf("payload mismatch")
	}
}

func TestTracesUsesDefaultProject(t *testing.T) {
	t.Parallel()
	pub := &fakePublisher{}
	s := newTestServer(t, pub)
	rr := httptest.NewRecorder()
	s.Routes().ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader(`{}`)))
	if rr.Code != http.StatusAccepted {
		t.Fatalf("want 202, got %d", rr.Code)
	}
	if pub.published[0].projectID != "demo" {
		t.Fatalf("expected default project 'demo', got %q", pub.published[0].projectID)
	}
}

func TestTracesRejectsInvalidJSON(t *testing.T) {
	t.Parallel()
	s := newTestServer(t, &fakePublisher{})
	rr := httptest.NewRecorder()
	s.Routes().ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader("not json")))
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d", rr.Code)
	}
}

func TestTracesReturns503WhenQueueDown(t *testing.T) {
	t.Parallel()
	s := newTestServer(t, &fakePublisher{publishErr: errors.New("redis dead")})
	rr := httptest.NewRecorder()
	s.Routes().ServeHTTP(rr, httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader(`{}`)))
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("want 503, got %d", rr.Code)
	}
}

func TestUnknownRouteIs404(t *testing.T) {
	t.Parallel()
	s := newTestServer(t, &fakePublisher{})
	rr := httptest.NewRecorder()
	s.Routes().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/nope", nil))
	if rr.Code != http.StatusNotFound {
		t.Fatalf("want 404, got %d", rr.Code)
	}
}
