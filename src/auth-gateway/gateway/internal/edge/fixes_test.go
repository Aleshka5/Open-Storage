package edge

import (
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
)

func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// newLimited builds the edge from the shared fixture with a smaller budget. The
// resume upstream is a live test server, so a status code says what the edge
// decided rather than what a missing name did.
func newLimited(t *testing.T, limit int) http.Handler {
	t.Helper()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	t.Cleanup(upstream.Close)
	raw := strings.Replace(yamlConfig,
		"rate_limit: { requests: 1000, per: 1m }",
		fmt.Sprintf("rate_limit: { requests: %d, per: 1m }", limit), 1)
	raw = strings.Replace(raw, `resume: "resume:80"`, `resume: "`+upstream.URL+`"`, 1)
	file, err := config.Parse([]byte(raw))
	if err != nil {
		t.Fatalf("config: %v", err)
	}
	srv, err := New(Config{
		File:     file,
		Verifier: &fakeVerifier{tokens: map[string]*oidc.Identity{}},
		Logger:   discardLogger(),
	})
	if err != nil {
		t.Fatalf("edge: %v", err)
	}
	return srv.Handler()
}

// A public route used to hand the client's own Authorization header to the
// upstream. identity-v1 says the application receives the bearer the gateway
// injected, and nothing when it injected nothing.
func TestInboundAuthorizationIsDropped(t *testing.T) {
	h := newHarness(t)
	rec := h.do(t, "filenkov.store", "GET", "/", "", map[string]string{
		"Authorization": "Bearer client-supplied",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	select {
	case seen := <-h.seen:
		if got := seen.Header.Get("Authorization"); got != "" {
			t.Fatalf("upstream received the client bearer %q", got)
		}
	case <-time.After(time.Second):
		t.Fatal("the upstream never saw the request")
	}
}

// On an authorized route the header carries the cookie's token, not the one the
// client typed next to it.
func TestSessionAuthorizationIsTheCookieToken(t *testing.T) {
	h := newHarness(t)
	token := h.sealTok(&oidc.Identity{Subject: "s1", Roles: []string{"svc:storage:family"}})
	rec := h.do(t, "storage.filenkov.store", "GET", "/files", token, map[string]string{
		"Authorization": "Bearer forged",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	select {
	case seen := <-h.seen:
		if got, want := seen.Header.Get("Authorization"), "Bearer "+token; got != want {
			t.Fatalf("Authorization = %q, want the cookie token", got)
		}
	case <-time.After(time.Second):
		t.Fatal("the upstream never saw the request")
	}
}

// The proxy in front of the gateway appends the address it saw to whatever the
// client sent, so only the last hop is trustworthy.
func TestClientIPUsesTheLastHop(t *testing.T) {
	cases := []struct{ name, xff, remote, want string }{
		{"caddy appends", "9.9.9.9, 203.0.113.7", "127.0.0.1:5000", "203.0.113.7"},
		{"caddy overwrites", "203.0.113.7", "127.0.0.1:5000", "203.0.113.7"},
		{"garbage is not an address", "not-an-ip", "127.0.0.1:5000", "127.0.0.1"},
		{"empty hop is skipped", "9.9.9.9, ", "127.0.0.1:5000", "9.9.9.9"},
		{"no header", "", "198.51.100.4:9000", "198.51.100.4"},
		{"host and port hop", "203.0.113.7:4444", "127.0.0.1:5000", "203.0.113.7"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			r := httptest.NewRequest("GET", "/", nil)
			r.RemoteAddr = tc.remote
			if tc.xff != "" {
				r.Header.Set("X-Forwarded-For", tc.xff)
			}
			if got := clientIP(r); got != tc.want {
				t.Fatalf("clientIP = %q, want %q", got, tc.want)
			}
		})
	}
}

// A client that rotates the part of X-Forwarded-For it controls does not get a
// fresh budget: the last hop is the same address every time.
func TestRateLimitFollowsTheLastHop(t *testing.T) {
	srv := newLimited(t, 2)
	for i, want := range []int{http.StatusOK, http.StatusOK, http.StatusTooManyRequests} {
		req := httptest.NewRequest("GET", "http://filenkov.store/", nil)
		req.Host = "filenkov.store"
		req.Header.Set("X-Forwarded-For", fmt.Sprintf("10.0.0.%d, 203.0.113.7", i+1))
		rec := httptest.NewRecorder()
		srv.ServeHTTP(rec, req)
		if rec.Code != want {
			t.Fatalf("request %d = %d, want %d", i+1, rec.Code, want)
		}
	}
}

// Probes answer for free only if they bypass the budget; they must not.
func TestProbesAreMetered(t *testing.T) {
	srv := newLimited(t, 1)
	for i, want := range []int{http.StatusOK, http.StatusTooManyRequests} {
		req := httptest.NewRequest("GET", "http://127.0.0.1:8080/healthz", nil)
		req.RemoteAddr = "203.0.113.9:1234"
		rec := httptest.NewRecorder()
		srv.ServeHTTP(rec, req)
		if rec.Code != want {
			t.Fatalf("probe %d = %d, want %d", i+1, rec.Code, want)
		}
	}
}

// `frame: self` is a host property, not a guess about its name.
func TestFrameHeaderFollowsConfig(t *testing.T) {
	h := newHarness(t)
	if rec := h.do(t, "storage.filenkov.store", "GET", "/health", "", nil); rec.Header().Get("X-Frame-Options") != "DENY" {
		t.Fatalf("storage X-Frame-Options = %q, want DENY", rec.Header().Get("X-Frame-Options"))
	}
	audio := h.sealTok(&oidc.Identity{Subject: "a1", Roles: []string{"svc:audio:family"}})
	if rec := h.do(t, "audio.filenkov.store", "GET", "/", audio, nil); rec.Header().Get("X-Frame-Options") != "" {
		t.Fatalf("audio frames itself, got X-Frame-Options = %q", rec.Header().Get("X-Frame-Options"))
	}
}

// Keycloak serves check_session_iframe on its own origin, so a DENY on the idp
// host turns into a 3rd-party check iframe timeout at login (ADR-0008).
func TestIdPHostFrameSelf(t *testing.T) {
	h := newHarness(t)
	if rec := h.do(t, "id.filenkov.store", "GET", "/realms/filenkov/", "", nil); rec.Header().Get("X-Frame-Options") != "" {
		t.Fatalf("idp frames its own check_session_iframe, got X-Frame-Options = %q", rec.Header().Get("X-Frame-Options"))
	}
}

// The gateway's own answers follow the host too: a `frame: self` host must not
// get a DENY on a 404 or on the 302 to login.
func TestOwnAnswersFollowHostFrame(t *testing.T) {
	h := newHarness(t)
	if rec := h.do(t, "id.filenkov.store", "GET", "/no-such-path-here", "", nil); rec.Header().Get("X-Frame-Options") != "" {
		t.Fatalf("idp 404 X-Frame-Options = %q, want empty", rec.Header().Get("X-Frame-Options"))
	}
	if rec := h.do(t, "storage.filenkov.store", "GET", "/no-such-path-here", "", nil); rec.Header().Get("X-Frame-Options") != "DENY" {
		t.Fatalf("storage 404 X-Frame-Options = %q, want DENY", rec.Header().Get("X-Frame-Options"))
	}
	// meet frames itself and answers an anonymous caller with a 302 to login.
	if rec := h.do(t, "meet.filenkov.store", "GET", "/", "", nil); rec.Header().Get("X-Frame-Options") != "" {
		t.Fatalf("meet 302 X-Frame-Options = %q, want empty", rec.Header().Get("X-Frame-Options"))
	}
}

// Every timeout a route can ask for has a transport, and the one it gets is the
// route's own: a silent downgrade to the default is what this guards.
func TestTransportCoversEveryRouteTimeout(t *testing.T) {
	h := newHarness(t)
	for _, b := range h.server.file.Hosts {
		block := h.server.router.HostBlock(b.Host)
		if block == nil {
			continue
		}
		for _, route := range block.Routes {
			if _, ok := h.server.proxy.transports[route.Timeouts.ResponseHeader]; !ok {
				t.Fatalf("%s %s: no transport for %s", block.Name, route.Path, route.Timeouts.ResponseHeader)
			}
		}
	}
}

// A passthrough host is not an app under identity v1: the idp console needs the
// bearer the browser holds, so nothing is stripped there and nothing is written.
func TestPassthroughHostKeepsClientHeaders(t *testing.T) {
	echo := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Seen-Authorization", r.Header.Get("Authorization"))
		w.Header().Set("X-Seen-Auth-Subject", r.Header.Get("X-Auth-Subject"))
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(echo.Close)

	raw := `
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
  up: "` + echo.URL + `"
hosts:
  - host: inject.example
    upstream: up
    routes:
      - { path: /**, policy: public }
  - host: pass.example
    upstream: up
    identity: passthrough
    routes:
      - { path: /**, policy: public }
`
	file, err := config.Parse([]byte(raw))
	if err != nil {
		t.Fatalf("config: %v", err)
	}
	srv, err := New(Config{
		File:     file,
		Verifier: &fakeVerifier{tokens: map[string]*oidc.Identity{}},
		Logger:   discardLogger(),
	})
	if err != nil {
		t.Fatalf("edge: %v", err)
	}
	handler := srv.Handler()

	for _, tc := range []struct {
		host        string
		wantAuth    string
		wantSubject string
	}{
		{"inject.example", "", ""},
		{"pass.example", "Bearer client-supplied", "forged"},
	} {
		req := httptest.NewRequest("GET", "http://"+tc.host+"/", nil)
		req.Host = tc.host
		req.Header.Set("Authorization", "Bearer client-supplied")
		req.Header.Set("X-Auth-Subject", "forged")
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s: status = %d", tc.host, rec.Code)
		}
		if got := rec.Header().Get("X-Seen-Authorization"); got != tc.wantAuth {
			t.Fatalf("%s: upstream saw Authorization %q, want %q", tc.host, got, tc.wantAuth)
		}
		if got := rec.Header().Get("X-Seen-Auth-Subject"); got != tc.wantSubject {
			t.Fatalf("%s: upstream saw X-Auth-Subject %q, want %q", tc.host, got, tc.wantSubject)
		}
	}
}
