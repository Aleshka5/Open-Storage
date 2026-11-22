package bff

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
)

func sameSiteServer(t *testing.T, devHTTP bool) *Server {
	t.Helper()
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
  resume: "resume:80"
hosts:
  - host: filenkov.store
    upstream: resume
    routes:
      - { path: /**, policy: public }
  - host: observer.filenkov.store
    upstream: resume
    routes:
      - { path: /**, policy: public }
`
	file, err := config.Parse([]byte(raw))
	if err != nil {
		t.Fatalf("config: %v", err)
	}
	return &Server{file: file, devHTTP: devHTTP}
}

// A cross-site form POST carries Origin, so "the header is present" is not a
// pass: the value has to be one of ours.
func TestLogoutRefusesAForeignOrigin(t *testing.T) {
	s := sameSiteServer(t, false)
	for _, tc := range []struct {
		name   string
		origin string
		withX  bool
		want   bool
	}{
		{"our own page", "https://filenkov.store", false, true},
		{"another host we serve", "https://observer.filenkov.store", false, true},
		{"someone else's site", "https://evil.example", false, false},
		{"same name, other scheme", "http://filenkov.store", false, false},
		{"no origin, no header", "", false, false},
		{"no origin, our header", "", true, true},
		{"unparsable origin", "://nope", false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			r := httptest.NewRequest(http.MethodPost, "https://filenkov.store/auth/logout", nil)
			if tc.origin != "" {
				r.Header.Set("Origin", tc.origin)
			}
			if tc.withX {
				r.Header.Set("X-Requested-With", "XMLHttpRequest")
			}
			if got := s.sameSite(r); got != tc.want {
				t.Fatalf("sameSite = %v, want %v", got, tc.want)
			}
		})
	}
}

// A plain http origin is acceptable only where the stand itself is plain http.
func TestLogoutAcceptsHTTPOriginInDev(t *testing.T) {
	s := sameSiteServer(t, true)
	r := httptest.NewRequest(http.MethodPost, "http://filenkov.store/auth/logout", nil)
	r.Header.Set("Origin", "http://filenkov.store")
	if !s.sameSite(r) {
		t.Fatal("dev http origin was refused")
	}
}
