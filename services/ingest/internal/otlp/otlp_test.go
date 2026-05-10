package otlp_test

import (
	"testing"

	"github.com/abhayxcode/llm-judge/services/ingest/internal/otlp"
)

func TestTranslate_BasicSpanShape(t *testing.T) {
	body := []byte(`{
		"resourceSpans": [{
			"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "demo-app"}}]},
			"scopeSpans": [{
				"scope": {"name": "judge"},
				"spans": [{
					"traceId": "abc123",
					"spanId": "s1",
					"name": "rag_chain",
					"startTimeUnixNano": "1715299200000000000",
					"endTimeUnixNano":   "1715299201000000000",
					"attributes": [
						{"key": "gen_ai.system", "value": {"stringValue": "openai"}},
						{"key": "gen_ai.usage.input_tokens", "value": {"intValue": "10"}}
					],
					"status": {"code": 1}
				}]
			}]
		}]
	}`)

	traces, err := otlp.Translate(body)
	if err != nil {
		t.Fatalf("translate: %v", err)
	}
	if len(traces) != 1 {
		t.Fatalf("want 1 trace, got %d", len(traces))
	}
	tr := traces[0]
	if tr.TraceID != "abc123" {
		t.Errorf("trace_id = %s", tr.TraceID)
	}
	if tr.Attributes["service.name"] != "demo-app" {
		t.Errorf("service.name not propagated: %#v", tr.Attributes)
	}
	if tr.StartMs != 1715299200000 {
		t.Errorf("start_ms = %d", tr.StartMs)
	}
	if len(tr.Spans) != 1 {
		t.Fatalf("want 1 span, got %d", len(tr.Spans))
	}
	sp := tr.Spans[0]
	if sp.Name != "rag_chain" || sp.SpanID != "s1" {
		t.Errorf("span shape wrong: %+v", sp)
	}
	if sp.Attributes["gen_ai.system"] != "openai" {
		t.Errorf("gen_ai.system: %v", sp.Attributes)
	}
	if sp.Attributes["gen_ai.usage.input_tokens"] != "10" {
		t.Errorf("int value not coerced to string: %v", sp.Attributes)
	}
}

func TestTranslate_GroupsByTraceId(t *testing.T) {
	body := []byte(`{
		"resourceSpans": [{
			"resource": {"attributes": []},
			"scopeSpans": [{
				"spans": [
					{"traceId": "T1", "spanId": "a", "name": "root", "startTimeUnixNano": "1", "endTimeUnixNano": "2", "status": {"code": 1}},
					{"traceId": "T1", "spanId": "b", "parentSpanId": "a", "name": "child", "startTimeUnixNano": "1", "endTimeUnixNano": "2", "status": {"code": 1}},
					{"traceId": "T2", "spanId": "c", "name": "other", "startTimeUnixNano": "1", "endTimeUnixNano": "2", "status": {"code": 1}}
				]
			}]
		}]
	}`)
	traces, err := otlp.Translate(body)
	if err != nil {
		t.Fatalf("translate: %v", err)
	}
	if len(traces) != 2 {
		t.Fatalf("want 2 traces, got %d", len(traces))
	}
}

func TestTranslate_ErrorStatusFlagsTrace(t *testing.T) {
	body := []byte(`{
		"resourceSpans": [{
			"scopeSpans": [{
				"spans": [{
					"traceId": "T", "spanId": "x", "name": "boom",
					"startTimeUnixNano": "1", "endTimeUnixNano": "2",
					"status": {"code": 2, "message": "bang"}
				}]
			}]
		}]
	}`)
	traces, err := otlp.Translate(body)
	if err != nil {
		t.Fatalf("translate: %v", err)
	}
	if traces[0].Status != "error" {
		t.Errorf("status = %s", traces[0].Status)
	}
	if traces[0].Spans[0].Error == nil || *traces[0].Spans[0].Error != "bang" {
		t.Errorf("error msg not propagated: %+v", traces[0].Spans[0].Error)
	}
}

func TestTranslate_BadJSON(t *testing.T) {
	if _, err := otlp.Translate([]byte("not json")); err == nil {
		t.Fatal("want error on bad json")
	}
}

func TestTranslate_EmptyResourceSpans(t *testing.T) {
	traces, err := otlp.Translate([]byte(`{"resourceSpans": []}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(traces) != 0 {
		t.Errorf("want 0 traces, got %d", len(traces))
	}
}
