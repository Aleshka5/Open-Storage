// Package edge is the public HTTP entry point: it matches a route, decides who
// may call it, injects identity v1 and proxies. The invariants it must hold are
// owned by the gateway external contract.
package edge

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
	"github.com/aleshka5/open-storage/auth-gateway/internal/policy"
	"github.com/aleshka5/open-storage/auth-gateway/internal/session"
)

// TokenVerifier is the part of oidc.Verifier the edge uses. Tests supply a fake.
type TokenVerifier interface {
	Verify(ctx context.Context, raw string) (*oidc.Identity, error)
	Ready() error
}

// Refresher exchanges the session cookie for a fresh access token and writes the
// new cookies on w. It returns the token, or a status to deny with; status 0 with
// an empty token means "continue as anonymous".
type Refresher interface {
	Refresh(w http.ResponseWriter, r *http.Request) (token string, status int)
}

// Config wires the edge.
type Config struct {
	File      *config.File
	Verifier  TokenVerifier
	Sealer    *session.Sealer
	Refresher Refresher
	BFF       http.Handler
	Admin     http.Handler
	Logger    *slog.Logger
	// DevHTTP accepts plain HTTP cookies in tests. Production never sets it.
	DevHTTP bool
}

// Server serves every host on the block.
type Server struct {
	file      *config.File
	router    *config.Router
	verifier  TokenVerifier
	sealer    *session.Sealer
	refresher Refresher
	bff       http.Handler
	admin     http.Handler
	log       *slog.Logger
	devHTTP   bool
	proxy     *proxy
	limiter   *limiter
	metrics   *metrics
}

// New builds the server. A broken configuration is a startup error.
func New(cfg Config) (*Server, error) {
	if cfg.File == nil {
		return nil, fmt.Errorf("config is required")
	}
	if cfg.Verifier == nil {
		return nil, fmt.Errorf("verifier is required")
	}
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	s := &Server{
		file:      cfg.File,
		router:    cfg.File.Router(),
		verifier:  cfg.Verifier,
		sealer:    cfg.Sealer,
		refresher: cfg.Refresher,
		bff:       cfg.BFF,
		admin:     cfg.Admin,
		log:       cfg.Logger,
		devHTTP:   cfg.DevHTTP,
		limiter:   newLimiter(cfg.File.Defaults.RateLimit.Requests, cfg.File.Defaults.RateLimit.Per.D()),
		metrics:   newMetrics(),
	}
	s.proxy = newProxy(s)
	return s, nil
}

// Handler returns the whole edge.
func (s *Server) Handler() http.Handler { return http.HandlerFunc(s.serve) }

// Counters is the metric surface the BFF writes to.
type Counters interface {
	Refresh(result string)
	IdP(op string, status int)
}

// Counters exposes the process counters, so the BFF and the edge report into one
// registry and /metrics shows both.
func (s *Server) Counters() Counters { return s.metrics }

// SetBFF mounts the /auth handler after both halves exist.
func (s *Server) SetBFF(h http.Handler) { s.bff = h }

// SetRefresher mounts the refresh hook after the BFF exists.
func (s *Server) SetRefresher(r Refresher) { s.refresher = r }

// MetricsHandler is the second listener: /metrics and nothing else.
func (s *Server) MetricsHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/metrics" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(s.metrics.render())
	})
}

func (s *Server) serve(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	// Probes answer on any Host: a container healthcheck sends 127.0.0.1, and
	// /readyz must work before the first certificate exists.
	block := s.router.HostBlock(r.Host)
	if s.probe(w, r, block) {
		return
	}
	if block == nil {
		s.writeError(w, http.StatusNotFound, "not_found")
		return
	}
	if !s.limiter.allow(clientIP(r)) {
		s.metrics.count(block.Name, "rate_limit", "-", http.StatusTooManyRequests)
		s.writeError(w, http.StatusTooManyRequests, "rate_limited")
		return
	}
	route, ok := s.match(block, r)
	if !ok {
		s.writeError(w, http.StatusNotFound, "not_found")
		return
	}
	// A `deny` route is indistinguishable from a missing one: no route, no login
	// prompt, no hint that something lives here.
	if route.Policy.Kind == policy.Deny {
		s.writeError(w, http.StatusNotFound, "not_found")
		return
	}
	id, access := s.identity(r)
	if route.BFF {
		if s.bff == nil {
			s.writeError(w, http.StatusNotFound, "not_found")
			return
		}
		s.bff.ServeHTTP(w, withIdentity(r, id, access))
		return
	}
	if route.Admin {
		if id != nil && !policy.Blocked(id, block.Service) && route.Policy.Allow(id) {
			s.admin.ServeHTTP(w, withIdentity(r, id, access))
			return
		}
		s.deny(w, r, block, route, id)
		return
	}
	if id == nil && route.Policy.Kind != policy.Public && s.refresher != nil {
		if token, status := s.refresher.Refresh(w, r); token != "" {
			access = token
			if verified, err := s.verifier.Verify(r.Context(), token); err == nil {
				id = verified
			}
		} else if status > 0 {
			s.metrics.count(block.Name, route.Path, route.Policy.Original, status)
			s.writeError(w, status, statusText(status))
			return
		}
	}
	if policy.Blocked(id, block.Service) {
		s.metrics.count(block.Name, route.Path, route.Policy.Original, http.StatusForbidden)
		s.writeError(w, http.StatusForbidden, "blocked")
		return
	}
	if !route.Policy.Allow(id) {
		s.deny(w, r, block, route, id)
		return
	}
	s.forward(w, r, block, route, id, access, start)
}

func (s *Server) match(block *config.Block, r *http.Request) (*config.Compiled, bool) {
	_, route, ok := s.router.Match(r.Host, r.Method, r.URL.Path)
	if !ok || route == nil {
		return nil, false
	}
	return route, true
}

// deny answers anonymous callers with a redirect for a browser and JSON for an
// API client, and signed-in callers with 403.
func (s *Server) deny(w http.ResponseWriter, r *http.Request, block *config.Block, route *config.Compiled, id *oidc.Identity) {
	status := http.StatusForbidden
	body := "forbidden"
	if id == nil {
		status, body = http.StatusUnauthorized, "unauthorized"
		if wantsJSON(r) {
			s.metrics.count(block.Name, route.Path, route.Policy.Original, status)
			s.writeError(w, status, body)
			return
		}
		status = http.StatusFound
		applySecurityHeaders(w.Header(), "", true)
		http.Redirect(w, r, s.loginURL(r), http.StatusFound)
		s.metrics.count(block.Name, route.Path, route.Policy.Original, status)
		return
	}
	s.metrics.count(block.Name, route.Path, route.Policy.Original, status)
	s.writeError(w, status, body)
}

func (s *Server) loginURL(r *http.Request) string {
	origin := strings.TrimRight(s.file.PublicOrigin, "/")
	return origin + "/auth/login?return_to=" + url.QueryEscape(s.returnTo(r))
}

// returnTo is the request URL, limited to a host this block serves.
func (s *Server) returnTo(r *http.Request) string {
	scheme := "https"
	if s.devHTTP {
		scheme = "http"
	}
	raw := scheme + "://" + r.Host + r.URL.RequestURI()
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return s.file.PublicOrigin
	}
	if !s.file.AllowsHost(u.Host) {
		return s.file.PublicOrigin
	}
	if u.Scheme != "https" && !s.devHTTP {
		return s.file.PublicOrigin
	}
	return u.String()
}

// identity verifies the access cookie. A missing or invalid token is anonymous,
// never an error for a public route.
func (s *Server) identity(r *http.Request) (*oidc.Identity, string) {
	raw := session.Value(r, session.NameAccess)
	if raw == "" {
		return nil, ""
	}
	id, err := s.verifier.Verify(r.Context(), raw)
	if err != nil {
		return nil, ""
	}
	return id, raw
}

func wantsJSON(r *http.Request) bool {
	p := r.URL.Path
	if strings.HasPrefix(p, "/api/") || p == "/api" || strings.HasPrefix(p, "/users") {
		return true
	}
	if r.Header.Get("X-Requested-With") != "" {
		return true
	}
	if strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
		return true
	}
	return strings.Contains(strings.ToLower(r.Header.Get("Accept")), "application/json")
}

func statusText(status int) string {
	switch status {
	case http.StatusUnauthorized:
		return "unauthorized"
	case http.StatusForbidden:
		return "blocked"
	case http.StatusServiceUnavailable:
		return "auth_unavailable"
	default:
		return "unauthorized"
	}
}

func (s *Server) writeError(w http.ResponseWriter, status int, value string) {
	applySecurityHeaders(w.Header(), "", true)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(`{"error":"` + value + `"}`))
}

func clientIP(r *http.Request) string {
	if fwd := r.Header.Get("X-Forwarded-For"); fwd != "" {
		if i := strings.IndexByte(fwd, ','); i >= 0 {
			return strings.TrimSpace(fwd[:i])
		}
		return strings.TrimSpace(fwd)
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

// timeoutStatus keeps a deadline honest: a slow upstream is 504, a dead one 502.
func timeoutStatus(err error) (int, string) {
	if errors.Is(err, context.DeadlineExceeded) {
		return http.StatusGatewayTimeout, "gateway_timeout"
	}
	var ne net.Error
	if errors.As(err, &ne) && ne.Timeout() {
		return http.StatusGatewayTimeout, "gateway_timeout"
	}
	return http.StatusBadGateway, "bad_gateway"
}
