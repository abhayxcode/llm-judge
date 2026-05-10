// Package otlp translates OTLP/HTTP JSON requests into the internal
// trace payload shape (the same one /v1/traces accepts). Keeping the
// translator behind one function lets us swap in protobuf later
// without touching the HTTP layer.
package otlp

import (
	"encoding/json"
	"fmt"
)

// otlpRequest mirrors the relevant subset of the OTLP/HTTP JSON shape:
// https://github.com/open-telemetry/opentelemetry-proto. We only
// decode the fields we forward, leaving extras to be silently ignored.
type otlpRequest struct {
	ResourceSpans []resourceSpans `json:"resourceSpans"`
}

type resourceSpans struct {
	Resource   resource    `json:"resource"`
	ScopeSpans []scopeSpan `json:"scopeSpans"`
}

type scopeSpan struct {
	Scope scope  `json:"scope"`
	Spans []span `json:"spans"`
}

type scope struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}

type resource struct {
	Attributes []kv `json:"attributes"`
}

type span struct {
	TraceID           string `json:"traceId"`
	SpanID            string `json:"spanId"`
	ParentSpanID      string `json:"parentSpanId"`
	Name              string `json:"name"`
	Kind              int    `json:"kind"`
	StartTimeUnixNano string `json:"startTimeUnixNano"`
	EndTimeUnixNano   string `json:"endTimeUnixNano"`
	Attributes        []kv   `json:"attributes"`
	Status            status `json:"status"`
}

type status struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type kv struct {
	Key   string `json:"key"`
	Value anyVal `json:"value"`
}

// anyVal captures the OTLP "AnyValue" oneOf. We only flatten the
// scalar variants; arrays/maps fall back to their JSON text.
type anyVal struct {
	StringValue *string  `json:"stringValue,omitempty"`
	BoolValue   *bool    `json:"boolValue,omitempty"`
	IntValue    *string  `json:"intValue,omitempty"` // OTLP int → string per proto3 JSON
	DoubleValue *float64 `json:"doubleValue,omitempty"`
	ArrayValue  *struct {
		Values []anyVal `json:"values"`
	} `json:"arrayValue,omitempty"`
	KvlistValue *struct {
		Values []kv `json:"values"`
	} `json:"kvlistValue,omitempty"`
}

func (a anyVal) String() string {
	switch {
	case a.StringValue != nil:
		return *a.StringValue
	case a.BoolValue != nil:
		if *a.BoolValue {
			return "true"
		}
		return "false"
	case a.IntValue != nil:
		return *a.IntValue
	case a.DoubleValue != nil:
		return fmt.Sprintf("%v", *a.DoubleValue)
	default:
		// Arrays/maps: serialize back to JSON. Lossless and parsable.
		b, err := json.Marshal(a)
		if err != nil {
			return ""
		}
		return string(b)
	}
}

// InternalSpan is one element of the internal trace payload's "spans" array.
type InternalSpan struct {
	SpanID     string            `json:"span_id"`
	ParentID   *string           `json:"parent_id"`
	Name       string            `json:"name"`
	StartMs    int64             `json:"start_ms"`
	EndMs      *int64            `json:"end_ms"`
	Status     string            `json:"status"`
	Error      *string           `json:"error,omitempty"`
	Attributes map[string]string `json:"attributes"`
}

// InternalTrace is the payload shape /v1/traces consumes.
type InternalTrace struct {
	TraceID    string            `json:"trace_id"`
	Name       string            `json:"name"`
	StartMs    int64             `json:"start_ms"`
	EndMs      *int64            `json:"end_ms"`
	Status     string            `json:"status"`
	Attributes map[string]string `json:"attributes"`
	Spans      []InternalSpan    `json:"spans"`
	SDKLang    string            `json:"sdk_lang,omitempty"`
	SDKVersion string            `json:"sdk_version,omitempty"`
}

// Translate walks an OTLP/HTTP JSON body and returns one InternalTrace
// per traceId observed. Resource attributes are merged into each
// trace's top-level attributes (service.name etc).
func Translate(body []byte) ([]InternalTrace, error) {
	var req otlpRequest
	if err := json.Unmarshal(body, &req); err != nil {
		return nil, fmt.Errorf("decode otlp: %w", err)
	}

	byTrace := map[string]*InternalTrace{}
	for _, rs := range req.ResourceSpans {
		resAttrs := flattenAttrs(rs.Resource.Attributes)
		for _, ss := range rs.ScopeSpans {
			for _, sp := range ss.Spans {
				if sp.TraceID == "" || sp.SpanID == "" {
					continue
				}
				it, ok := byTrace[sp.TraceID]
				if !ok {
					it = &InternalTrace{
						TraceID:    sp.TraceID,
						Name:       sp.Name,
						Status:     "ok",
						Attributes: copyMap(resAttrs),
						Spans:      []InternalSpan{},
					}
					it.Attributes["otel.scope.name"] = ss.Scope.Name
					byTrace[sp.TraceID] = it
				}

				start := unixNanoToMs(sp.StartTimeUnixNano)
				endMs := unixNanoToMs(sp.EndTimeUnixNano)
				var endPtr *int64
				if endMs > 0 {
					endPtr = &endMs
				}

				spanStatus := "ok"
				var spanErr *string
				if sp.Status.Code == 2 { // STATUS_CODE_ERROR
					spanStatus = "error"
					if sp.Status.Message != "" {
						msg := sp.Status.Message
						spanErr = &msg
					}
					it.Status = "error"
				}

				var parent *string
				if sp.ParentSpanID != "" {
					p := sp.ParentSpanID
					parent = &p
				}

				attrs := flattenAttrs(sp.Attributes)
				is := InternalSpan{
					SpanID:     sp.SpanID,
					ParentID:   parent,
					Name:       sp.Name,
					StartMs:    start,
					EndMs:      endPtr,
					Status:     spanStatus,
					Error:      spanErr,
					Attributes: attrs,
				}
				it.Spans = append(it.Spans, is)

				// First span we see (by start time) seeds the trace's
				// top-level start_ms / name.
				if it.StartMs == 0 || start < it.StartMs {
					it.StartMs = start
				}
				if endPtr != nil {
					if it.EndMs == nil || *endPtr > *it.EndMs {
						it.EndMs = endPtr
					}
				}
				// Pick the root span's name (parent_id == nil) when we see one.
				if parent == nil {
					it.Name = sp.Name
				}
			}
		}
	}

	out := make([]InternalTrace, 0, len(byTrace))
	for _, it := range byTrace {
		out = append(out, *it)
	}
	return out, nil
}

func flattenAttrs(in []kv) map[string]string {
	out := make(map[string]string, len(in))
	for _, v := range in {
		out[v.Key] = v.Value.String()
	}
	return out
}

func copyMap(m map[string]string) map[string]string {
	out := make(map[string]string, len(m))
	for k, v := range m {
		out[k] = v
	}
	return out
}

func unixNanoToMs(s string) int64 {
	if s == "" {
		return 0
	}
	// nanos as a string per proto3 JSON. Parse without strconv to avoid
	// allocating an Int — manual loop is faster and simpler here.
	var n int64
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c < '0' || c > '9' {
			return 0
		}
		n = n*10 + int64(c-'0')
	}
	return n / 1_000_000
}
