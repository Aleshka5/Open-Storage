package edge

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
	"github.com/aleshka5/open-storage/auth-gateway/internal/session"
)

const yamlConfig = `
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
services: [storage, image, audio]
defaults:
  timeouts: { connect: 1s, read_header: 5s, response_header: 2s, idle: 30s }
  rate_limit: { requests: 1000, per: 1m }
upstreams:
  resume: "resume:80"
  storage: "app:8000"
  image: "qwen-image:8000"
  audio: "audio-api:8000"
  audio_web: "frontend:80"
  idp: "idp:8080"
hosts:
  - host: filenkov.store
    upstream: resume
    routes:
      - { path: /auth/**, bff: true }
      - { path: /admin/**, admin: true, policy: admin }
      - { path: /api/**, methods: [POST], upstream: storage, policy: public,
          inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" } }
      - { path: /users/**, policy: deny }
      - { path: /**, policy: public }
  - host: storage.filenkov.store
    upstream: storage
    service: storage
    routes:
      - { path: /health, policy: public }
      - { path: /**, policy: "service(storage, family, admin)" }
  - host: image.filenkov.store
    upstream: image
    service: image
    routes:
      - { path: /healthz, policy: public }
      - { path: /**, policy: "service(image, family, admin)" }
  - host: audio.filenkov.store
    upstream: audio_web
    service: audio
    frame: self
    permissions_policy: "camera=(), microphone=(self), geolocation=()"
    timeouts: { response_header: 500ms }
    routes:
      - { path: /api/**, upstream: audio, policy: "service(audio, family, admin)" }
      - { path: /**, policy: session }
  - host: id.filenkov.store
    upstream: idp
    identity: passthrough
    frame: self
    routes:
      - { path: /**, policy: public }
`

type fakeVerifier struct {
	tokens map[string]*oidc.Identity
	fail   error
}

func (f *fakeVerifier) Verify(_ context.Context, raw string) (*oidc.Identity, error) {
	if f.fail != nil {
		return nil, f.fail
	}
	if id, ok := f.tokens[raw]; ok {
		return id, nil
	}
	return nil, errors.New("unknown token")
}

func (f *fakeVerifier) Ready() error { return nil }

type fakeRefresher struct {
	token  string
	status int
	calls  int
}

func (f *fakeRefresher) Refresh(w http.ResponseWriter, r *http.Request) (string, int) {
	f.calls++
	if f.token != "" {
		http.SetCookie(w, &http.Cookie{Name: "refreshed", Value: "1"})
	}
	return f.token, f.status
}

type harness struct {
	server   *Server
	verifier *fakeVerifier
	refresh  *fakeRefresher
	bff      *httptest.Server
	upstream *httptest.Server
	seen     chan *http.Request
	upBody   string
	upStatus int
	upDelay  time.Duration
	sealTok  func(*oidc.Identity) string
	handler  http.Handler
}

func newHarness(t *testing.T) *harness {
	t.Helper()
	h := &harness{
		verifier: &fakeVerifier{tokens: map[string]*oidc.Identity{}},
		refresh:  &fakeRefresher{},
		seen:     make(chan *http.Request, 16),
		upBody:   "upstream",
		upStatus: http.StatusOK,
	}
	h.upstream = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case h.seen <- r.Clone(context.Background()):
		default:
		}
		if r.Header.Get("Upgrade") == "websocket" {
			conn, rw, err := w.(http.Hijacker).Hijack()
			if err != nil {
				t.Errorf("hijack: %v", err)
				return
			}
			_, _ = rw.WriteString("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
			_ = rw.Flush()
			_ = conn.Close()
			return
		}
		if h.upDelay > 0 {
			time.Sleep(h.upDelay)
		}
		w.WriteHeader(h.upStatus)
		_, _ = w.Write([]byte(h.upBody))
	}))
	t.Cleanup(h.upstream.Close)

	raw := strings.Replace(yamlConfig, `resume: "resume:80"`, `resume: "`+h.upstream.URL+`"`, 1)
	raw = strings.Replace(raw, `storage: "app:8000"`, `storage: "`+h.upstream.URL+`"`, 1)
	raw = strings.Replace(raw, `image: "qwen-image:8000"`, `image: "`+h.upstream.URL+`"`, 1)
	raw = strings.Replace(raw, `audio: "audio-api:8000"`, `audio: "`+h.upstream.URL+`"`, 1)
	raw = strings.Replace(raw, `audio_web: "frontend:80"`, `audio_web: "`+h.upstream.URL+`"`, 1)
	file, err := config.Parse([]byte(raw))
	if err != nil {
		t.Fatalf("config: %v", err)
	}
	env := map[string]string{
		"IDP_CLIENT_SECRET":   "idp",
		"GATEWAY_SESSION_KEY": "0123456789abcdef0123456789abcdef",
		"IDP_ADMIN_SECRET":    "admin",
		"SWITCH_TOKEN":        "switch-secret",
	}
	if err := file.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err != nil {
		t.Fatalf("env: %v", err)
	}
	sealer, err := session.NewSealer(env["GATEWAY_SESSION_KEY"], ".filenkov.store", 5*time.Minute, 168*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	var logs bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&logs, &slog.HandlerOptions{Level: slog.LevelDebug}))
	h.bff = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("bff:" + r.URL.Path))
	}))
	t.Cleanup(h.bff.Close)

	server, err := New(Config{
		File:      file,
		Verifier:  h.verifier,
		Sealer:    sealer,
		Refresher: h.refresh,
		BFF:       http.RedirectHandler(h.bff.URL+"/auth/login", http.StatusFound),
		Admin: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			id := oidc.FromContext(r.Context())
			if id == nil {
				t.Error("admin handler got no identity")
			}
			_, _ = w.Write([]byte("admin:" + id.Subject))
		}),
		Logger: logger,
	})
	if err != nil {
		t.Fatalf("edge: %v", err)
	}
	h.server = server
	h.handler = server.Handler()
	h.sealTok = func(id *oidc.Identity) string {
		tok := "tok-" + id.Subject
		h.verifier.tokens[tok] = id
		return tok
	}
	t.Cleanup(func() {
		if t.Failed() {
			t.Logf("logs: %s", logs.String())
		}
	})
	return h
}

func (h *harness) do(t *testing.T, host, method, path, token string, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	req.Host = host
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	if token != "" {
		req.AddCookie(&http.Cookie{Name: session.NameAccess, Value: token})
	}
	rec := httptest.NewRecorder()
	h.handler.ServeHTTP(rec, req)
	return rec
}

func TestUnknownHostAndRoute(t *testing.T) {
	h := newHarness(t)
	rec := h.do(t, "nope.example", "GET", "/", "", nil)
	if rec.Code != http.StatusNotFound || !strings.Contains(rec.Body.String(), `"not_found"`) {
		t.Fatalf("unknown host = %d %s", rec.Code, rec.Body.String())
	}
	rec = h.do(t, "filenkov.store", "GET", "/users/me", "", nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("deny route = %d", rec.Code)
	}
}

func TestAnonymousRedirectVersusJSON(t *testing.T) {
	h := newHarness(t)
	rec := h.do(t, "storage.filenkov.store", "GET", "/files", "", nil)
	if rec.Code != http.StatusFound {
		t.Fatalf("browser navigation = %d", rec.Code)
	}
	loc := rec.Header().Get("Location")
	if !strings.HasPrefix(loc, "https://filenkov.store/auth/login?return_to=") {
		t.Fatalf("Location = %q", loc)
	}
	if !strings.Contains(loc, "storage.filenkov.store") {
		t.Fatalf("return_to lost the host: %q", loc)
	}
	rec = h.do(t, "audio.filenkov.store", "GET", "/api/voice", "", map[string]string{"Accept": "application/json"})
	if rec.Code != http.StatusUnauthorized || !strings.Contains(rec.Body.String(), `"unauthorized"`) {
		t.Fatalf("api client = %d %s", rec.Code, rec.Body.String())
	}
}

func TestRolesDecideAccess(t *testing.T) {
	h := newHarness(t)
	stranger := &oidc.Identity{Subject: "s1"}
	family := &oidc.Identity{Subject: "s2", Roles: []string{"svc:storage:family"}}
	admin := &oidc.Identity{Subject: "s3", Roles: []string{"admin", "svc:image:admin"}}
	blocked := &oidc.Identity{Subject: "s4", Roles: []string{"svc:audio:blocked"}}

	if rec := h.do(t, "storage.filenkov.store", "GET", "/files", h.sealTok(stranger), nil); rec.Code != http.StatusForbidden {
		t.Fatalf("stranger = %d", rec.Code)
	}
	if rec := h.do(t, "storage.filenkov.store", "GET", "/files", h.sealTok(family), nil); rec.Code != http.StatusOK {
		t.Fatalf("family = %d", rec.Code)
	}
	if rec := h.do(t, "image.filenkov.store", "GET", "/generate", h.sealTok(family), nil); rec.Code != http.StatusForbidden {
		t.Fatalf("family on image = %d", rec.Code)
	}
	if rec := h.do(t, "image.filenkov.store", "GET", "/generate", h.sealTok(admin), nil); rec.Code != http.StatusOK {
		t.Fatalf("image admin = %d", rec.Code)
	}
	// The audio UI is a `session` route on a host that names its service, so a
	// blocked account is closed even though the account itself is enabled.
	rec := h.do(t, "audio.filenkov.store", "GET", "/", h.sealTok(blocked), nil)
	if rec.Code != http.StatusForbidden || !strings.Contains(rec.Body.String(), `"blocked"`) {
		t.Fatalf("blocked = %d %s", rec.Code, rec.Body.String())
	}
}

func TestIdentityIsStrippedAndInjected(t *testing.T) {
	h := newHarness(t)
	id := &oidc.Identity{Subject: "sub-1", Email: "ada@example.com", Name: "Ada", SID: "sid-1", Roles: []string{"svc:storage:family", "admin"}}
	token := h.sealTok(id)
	rec := h.do(t, "storage.filenkov.store", "GET", "/files", token, map[string]string{
		"X-Auth-Subject":  "forged",
		"X-User-Id":       "forged",
		"X-Storage-Role":  "ADMIN",
		"X-Forwarded-For": "203.0.113.9",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	seen := <-h.seen
	for _, name := range []string{"X-User-Id", "X-Storage-Role"} {
		if got := seen.Header.Get(name); got != "" {
			t.Fatalf("%s leaked upstream: %q", name, got)
		}
	}
	if got := seen.Header.Get("X-Auth-Subject"); got != "sub-1" {
		t.Fatalf("X-Auth-Subject = %q", got)
	}
	if got := seen.Header.Get("X-Auth-Roles"); got != "admin svc:storage:family" {
		t.Fatalf("X-Auth-Roles = %q", got)
	}
	if got := seen.Header.Get("X-Auth-Session"); got != "sid-1" {
		t.Fatalf("X-Auth-Session = %q", got)
	}
	if got := seen.Header.Get("Authorization"); got != "Bearer "+token {
		t.Fatalf("Authorization = %q", got)
	}
	if got := seen.Header.Get("X-Forwarded-Proto"); got != "https" {
		t.Fatalf("X-Forwarded-Proto = %q", got)
	}
	if got := seen.Header.Get("X-Forwarded-Host"); got != "storage.filenkov.store" {
		t.Fatalf("X-Forwarded-Host = %q", got)
	}
}

func TestConfigHeaderBeatsClientHeader(t *testing.T) {
	h := newHarness(t)
	rec := h.do(t, "filenkov.store", "POST", "/api/switch", "", map[string]string{"X-Service-Token": "client-supplied"})
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	seen := <-h.seen
	if got := seen.Header.Get("X-Service-Token"); got != "switch-secret" {
		t.Fatalf("X-Service-Token = %q, want the config value", got)
	}
}

func TestAnonGetsNoIdentityHeaders(t *testing.T) {
	h := newHarness(t)
	if rec := h.do(t, "storage.filenkov.store", "GET", "/health", "", nil); rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	seen := <-h.seen
	if got := seen.Header.Get("X-Auth-Subject"); got != "" {
		t.Fatalf("anonymous request carried X-Auth-Subject = %q", got)
	}
	if got := seen.Header.Get("Authorization"); got != "" {
		t.Fatalf("anonymous request carried Authorization = %q", got)
	}
}

func TestWebSocketUpgradePassesAndFlushes(t *testing.T) {
	h := newHarness(t)
	srv := httptest.NewServer(h.handler)
	defer srv.Close()

	req, _ := http.NewRequest("GET", srv.URL+"/ws", nil)
	req.Host = "audio.filenkov.store"
	req.Header.Set("Upgrade", "websocket")
	req.Header.Set("Connection", "Upgrade")
	req.Header.Set("Sec-WebSocket-Version", "13")
	req.Header.Set("Sec-WebSocket-Key", "dGhlIHNhbXBsZSBub25jZQ==")
	id := &oidc.Identity{Subject: "ws", Roles: []string{"svc:audio:family"}}
	tok := h.sealTok(id)
	req.AddCookie(&http.Cookie{Name: session.NameAccess, Value: tok})

	res, err := http.DefaultTransport.RoundTrip(req)
	if err != nil {
		t.Fatalf("upgrade: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusSwitchingProtocols {
		t.Fatalf("status = %d, want 101", res.StatusCode)
	}
	if res.Header.Get("X-Frame-Options") != "" || res.Header.Get("Permissions-Policy") != "" {
		t.Fatal("security headers must not ride on the upgrade handshake")
	}
}

func TestHostTimeoutIs504(t *testing.T) {
	h := newHarness(t)
	h.upDelay = 900 * time.Millisecond
	id := &oidc.Identity{Subject: "s", Roles: []string{"svc:audio:family"}}
	rec := h.do(t, "audio.filenkov.store", "GET", "/api/slow", h.sealTok(id), nil)
	if rec.Code != http.StatusGatewayTimeout {
		t.Fatalf("status = %d, want 504", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"gateway_timeout"`) {
		t.Fatalf("body = %s", rec.Body.String())
	}
}

func TestSecurityHeaders(t *testing.T) {
	h := newHarness(t)
	rec := h.do(t, "storage.filenkov.store", "GET", "/health", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	for _, name := range []string{"X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options", "Permissions-Policy"} {
		if rec.Header().Get(name) == "" {
			t.Fatalf("missing %s", name)
		}
	}
	if rec.Header().Get("Strict-Transport-Security") != "" {
		t.Fatal("HSTS belongs to the proxy, not the gateway")
	}
	rec = h.do(t, "audio.filenkov.store", "GET", "/", h.sealTok(&oidc.Identity{Subject: "a", Roles: []string{"svc:audio:family"}}), nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("audio session route = %d", rec.Code)
	}
	if rec.Header().Get("X-Frame-Options") != "" {
		t.Fatal("audio frames itself: X-Frame-Options must be omitted")
	}
	if got := rec.Header().Get("Permissions-Policy"); !strings.Contains(got, "microphone=(self)") {
		t.Fatalf("Permissions-Policy = %q", got)
	}
}

func TestProbesAndRateLimit(t *testing.T) {
	h := newHarness(t)
	rec := h.do(t, "filenkov.store", "GET", "/healthz", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("healthz = %d", rec.Code)
	}
	rec = h.do(t, "filenkov.store", "GET", "/readyz", "", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("readyz = %d", rec.Code)
	}
	// image.filenkov.store routes /healthz to its own app, so the probe must not
	// swallow it.
	h.verifier.tokens["img"] = &oidc.Identity{Subject: "i", Roles: []string{"svc:image:family"}}
	rec = h.do(t, "image.filenkov.store", "GET", "/healthz", "img", nil)
	if rec.Code != http.StatusOK || rec.Body.String() != "upstream" {
		t.Fatalf("host-owned /healthz = %d %q", rec.Code, rec.Body.String())
	}
}

func TestMetricsLoopbackOnly(t *testing.T) {
	h := newHarness(t)
	req := httptest.NewRequest("GET", "http://filenkov.store/metrics", nil)
	req.Host = "filenkov.store"
	req.RemoteAddr = "203.0.113.5:1234"
	rec := httptest.NewRecorder()
	h.handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("public /metrics = %d", rec.Code)
	}
	req.RemoteAddr = "127.0.0.1:1234"
	rec = httptest.NewRecorder()
	h.handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("the public listener must never serve /metrics, got %d", rec.Code)
	}
	rec = httptest.NewRecorder()
	h.server.MetricsHandler().ServeHTTP(rec, httptest.NewRequest("GET", "/metrics", nil))
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), "gateway_requests_total") {
		t.Fatalf("metrics listener = %d %s", rec.Code, rec.Body.String())
	}
}

func TestRefreshHookRunsOncePerRequest(t *testing.T) {
	h := newHarness(t)
	h.refresh.token = h.sealTok(&oidc.Identity{Subject: "r", Roles: []string{"svc:storage:family"}})
	req := httptest.NewRequest("GET", "/files", nil)
	req.Host = "storage.filenkov.store"
	req.AddCookie(&http.Cookie{Name: session.NameSession, Value: "sealed"})
	rec := httptest.NewRecorder()
	h.handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	if h.refresh.calls != 1 {
		t.Fatalf("refresh calls = %d", h.refresh.calls)
	}
}

func TestAccessLogCarriesNoToken(t *testing.T) {
	h := newHarness(t)
	id := &oidc.Identity{Subject: "sub-log", Roles: []string{"svc:storage:family"}}
	token := h.sealTok(id)
	var buf bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&buf, nil))
	srv, err := New(Config{File: h.server.file, Verifier: h.verifier, Sealer: h.server.sealer, Logger: logger, DevHTTP: true})
	if err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest("GET", "/files", nil)
	req.Host = "storage.filenkov.store"
	req.AddCookie(&http.Cookie{Name: session.NameAccess, Value: token})
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, req)
	out := buf.String()
	if strings.Contains(out, token) || strings.Contains(out, "refresh") && strings.Contains(out, "rt-") {
		t.Fatalf("log leaked a credential: %s", out)
	}
	var line map[string]any
	if err := json.Unmarshal([]byte(strings.TrimSpace(out)), &line); err != nil {
		t.Fatalf("log is not one JSON line: %v (%s)", err, out)
	}
	for _, key := range []string{"host", "method", "path", "route", "policy", "status", "dur_ms", "sub", "ip", "ua", "ts"} {
		if _, ok := line[key]; !ok {
			t.Fatalf("access log is missing %q: %s", key, out)
		}
	}
}

func TestSSEIsNotBuffered(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("data: one\n\n"))
		w.(http.Flusher).Flush()
		time.Sleep(300 * time.Millisecond)
		_, _ = w.Write([]byte("data: two\n\n"))
		w.(http.Flusher).Flush()
	}))
	defer up.Close()

	raw := strings.Replace(yamlConfig, `audio_web: "frontend:80"`, `audio_web: "`+up.URL+`"`, 1)
	raw = strings.Replace(raw, `audio: "audio-api:8000"`, `audio: "`+up.URL+`"`, 1)
	file, err := config.Parse([]byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	env := map[string]string{"IDP_CLIENT_SECRET": "i", "GATEWAY_SESSION_KEY": "0123456789abcdef0123456789abcdef", "IDP_ADMIN_SECRET": "a", "SWITCH_TOKEN": "s"}
	if err := file.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err != nil {
		t.Fatal(err)
	}
	sealer, _ := session.NewSealer(env["GATEWAY_SESSION_KEY"], ".filenkov.store", time.Minute, time.Hour)
	verifier := &fakeVerifier{tokens: map[string]*oidc.Identity{"t": {Subject: "s", Roles: []string{"svc:audio:family"}}}}
	srv, err := New(Config{File: file, Verifier: verifier, Sealer: sealer, Logger: slog.Default()})
	if err != nil {
		t.Fatal(err)
	}
	front := httptest.NewServer(srv.Handler())
	defer front.Close()

	req, _ := http.NewRequest("GET", front.URL+"/api/stream", nil)
	req.Host = "audio.filenkov.store"
	req.AddCookie(&http.Cookie{Name: session.NameAccess, Value: "t"})
	start := time.Now()
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	br := bufio.NewReader(res.Body)
	line, err := br.ReadString('\n')
	if err != nil {
		t.Fatalf("first chunk: %v", err)
	}
	if !strings.Contains(line, "one") {
		t.Fatalf("first chunk = %q", line)
	}
	if elapsed := time.Since(start); elapsed > 250*time.Millisecond {
		t.Fatalf("first chunk arrived after %v: the stream was buffered", elapsed)
	}
}

func TestUpstreamDeadIs502(t *testing.T) {
	h := newHarness(t)
	dead := httptest.NewServer(http.NotFoundHandler())
	url := dead.URL
	dead.Close()
	raw := strings.Replace(yamlConfig, `storage: "app:8000"`, `storage: "`+url+`"`, 1)
	file, err := config.Parse([]byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	env := map[string]string{"IDP_CLIENT_SECRET": "i", "GATEWAY_SESSION_KEY": "0123456789abcdef0123456789abcdef", "IDP_ADMIN_SECRET": "a", "SWITCH_TOKEN": "s"}
	if err := file.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err != nil {
		t.Fatal(err)
	}
	sealer, _ := session.NewSealer(env["GATEWAY_SESSION_KEY"], ".filenkov.store", time.Minute, time.Hour)
	srv, err := New(Config{File: file, Verifier: h.verifier, Sealer: sealer, Logger: slog.Default()})
	if err != nil {
		t.Fatal(err)
	}
	id := &oidc.Identity{Subject: "d", Roles: []string{"svc:storage:family"}}
	h.verifier.tokens["dead"] = id
	req := httptest.NewRequest("GET", "/files", nil)
	req.Host = "storage.filenkov.store"
	req.AddCookie(&http.Cookie{Name: session.NameAccess, Value: "dead"})
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502", rec.Code)
	}
}

var _ = net.JoinHostPort
