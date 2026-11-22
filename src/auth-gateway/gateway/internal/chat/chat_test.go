package chat

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/aleshka5/open-storage/auth-gateway/internal/llm"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
)

// streamUpstream is a chat-completions endpoint that answers one delta and stops.
func streamUpstream(t *testing.T, seenStatus *int, seenHeaders *http.Header, seenBody *map[string]any) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/chat/completions" {
			t.Errorf("path %q", r.URL.Path)
		}
		if seenStatus != nil {
			*seenStatus = http.StatusOK
		}
		if seenHeaders != nil {
			*seenHeaders = r.Header.Clone()
		}
		if seenBody != nil {
			raw, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(raw, seenBody)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = io.WriteString(w, `data: {"choices":[{"delta":{"content":"He leads agents."}}]}`+"\n\n")
		_, _ = io.WriteString(w, "data: [DONE]\n\n")
	}))
}

func newClient(t *testing.T, url string) *llm.Client {
	t.Helper()
	c, err := llm.New(llm.Config{Host: url + "/v1", APIKey: "k-1", Model: "m"})
	if err != nil {
		t.Fatal(err)
	}
	return c
}

func TestStreamsAnAnswerAndTerminates(t *testing.T) {
	upstream := streamUpstream(t, nil, nil, nil)
	defer upstream.Close()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/api/chat", strings.NewReader(`{"question":"what?"}`))
	New(newClient(t, upstream.URL), nil).ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status %d: %s", rec.Code, rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); ct != "text/event-stream" {
		t.Fatalf("content type %q", ct)
	}
	body := rec.Body.String()
	if !strings.Contains(body, `"delta":"He leads agents."`) {
		t.Fatalf("missing delta: %q", body)
	}
	if !strings.HasSuffix(body, "data: [DONE]\n\n") {
		t.Fatalf("missing terminator: %q", body)
	}
}

func TestPassesTheKeyAndThePromptUpstream(t *testing.T) {
	var headers http.Header
	var body map[string]any
	upstream := streamUpstream(t, nil, &headers, &body)
	defer upstream.Close()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/api/chat", strings.NewReader(`{"question":"what?"}`))
	New(newClient(t, upstream.URL), nil).ServeHTTP(rec, req)

	if got := headers.Get("Authorization"); got != "Bearer k-1" {
		t.Fatalf("authorization %q", got)
	}
	msgs, _ := body["messages"].([]any)
	if len(msgs) != 2 {
		t.Fatalf("messages %v", body["messages"])
	}
	// The system prompt is the owner's, not the caller's.
	system, _ := msgs[0].(map[string]any)
	if !strings.Contains(system["content"].(string), "Alexey") {
		t.Fatalf("system prompt is not the owner's: %v", system)
	}
}

func TestNoConfigIsA503(t *testing.T) {
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/api/chat", strings.NewReader(`{"question":"hi"}`))
	New(nil, nil).ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "chat is not configured") {
		t.Fatalf("body %q", rec.Body.String())
	}
}

func TestRejectsAnEmptyOrOversizedQuestion(t *testing.T) {
	upstream := streamUpstream(t, nil, nil, nil)
	defer upstream.Close()
	h := New(newClient(t, upstream.URL), nil)

	for _, q := range []string{`{"question":"   "}`, `{"question":"` + strings.Repeat("a", llm.MaxQuestionRunes+1) + `"}`} {
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/api/chat", strings.NewReader(q)))
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("status %d for %q", rec.Code, q[:40])
		}
	}
}

// The identity the handler attributes a question to comes from the verified
// cookie the edge put in the context, never from a header the client wrote.
func TestIdentityComesFromTheContextNotTheRequest(t *testing.T) {
	var body map[string]any
	upstream := streamUpstream(t, nil, nil, &body)
	defer upstream.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/chat", strings.NewReader(`{"question":"hi"}`))
	req.Header.Set("X-Auth-Subject", "attacker")
	req.Header.Set("X-Auth-Email", "attacker@example.com")
	req = req.WithContext(oidc.WithIdentity(req.Context(), &oidc.Identity{Subject: "u-1", Email: "real@example.com"}))

	New(newClient(t, upstream.URL), nil).ServeHTTP(httptest.NewRecorder(), req)

	meta, _ := body["metadata"].(map[string]any)
	if meta["user_id"] != "u-1" || meta["user_email"] != "real@example.com" {
		t.Fatalf("metadata %v", meta)
	}
}

func TestSessionIDIsOpaqueOrFresh(t *testing.T) {
	if got := sessionID(httptest.NewRequest(http.MethodPost, "/", nil)); len(got) != 36 {
		t.Fatalf("want a generated uuid, got %q", got)
	}
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req.Header.Set(sessionHeader, "abc-123_X.y")
	if got := sessionID(req); got != "abc-123_X.y" {
		t.Fatalf("kept %q", got)
	}
	// Anything that could forge a log line is replaced.
	req.Header.Set(sessionHeader, "abc 123")
	if got, err := uuid.Parse(sessionID(req)); err != nil || got.Version() != 4 {
		t.Fatalf("a space should produce a fresh uuid, got %q", sessionID(req))
	}
}
