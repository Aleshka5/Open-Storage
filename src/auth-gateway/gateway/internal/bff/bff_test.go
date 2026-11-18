package bff

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	jose "github.com/go-jose/go-jose/v4"
	"github.com/go-jose/go-jose/v4/jwt"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
	"github.com/aleshka5/open-storage/auth-gateway/internal/session"
)

type fakeIdP struct {
	server     *httptest.Server
	priv       *rsa.PrivateKey
	issuer     string
	tokenCalls atomic.Int32
	logoutHits atomic.Int32
	// grant is the answer the token endpoint gives: "ok" or "invalid_grant".
	grant string
	// idNonce lets the fake sign an id_token with the nonce the BFF expects.
	idNonce string
	refresh string
}

func newFakeIdP(t *testing.T) *fakeIdP {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	f := &fakeIdP{priv: priv, grant: "ok", refresh: "rt-1"}
	mux := http.NewServeMux()
	mux.HandleFunc("/realms/filenkov/.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"issuer":                 f.issuer,
			"authorization_endpoint": f.issuer + "/auth",
			"token_endpoint":         f.issuer + "/token",
			"jwks_uri":               f.issuer + "/certs",
			"end_session_endpoint":   f.issuer + "/logout",
		})
	})
	mux.HandleFunc("/realms/filenkov/certs", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(jose.JSONWebKeySet{Keys: []jose.JSONWebKey{{
			Key: &priv.PublicKey, KeyID: "k1", Algorithm: "RS256", Use: "sig",
		}}})
	})
	mux.HandleFunc("/realms/filenkov/logout", func(w http.ResponseWriter, r *http.Request) {
		f.logoutHits.Add(1)
		w.WriteHeader(http.StatusNoContent)
	})
	mux.HandleFunc("/realms/filenkov/token", func(w http.ResponseWriter, r *http.Request) {
		f.tokenCalls.Add(1)
		_ = r.ParseForm()
		if f.grant != "ok" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(`{"error":"invalid_grant"}`))
			return
		}
		code := r.PostForm.Get("code")
		nonce := strings.TrimPrefix(code, "nonce:")
		access := f.sign(t, map[string]any{
			"iss": f.issuer, "aud": "account", "azp": "gateway", "typ": "Bearer",
			"sub": "sub-1", "email": "ada@example.com", "name": "Ada", "sid": "sid-1",
			"exp":          time.Now().Add(5 * time.Minute).Unix(),
			"realm_access": map[string]any{"roles": []string{"admin", "svc:storage:family"}},
		})
		idToken := f.sign(t, map[string]any{
			"iss": f.issuer, "aud": "gateway", "azp": "gateway",
			"sub": "sub-1", "email": "ada@example.com", "name": "Ada", "sid": "sid-1", "nonce": nonce,
			"exp": time.Now().Add(5 * time.Minute).Unix(),
		})
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token": access, "id_token": idToken, "refresh_token": f.refresh, "expires_in": 300,
		})
	})
	f.server = httptest.NewServer(mux)
	f.issuer = f.server.URL + "/realms/filenkov"
	t.Cleanup(f.server.Close)
	return f
}

func (f *fakeIdP) sign(t *testing.T, claims map[string]any) string {
	t.Helper()
	signer, err := jose.NewSigner(
		jose.SigningKey{Algorithm: jose.RS256, Key: jose.JSONWebKey{Key: f.priv, KeyID: "k1"}},
		(&jose.SignerOptions{}).WithType("JWT"),
	)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := jwt.Signed(signer).Claims(claims).Serialize()
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

type harness struct {
	idp    *fakeIdP
	server *Server
	file   *config.File
}

const yamlConfig = `
public_origin: "https://filenkov.store"
idp:
  issuer: "ISSUER"
  client_id: gateway
  client_secret: "env:IDP_CLIENT_SECRET"
session:
  cookie_domain: ".filenkov.store"
  key: "env:GATEWAY_SESSION_KEY"
services: [storage, image]
upstreams:
  resume: "resume:80"
hosts:
  - host: filenkov.store
    upstream: resume
    routes:
      - { path: /auth/**, bff: true }
      - { path: /**, policy: public }
  - host: storage.filenkov.store
    upstream: resume
    routes:
      - { path: /**, policy: "service(storage, family)" }
`

func newHarness(t *testing.T) *harness {
	t.Helper()
	idp := newFakeIdP(t)
	raw := strings.Replace(yamlConfig, "ISSUER", idp.issuer, 1)
	file, err := config.Parse([]byte(raw))
	if err != nil {
		t.Fatalf("config: %v", err)
	}
	env := map[string]string{
		"IDP_CLIENT_SECRET":   "idp-secret",
		"GATEWAY_SESSION_KEY": "0123456789abcdef0123456789abcdef",
	}
	if err := file.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err != nil {
		t.Fatalf("env: %v", err)
	}
	provider, err := oidc.Discover(t.Context(), idp.issuer, nil)
	if err != nil {
		t.Fatalf("discover: %v", err)
	}
	verifier, err := oidc.NewVerifier(t.Context(), provider, "account", "gateway", "gateway", 15*time.Minute, nil)
	if err != nil {
		t.Fatalf("verifier: %v", err)
	}
	sealer, err := session.NewSealer(env["GATEWAY_SESSION_KEY"], ".filenkov.store", 5*time.Minute, 168*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	srv, err := New(Config{File: file, Provider: provider, Verifier: verifier, Sealer: sealer})
	if err != nil {
		t.Fatalf("bff: %v", err)
	}
	return &harness{idp: idp, server: srv, file: file}
}

func (h *harness) call(t *testing.T, path string, cookies []*http.Cookie, id *oidc.Identity, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest("GET", "http://filenkov.store"+path, nil)
	req.Host = "filenkov.store"
	for _, c := range cookies {
		req.AddCookie(&http.Cookie{Name: c.Name, Value: c.Value})
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	if id != nil {
		req = req.WithContext(oidc.WithIdentity(req.Context(), id))
	}
	rec := httptest.NewRecorder()
	h.server.Handler().ServeHTTP(rec, req)
	return rec
}

func cookieOf(rec *httptest.ResponseRecorder, name string) *http.Cookie {
	for _, c := range rec.Result().Cookies() {
		if c.Name == name {
			return c
		}
	}
	return nil
}

func TestLoginRedirectsWithPKCEAndNonce(t *testing.T) {
	h := newHarness(t)
	rec := h.call(t, "/auth/login?return_to="+url.QueryEscape("https://storage.filenkov.store/files"), nil, nil, nil)
	if rec.Code != http.StatusFound {
		t.Fatalf("status = %d", rec.Code)
	}
	loc, err := url.Parse(rec.Header().Get("Location"))
	if err != nil {
		t.Fatal(err)
	}
	q := loc.Query()
	if q.Get("client_id") != "gateway" || q.Get("redirect_uri") != "https://filenkov.store/auth/callback" {
		t.Fatalf("query = %v", q)
	}
	if q.Get("kc_idp_hint") != "google" || q.Get("code_challenge_method") != "S256" {
		t.Fatalf("query = %v", q)
	}
	if len(q.Get("state")) < 16 || len(q.Get("nonce")) < 16 || len(q.Get("code_challenge")) < 32 {
		t.Fatalf("state, nonce or challenge is too short: %v", q)
	}
	if c := cookieOf(rec, session.NameFlow); c == nil || !c.HttpOnly || c.Value == "" {
		t.Fatalf("flow cookie = %+v", c)
	}
}

func TestLoginRefusesForeignReturnTo(t *testing.T) {
	h := newHarness(t)
	rec := h.call(t, "/auth/login?return_to="+url.QueryEscape("https://evil.example.com/steal"), nil, nil, nil)
	if rec.Code != http.StatusFound {
		t.Fatalf("status = %d", rec.Code)
	}
	flow := cookieOf(rec, session.NameFlow)
	st, err := h.server.sealer.OpenFlow(flow.Value)
	if err != nil {
		t.Fatal(err)
	}
	if st.ReturnTo != "https://filenkov.store/" {
		t.Fatalf("return_to = %q, want the public origin", st.ReturnTo)
	}
}

func TestCallbackCompletesTheLogin(t *testing.T) {
	h := newHarness(t)
	rec := h.call(t, "/auth/login?return_to="+url.QueryEscape("https://storage.filenkov.store/files"), nil, nil, nil)
	flow := cookieOf(rec, session.NameFlow)
	loc, _ := url.Parse(rec.Header().Get("Location"))
	state := loc.Query().Get("state")
	nonce := loc.Query().Get("nonce")

	cb := h.call(t, "/auth/callback?code=nonce:"+nonce+"&state="+state, []*http.Cookie{{Name: flow.Name, Value: flow.Value}}, nil, nil)
	if cb.Code != http.StatusFound {
		t.Fatalf("status = %d", cb.Code)
	}
	if got := cb.Header().Get("Location"); got != "https://storage.filenkov.store/files" {
		t.Fatalf("Location = %q", got)
	}
	access := cookieOf(cb, session.NameAccess)
	if access == nil || access.Value == "" {
		t.Fatal("no access cookie")
	}
	sealed := cookieOf(cb, session.NameSession)
	if sealed == nil {
		t.Fatal("no session cookie")
	}
	st, err := h.server.sealer.Open(sealed.Value)
	if err != nil {
		t.Fatal(err)
	}
	if st.Subject != "sub-1" || st.SID != "sid-1" || st.RefreshToken == "" {
		t.Fatalf("session = %+v", st)
	}
	// The flow cookie is deleted whatever the outcome.
	if c := cookieOf(cb, session.NameFlow); c == nil || c.MaxAge >= 0 {
		t.Fatalf("flow cookie was not cleared: %+v", c)
	}
}

func TestCallbackRejectsForeignState(t *testing.T) {
	h := newHarness(t)
	rec := h.call(t, "/auth/login", nil, nil, nil)
	flow := cookieOf(rec, session.NameFlow)
	loc, _ := url.Parse(rec.Header().Get("Location"))
	nonce := loc.Query().Get("nonce")
	cb := h.call(t, "/auth/callback?code=nonce:"+nonce+"&state=forged", []*http.Cookie{{Name: flow.Name, Value: flow.Value}}, nil, nil)
	if cb.Code != http.StatusFound || !strings.Contains(cb.Header().Get("Location"), "auth_error=invalid_state") {
		t.Fatalf("callback = %d %q", cb.Code, cb.Header().Get("Location"))
	}
	if cookieOf(cb, session.NameAccess) != nil {
		t.Fatal("a failed callback must not set an access cookie")
	}
}

func TestSessionProfile(t *testing.T) {
	h := newHarness(t)
	rec := h.call(t, "/auth/session", nil, nil, nil)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous = %d", rec.Code)
	}
	id := &oidc.Identity{Subject: "sub-1", Email: "ada@example.com", Name: "Ada", Roles: []string{"admin", "svc:storage:family"}}
	rec = h.call(t, "/auth/session", nil, id, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("signed in = %d %s", rec.Code, rec.Body.String())
	}
	var body struct {
		Subject  string `json:"subject"`
		Services []struct {
			Service string  `json:"service"`
			Level   *string `json:"level"`
		} `json:"services"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Subject != "sub-1" || len(body.Services) != 2 {
		t.Fatalf("body = %s", rec.Body.String())
	}
	if body.Services[0].Level == nil || *body.Services[0].Level != "family" {
		t.Fatalf("storage level = %v", body.Services[0].Level)
	}
	if body.Services[1].Level != nil {
		t.Fatalf("image level should be null, got %v", *body.Services[1].Level)
	}
}

func TestSessionRefreshesSilently(t *testing.T) {
	h := newHarness(t)
	sealed, err := h.server.sealer.Seal(session.State{Subject: "sub-1", RefreshToken: "rt-1", SID: "sid-1"})
	if err != nil {
		t.Fatal(err)
	}
	rec := h.call(t, "/auth/session", []*http.Cookie{{Name: session.NameSession, Value: sealed}}, nil, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d %s", rec.Code, rec.Body.String())
	}
	if cookieOf(rec, session.NameAccess) == nil {
		t.Fatal("a silent refresh must set a new access cookie")
	}
	if h.idp.tokenCalls.Load() != 1 {
		t.Fatalf("token calls = %d", h.idp.tokenCalls.Load())
	}
}

func TestRefreshInvalidGrantClearsCookies(t *testing.T) {
	h := newHarness(t)
	h.idp.grant = "invalid_grant"
	sealed, _ := h.server.sealer.Seal(session.State{Subject: "sub-1", RefreshToken: "rt-dead", SID: "sid-1"})
	rec := h.call(t, "/auth/session", []*http.Cookie{{Name: session.NameSession, Value: sealed}}, nil, nil)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d", rec.Code)
	}
	cleared := cookieOf(rec, session.NameSession)
	if cleared == nil || cleared.MaxAge >= 0 {
		t.Fatalf("session cookie was not cleared: %+v", cleared)
	}
}

func TestLogoutNeedsOrigin(t *testing.T) {
	h := newHarness(t)
	req := httptest.NewRequest("POST", "http://filenkov.store/auth/logout", nil)
	req.Host = "filenkov.store"
	rec := httptest.NewRecorder()
	h.server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("logout without Origin = %d", rec.Code)
	}

	sealed, _ := h.server.sealer.Seal(session.State{Subject: "sub-1", RefreshToken: "rt-1", SID: "sid-1"})
	req = httptest.NewRequest("POST", "http://filenkov.store/auth/logout", nil)
	req.Host = "filenkov.store"
	req.Header.Set("Origin", "https://filenkov.store")
	req.AddCookie(&http.Cookie{Name: session.NameSession, Value: sealed})
	rec = httptest.NewRecorder()
	h.server.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("logout = %d", rec.Code)
	}
	if h.idp.logoutHits.Load() != 1 {
		t.Fatalf("idp logout hits = %d", h.idp.logoutHits.Load())
	}
	for _, name := range []string{session.NameAccess, session.NameSession} {
		if c := cookieOf(rec, name); c == nil || c.MaxAge >= 0 {
			t.Fatalf("%s was not cleared: %+v", name, c)
		}
	}
}

func TestGetLogoutDoesNotExist(t *testing.T) {
	h := newHarness(t)
	rec := h.call(t, "/auth/logout", nil, nil, nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("GET /auth/logout = %d", rec.Code)
	}
}
