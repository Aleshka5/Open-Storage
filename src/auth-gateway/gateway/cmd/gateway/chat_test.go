package main

import (
	"bytes"
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
)

const chatConfig = `
listen: ":8080"
public_origin: "https://filenkov.store"
idp:
  issuer: "https://id.filenkov.store/realms/filenkov"
  client_id: gateway
  client_secret: "env:IDP_CLIENT_SECRET"
session:
  key: "env:GATEWAY_SESSION_KEY"
services: [storage]
upstreams:
  resume: "resume:80"
hosts:
  - host: filenkov.store
    upstream: resume
    routes:
      - { path: /**, policy: public }
`

func quietLog() *slog.Logger {
	return slog.New(slog.NewTextHandler(&bytes.Buffer{}, nil))
}

func clearLLMEnv(t *testing.T) {
	t.Helper()
	for _, name := range []string{
		"LLM_HOST", "LLM_MODEL", "LLM_REASONING_EFFORT", "LLM_API_KEY",
		"MLFLOW_TRACING_ENDPOINT", "MLFLOW_EXPERIMENT_ID",
	} {
		t.Setenv(name, "")
	}
}

func parseChat(t *testing.T, extra string) *config.File {
	t.Helper()
	file, err := config.Parse([]byte(chatConfig + extra))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	env := map[string]string{
		"IDP_CLIENT_SECRET":   "idp",
		"GATEWAY_SESSION_KEY": "0123456789abcdef0123456789abcdef",
	}
	if err := file.ResolveEnv(func(k string) (string, bool) {
		v, ok := env[k]
		return v, ok
	}); err != nil {
		t.Fatalf("env: %v", err)
	}
	return file
}

func assertChatUnavailable(t *testing.T, h http.Handler) {
	t.Helper()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/api/chat", strings.NewReader(`{"question":"hi"}`))
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", rec.Code)
	}
	if rec.Body.String() != `{"error":"chat_unavailable"}` {
		t.Fatalf("body %q", rec.Body.String())
	}
	ct := rec.Header().Get("Content-Type")
	if ct != "application/json" {
		t.Fatalf("content type %q", ct)
	}
	if strings.Contains(rec.Body.String(), "data:") || strings.Contains(ct, "event-stream") {
		t.Fatalf("stream started: %q", rec.Body.String())
	}
}

func TestMissingLLMBlockAnswersChatUnavailable(t *testing.T) {
	clearLLMEnv(t)
	h, shutdown, err := newChat(context.Background(), parseChat(t, ""), quietLog())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = shutdown(context.Background()) })
	assertChatUnavailable(t, h)
}

func TestMissingLLMKeyAnswersChatUnavailable(t *testing.T) {
	clearLLMEnv(t)
	h, shutdown, err := newChat(context.Background(), parseChat(t, `
llm:
  host: "http://127.0.0.1:9/v1"
  model: m
`), quietLog())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = shutdown(context.Background()) })
	assertChatUnavailable(t, h)
}
