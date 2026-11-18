package oidc

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	jose "github.com/go-jose/go-jose/v4"
	"github.com/go-jose/go-jose/v4/jwt"
)

const kid = "test-key-1"

type fakeIdP struct {
	server   *httptest.Server
	priv     *rsa.PrivateKey
	other    *rsa.PrivateKey
	jwksHits *int32
	issuer   string
}

func newFakeIdP(t *testing.T) *fakeIdP {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	other, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	f := &fakeIdP{priv: priv, other: other, jwksHits: new(int32)}
	mux := http.NewServeMux()
	mux.HandleFunc("/realms/filenkov/.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"issuer":                 f.issuer,
			"authorization_endpoint": f.issuer + "/auth",
			"token_endpoint":         f.issuer + "/token",
			"jwks_uri":               f.issuer + "/certs",
			"revocation_endpoint":    f.issuer + "/revoke",
			"end_session_endpoint":   f.issuer + "/logout",
		})
	})
	mux.HandleFunc("/realms/filenkov/certs", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(f.jwksHits, 1)
		set := jose.JSONWebKeySet{Keys: []jose.JSONWebKey{{
			Key: &priv.PublicKey, KeyID: kid, Algorithm: "RS256", Use: "sig",
		}}}
		_ = json.NewEncoder(w).Encode(set)
	})
	f.server = httptest.NewServer(mux)
	f.issuer = f.server.URL + "/realms/filenkov"
	t.Cleanup(f.server.Close)
	return f
}

func (f *fakeIdP) sign(t *testing.T, claims map[string]any, key *rsa.PrivateKey, keyID string) string {
	t.Helper()
	signer, err := jose.NewSigner(
		jose.SigningKey{Algorithm: jose.RS256, Key: jose.JSONWebKey{Key: key, KeyID: keyID}},
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

func baseClaims(f *fakeIdP, mutate func(map[string]any)) map[string]any {
	c := map[string]any{
		"iss":   f.issuer,
		"aud":   "account",
		"azp":   "gateway",
		"typ":   "Bearer",
		"sub":   "8f14e45f-ceea-467a-9e4b-1c2f9a0f5d11",
		"email": "ada@example.com",
		"name":  "Ada Lovelace",
		"sid":   "s-1",
		"exp":   time.Now().Add(5 * time.Minute).Unix(),
		"realm_access": map[string]any{
			"roles": []string{"admin", "svc:storage:family"},
		},
	}
	if mutate != nil {
		mutate(c)
	}
	return c
}

func (f *fakeIdP) verifier(t *testing.T) *Verifier {
	t.Helper()
	ctx := context.Background()
	p, err := Discover(ctx, f.issuer, nil)
	if err != nil {
		t.Fatalf("discover: %v", err)
	}
	v, err := NewVerifier(ctx, p, "account", "gateway", "gateway", 15*time.Minute, nil)
	if err != nil {
		t.Fatalf("verifier: %v", err)
	}
	return v
}

func TestVerifyValid(t *testing.T) {
	f := newFakeIdP(t)
	v := f.verifier(t)
	id, err := v.Verify(context.Background(), f.sign(t, baseClaims(f, nil), f.priv, kid))
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if id.Subject == "" || id.Email != "ada@example.com" || id.SID != "s-1" {
		t.Fatalf("identity = %+v", id)
	}
	if !id.HasRole("admin") || id.ServiceLevel("storage") != "family" {
		t.Fatalf("roles = %v", id.Roles)
	}
	if got := id.RoleHeader(); got != "admin svc:storage:family" {
		t.Fatalf("role header = %q", got)
	}
}

func TestVerifyRejects(t *testing.T) {
	f := newFakeIdP(t)
	v := f.verifier(t)
	cases := []struct {
		name   string
		claims map[string]any
		key    *rsa.PrivateKey
		kid    string
	}{
		{"bad signature", baseClaims(f, nil), f.other, kid},
		{"foreign aud", baseClaims(f, func(c map[string]any) { c["aud"] = []string{"other"} }), f.priv, kid},
		{"expired", baseClaims(f, func(c map[string]any) { c["exp"] = time.Now().Add(-2 * time.Minute).Unix() }), f.priv, kid},
		{"wrong azp", baseClaims(f, func(c map[string]any) { c["azp"] = "someone-else" }), f.priv, kid},
		{"not an access token", baseClaims(f, func(c map[string]any) { c["typ"] = "ID" }), f.priv, kid},
		{"no subject", baseClaims(f, func(c map[string]any) { delete(c, "sub") }), f.priv, kid},
		{"unknown kid", baseClaims(f, nil), f.priv, "rotated-key"},
		{"not yet valid", baseClaims(f, func(c map[string]any) { c["nbf"] = time.Now().Add(10 * time.Minute).Unix() }), f.priv, kid},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if _, err := v.Verify(context.Background(), f.sign(t, c.claims, c.key, c.kid)); err == nil {
				t.Fatal("expected an error")
			}
		})
	}
}

// An unknown kid asks the idp for keys again; a token that keeps failing must not
// turn every request into a JWKS fetch.
func TestUnknownKidReloadsOnce(t *testing.T) {
	f := newFakeIdP(t)
	v := f.verifier(t)
	valid := f.sign(t, baseClaims(f, nil), f.priv, kid)
	if _, err := v.Verify(context.Background(), valid); err != nil {
		t.Fatalf("warm: %v", err)
	}
	before := atomic.LoadInt32(f.jwksHits)
	unknown := f.sign(t, baseClaims(f, nil), f.priv, "rotated-key")
	if _, err := v.Verify(context.Background(), unknown); err == nil {
		t.Fatal("an unknown kid must not verify")
	}
	after := atomic.LoadInt32(f.jwksHits)
	if after-before != 1 {
		t.Fatalf("unknown kid caused %d jwks fetches, want 1", after-before)
	}
	if _, err := v.Verify(context.Background(), valid); err != nil {
		t.Fatalf("a known kid must still verify: %v", err)
	}
}

func TestKeySetRotatesAfterTTL(t *testing.T) {
	f := newFakeIdP(t)
	ctx := context.Background()
	p, err := Discover(ctx, f.issuer, nil)
	if err != nil {
		t.Fatal(err)
	}
	clock := time.Now()
	v, err := NewVerifier(ctx, p, "account", "gateway", "gateway", 15*time.Minute, nil)
	if err != nil {
		t.Fatal(err)
	}
	v.now = func() time.Time { return clock }
	// The token must outlive the cache TTL, otherwise this test measures expiry.
	tok := f.sign(t, baseClaims(f, func(c map[string]any) {
		c["exp"] = clock.Add(2 * time.Hour).Unix()
	}), f.priv, kid)
	if _, err := v.Verify(ctx, tok); err != nil {
		t.Fatal(err)
	}
	before := atomic.LoadInt32(f.jwksHits)
	clock = clock.Add(16 * time.Minute)
	if _, err := v.Verify(ctx, tok); err != nil {
		t.Fatal(err)
	}
	if atomic.LoadInt32(f.jwksHits) <= before {
		t.Fatal("an expired cache must reload the key set")
	}
}

func TestDiscoverRejectsForeignIssuer(t *testing.T) {
	f := newFakeIdP(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"issuer":                 "https://evil.example/realms/filenkov",
			"authorization_endpoint": "https://evil.example/auth",
			"token_endpoint":         "https://evil.example/token",
			"jwks_uri":               "https://evil.example/certs",
		})
	}))
	defer srv.Close()
	if _, err := Discover(context.Background(), f.issuer, nil); err == nil {
		_ = srv
	}
	if _, err := Discover(context.Background(), srv.URL+"/realms/filenkov", nil); err == nil {
		t.Fatal("a document with a different issuer must be refused")
	}
}
