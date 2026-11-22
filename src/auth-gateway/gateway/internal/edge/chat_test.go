package edge

import (
	"bytes"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
	"github.com/aleshka5/open-storage/auth-gateway/internal/session"
)

// chatConfig is the apex host with POST /api/chat served in this process instead
// of proxied to the model: the route the owl uses.
const chatConfig = `
listen: ":8080"
public_origin: "https://filenkov.store"
idp:
  issuer: "https://id.filenkov.store/realms/filenkov"
  client_id: gateway
  client_secret: "env:IDP_CLIENT_SECRET"
session:
  key: "env:GATEWAY_SESSION_KEY"
admin:
  client_id: gateway-admin
  client_secret: "env:IDP_ADMIN_SECRET"
services: [storage]
defaults:
  timeouts: { connect: 1s, read_header: 5s, response_header: 2s, idle: 30s }
  rate_limit: { requests: 1000, per: 1m }
upstreams:
  resume: "resume:80"
hosts:
  - host: filenkov.store
    upstream: resume
    routes:
      - { path: /api/chat, methods: [POST], chat: true, policy: public }
      - { path: /admin/**, admin: true, policy: admin }
      - { path: /**, policy: public }
`

type chatHarness struct {
	server  *Server
	handler http.Handler
	logs    *bytes.Buffer
}

func newChatHarness(t *testing.T, chat http.Handler) *chatHarness {
	t.Helper()
	file, err := config.Parse([]byte(chatConfig))
	if err != nil {
		t.Fatalf("config: %v", err)
	}
	env := map[string]string{
		"IDP_CLIENT_SECRET":   "idp",
		"GATEWAY_SESSION_KEY": "0123456789abcdef0123456789abcdef",
		"IDP_ADMIN_SECRET":    "admin",
	}
	if err := file.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err != nil {
		t.Fatalf("env: %v", err)
	}
	sealer, err := session.NewSealer(env["GATEWAY_SESSION_KEY"], ".filenkov.store", 5*time.Minute, 168*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	logs := &bytes.Buffer{}
	server, err := New(Config{
		File:     file,
		Verifier: &fakeVerifier{tokens: map[string]*oidc.Identity{}},
		Sealer:   sealer,
		Chat:     chat,
		Logger:   slog.New(slog.NewJSONHandler(logs, &slog.HandlerOptions{Level: slog.LevelDebug})),
	})
	if err != nil {
		t.Fatalf("edge: %v", err)
	}
	return &chatHarness{server: server, handler: server.Handler(), logs: logs}
}

func (h *chatHarness) do(method, path, body string, headers map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Host = "filenkov.store"
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.handler.ServeHTTP(rec, req)
	return rec
}

func streamHandler(chunks ...string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		for _, c := range chunks {
			_, _ = w.Write([]byte(c))
			if f, ok := w.(http.Flusher); ok {
				f.Flush()
			}
		}
	})
}

// The chat is served in this process, so it never reaches the proxy's response
// hook — and still has to answer with the same headers as every other route.
func TestChatRouteCarriesTheSecurityHeaders(t *testing.T) {
	h := newChatHarness(t, streamHandler(`data: {"delta":"hi"}`+"\n\n", "data: [DONE]\n\n"))

	rec := h.do(http.MethodPost, "/api/chat", `{"question":"hi"}`, nil)

	if rec.Code != http.StatusOK {
		t.Fatalf("status %d: %s", rec.Code, rec.Body.String())
	}
	if got := rec.Header().Get("Content-Type"); got != "text/event-stream" {
		t.Fatalf("content type %q", got)
	}
	if got := rec.Header().Get("X-Frame-Options"); got != "DENY" {
		t.Fatalf("x-frame-options %q", got)
	}
	if got := rec.Header().Get("X-Content-Type-Options"); got != "nosniff" {
		t.Fatalf("nosniff %q", got)
	}
	if !strings.HasSuffix(rec.Body.String(), "data: [DONE]\n\n") {
		t.Fatalf("body %q", rec.Body.String())
	}
}

// The policy is the route's, not the handler's: with no model configured the
// route still exists and says so instead of 404.
func TestChatRouteWithoutAHandlerIsA503(t *testing.T) {
	h := newChatHarness(t, nil)

	rec := h.do(http.MethodPost, "/api/chat", `{"question":"hi"}`, nil)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", rec.Code)
	}
	if rec.Body.String() != `{"error":"chat_unavailable"}` {
		t.Fatalf("body %q", rec.Body.String())
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("content type %q", ct)
	}
	if strings.Contains(rec.Body.String(), "data:") {
		t.Fatalf("stream started: %q", rec.Body.String())
	}
}

// The method allow-list is the route's: a GET on /api/chat falls through to the
// catch-all, which is the page, not the chat.
func TestChatRouteIsPostOnly(t *testing.T) {
	h := newChatHarness(t, streamHandler("data: [DONE]\n\n"))

	rec := h.do(http.MethodGet, "/api/chat", "", nil)

	if rec.Code == http.StatusOK && strings.Contains(rec.Body.String(), "[DONE]") {
		t.Fatalf("a GET reached the chat handler: %d %s", rec.Code, rec.Body.String())
	}
}

// The verified identity reaches the handler through the context, and the edge
// keeps its promise that the client's own identity headers never do.
func TestChatRoutePassesOnlyTheVerifiedIdentity(t *testing.T) {
	var got *oidc.Identity
	h := newChatHarness(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got = oidc.FromContext(r.Context())
		w.WriteHeader(http.StatusOK)
	}))
	tok := "tok-chat"
	h.server.verifier.(*fakeVerifier).tokens[tok] = &oidc.Identity{Subject: "u-9", Email: "real@example.com"}

	req := httptest.NewRequest(http.MethodPost, "/api/chat", strings.NewReader(`{"question":"hi"}`))
	req.Host = "filenkov.store"
	req.Header.Set("X-Auth-Subject", "attacker")
	req.AddCookie(&http.Cookie{Name: session.NameAccess, Value: tok})
	h.handler.ServeHTTP(httptest.NewRecorder(), req)

	if got == nil || got.Subject != "u-9" {
		t.Fatalf("identity %+v", got)
	}
}

// A fixture guard: the chat config must still compile the route it tests.
func TestChatConfigCompilesTheRoute(t *testing.T) {
	h := newChatHarness(t, nil)
	_, route, ok := h.server.router.Match("filenkov.store", http.MethodPost, "/api/chat")
	if !ok || route == nil || !route.Chat {
		t.Fatalf("route %+v ok=%v", route, ok)
	}
	if route.Upstream == nil || route.Upstream.Host != "resume:80" {
		// The route still inherits the host upstream for anything else it might
		// serve; what matters is that the chat branch runs before the proxy.
		t.Fatalf("unexpected upstream %v", route.Upstream)
	}
}
