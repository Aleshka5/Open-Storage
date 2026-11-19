package oidc

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// publicIssuer is the name a browser follows; it does not resolve from here,
// which is the whole reason a server-side base exists.
const publicIssuer = "https://id.example/realms/r"

func discoveryDoc(issuer, tokenURL string) string {
	return fmt.Sprintf(`{
	  "issuer": %q,
	  "authorization_endpoint": %q,
	  "token_endpoint": %q,
	  "jwks_uri": %q,
	  "end_session_endpoint": %q,
	  "revocation_endpoint": %q
	}`, issuer,
		issuer+"/auth",
		tokenURL,
		issuer+"/certs",
		issuer+"/logout",
		issuer+"/revoke")
}

func newDiscovery(t *testing.T, doc string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/realms/r/.well-known/openid-configuration" {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(doc))
	}))
	t.Cleanup(srv.Close)
	return srv
}

// newSelfDescribingDiscovery answers with a document whose issuer is the address
// it was reached on, which is what the plain Discover test needs.
func newSelfDescribingDiscovery(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		issuer := "http://" + r.Host + "/realms/r"
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(discoveryDoc(issuer, issuer+"/token")))
	}))
	t.Cleanup(srv.Close)
	return srv
}

// Without an internal base nothing is rewritten: the document is used verbatim.
func TestDiscoverKeepsPublicEndpoints(t *testing.T) {
	srv := newSelfDescribingDiscovery(t)
	issuer := srv.URL + "/realms/r"

	p, err := Discover(context.Background(), issuer, nil)
	if err != nil {
		t.Fatalf("discover: %v", err)
	}
	if p.TokenURL != issuer+"/token" || p.JWKSURL != issuer+"/certs" || p.AuthURL != issuer+"/auth" {
		t.Fatalf("endpoints changed without an internal base: %+v", p)
	}
}

// With an internal base the server-side endpoints move, and the browser's
// authorization endpoint does not.
func TestDiscoverServerSideRewritesOnlyServerCalls(t *testing.T) {
	srv := newDiscovery(t, discoveryDoc(publicIssuer, publicIssuer+"/token"))
	base := srv.URL + "/realms/r"
	p, err := DiscoverServerSide(context.Background(), publicIssuer, base, nil)
	if err != nil {
		t.Fatalf("discover: %v", err)
	}
	if p.AuthURL != publicIssuer+"/auth" {
		t.Fatalf("authorization endpoint must stay public, got %q", p.AuthURL)
	}
	for name, got := range map[string]string{
		"token":       p.TokenURL,
		"jwks":        p.JWKSURL,
		"end_session": p.EndSessionURL,
		"revocation":  p.RevokeURL,
	} {
		if !strings.HasPrefix(got, base+"/") {
			t.Fatalf("%s endpoint = %q, want the internal base %q", name, got, base)
		}
	}
	if p.Issuer != publicIssuer {
		t.Fatalf("issuer = %q, want the public issuer", p.Issuer)
	}
}

// An endpoint the idp hosts elsewhere is not ours to move.
func TestDiscoverServerSideLeavesForeignEndpoints(t *testing.T) {
	srv := newDiscovery(t, discoveryDoc(publicIssuer, "https://auth.other.example/token"))
	p, err := DiscoverServerSide(context.Background(), publicIssuer, srv.URL+"/realms/r", nil)
	if err != nil {
		t.Fatalf("discover: %v", err)
	}
	if p.TokenURL != "https://auth.other.example/token" {
		t.Fatalf("foreign token endpoint was rewritten to %q", p.TokenURL)
	}
}

// The internal base may not smuggle a different issuer past the check.
func TestDiscoverServerSideStillChecksIssuer(t *testing.T) {
	srv := newDiscovery(t, discoveryDoc("https://evil.example/realms/r", "https://evil.example/realms/r/token"))
	if _, err := DiscoverServerSide(context.Background(), publicIssuer, srv.URL+"/realms/r", nil); err == nil {
		t.Fatal("a mismatched issuer was accepted")
	}
}
