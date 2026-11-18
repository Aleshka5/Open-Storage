package edge

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httputil"
	"strings"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
)

type targetKey struct{}

// target is the resolved request: one block, one route, one identity.
type target struct {
	block  *config.Block
	route  *config.Compiled
	id     *oidc.Identity
	access string
}

func withTarget(r *http.Request, t *target) *http.Request {
	return r.WithContext(context.WithValue(r.Context(), targetKey{}, t))
}

func targetOf(r *http.Request) *target {
	t, _ := r.Context().Value(targetKey{}).(*target)
	return t
}

// withIdentity carries the verified identity to the in-process handlers.
func withIdentity(r *http.Request, id *oidc.Identity, access string) *http.Request {
	if id == nil {
		return r
	}
	return r.WithContext(oidc.WithIdentity(r.Context(), id))
}

type proxy struct {
	server     *Server
	transports map[time.Duration]*http.Transport
	fallback   *http.Transport
	rp         *httputil.ReverseProxy
}

func newProxy(s *Server) *proxy {
	p := &proxy{server: s, transports: make(map[time.Duration]*http.Transport)}
	add := func(d time.Duration) *http.Transport {
		if d <= 0 {
			d = 60 * time.Second
		}
		if t, ok := p.transports[d]; ok {
			return t
		}
		t := &http.Transport{
			Proxy: nil,
			DialContext: (&net.Dialer{
				Timeout:   s.file.Defaults.Timeouts.Connect.D(),
				KeepAlive: 30 * time.Second,
			}).DialContext,
			MaxIdleConnsPerHost:   32,
			IdleConnTimeout:       120 * time.Second,
			ResponseHeaderTimeout: d,
			// HTTP/2 toward upstreams breaks the WebSocket upgrade.
			ForceAttemptHTTP2: false,
		}
		p.transports[d] = t
		return t
	}
	p.fallback = add(s.file.Defaults.Timeouts.ResponseHeader.D())
	for i := range s.file.Hosts {
		h := &s.file.Hosts[i]
		if h.Timeouts != nil {
			add(config.MergeTimeouts(s.file.Defaults.Timeouts, h.Timeouts).ResponseHeader)
		}
		for j := range h.Routes {
			if h.Routes[j].Timeouts != nil {
				add(config.MergeTimeouts(s.file.Defaults.Timeouts, h.Routes[j].Timeouts).ResponseHeader)
			}
		}
	}
	p.rp = &httputil.ReverseProxy{
		// -1 streams SSE and token deltas as they arrive instead of buffering.
		FlushInterval: -1,
		Transport:     transportFor{p: p},
		Rewrite: func(pr *httputil.ProxyRequest) {
			t := targetOf(pr.In)
			if t == nil || t.route == nil || t.route.Upstream == nil {
				return
			}
			pr.SetURL(t.route.Upstream)
			if t.route.StripPrefix != "" {
				pr.Out.URL.Path = config.StripPath(pr.In.URL.Path, t.route.StripPrefix)
				pr.Out.URL.RawPath = ""
			}
			pr.SetXForwarded()
			if proto := forwardedProto(pr.In, s.devHTTP); proto != "" {
				pr.Out.Header.Set("X-Forwarded-Proto", proto)
			}
			// A client never supplies its own identity, and never overrides a
			// config header: strip first, then set.
			stripInboundIdentity(pr.Out.Header)
			for name, value := range t.route.Headers {
				pr.Out.Header.Set(name, value)
			}
			injectIdentity(pr.Out.Header, t.id, t.access)
		},
		ModifyResponse: func(resp *http.Response) error {
			if resp == nil {
				return nil
			}
			// Security headers on the handshake break the upgrade.
			if resp.StatusCode == http.StatusSwitchingProtocols {
				return nil
			}
			t := targetOf(resp.Request)
			if t == nil || t.block == nil {
				return nil
			}
			applySecurityHeaders(resp.Header, t.block.PermissionsPolicy, denyFraming(t.block.Name))
			return nil
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			status, value := timeoutStatus(err)
			s.log.Warn("gateway_upstream", "err", err, "host", r.Host, "path", r.URL.Path)
			s.writeError(w, status, value)
		},
	}
	return p
}

// transportFor picks the transport whose response-header timeout the matched
// route declared.
type transportFor struct{ p *proxy }

func (t transportFor) RoundTrip(r *http.Request) (*http.Response, error) {
	timeout := t.p.server.file.Defaults.Timeouts.ResponseHeader.D()
	if tg := targetOf(r); tg != nil && tg.route != nil {
		timeout = tg.route.Timeouts.ResponseHeader
	}
	if tr, ok := t.p.transports[timeout]; ok {
		return tr.RoundTrip(r)
	}
	return t.p.fallback.RoundTrip(r)
}

func (s *Server) forward(w http.ResponseWriter, r *http.Request, block *config.Block, route *config.Compiled, id *oidc.Identity, access string, start time.Time) {
	sw := &statusWriter{ResponseWriter: w}
	if isWebSocket(r) {
		s.metrics.wsDelta(block.Name, 1)
		defer s.metrics.wsDelta(block.Name, -1)
	}
	t := &target{block: block, route: route, id: id, access: access}
	s.proxy.rp.ServeHTTP(sw, withTarget(r, t))
	s.metrics.count(block.Name, route.Path, route.Policy.Original, sw.statusOr(http.StatusOK))
	s.metrics.observe(block.Name, route.Path, time.Since(start))
	s.log.Info("gateway_request",
		"ts", start.UTC().Format(time.RFC3339Nano),
		"host", block.Name,
		"method", r.Method,
		"path", r.URL.Path,
		"route", route.Path,
		"policy", route.Policy.Original,
		"status", sw.statusOr(http.StatusOK),
		"dur_ms", time.Since(start).Milliseconds(),
		"sub", subjectOf(id),
		"ip", clientIP(r),
		"ua", r.UserAgent(),
	)
}

// isWebSocket reports an upgrade request.
func isWebSocket(r *http.Request) bool {
	return strings.EqualFold(r.Header.Get("Upgrade"), "websocket")
}

func subjectOf(id *oidc.Identity) string {
	if id == nil {
		return ""
	}
	return id.Subject
}

func forwardedProto(r *http.Request, devHTTP bool) string {
	if v := r.Header.Get("X-Forwarded-Proto"); v != "" {
		return v
	}
	if r.TLS != nil {
		return "https"
	}
	if devHTTP {
		return "http"
	}
	return "https"
}

// stripInboundIdentity removes every name a client could use to claim an
// identity, with no exception.
func stripInboundIdentity(h http.Header) {
	for name := range h {
		lower := strings.ToLower(name)
		switch {
		case strings.HasPrefix(lower, "x-auth-"):
			h.Del(name)
		case lower == "x-user-id", lower == "x-storage-role", lower == "x-original-user":
			h.Del(name)
		}
	}
}

// injectIdentity sets identity v1. An empty header is omitted, not sent empty.
func injectIdentity(h http.Header, id *oidc.Identity, access string) {
	if id == nil {
		return
	}
	if access != "" {
		h.Set("Authorization", "Bearer "+access)
	}
	h.Set("X-Auth-Subject", id.Subject)
	if id.Email != "" {
		h.Set("X-Auth-Email", id.Email)
	}
	if id.Name != "" {
		h.Set("X-Auth-Name", id.Name)
	}
	if roles := id.RoleHeader(); roles != "" {
		h.Set("X-Auth-Roles", roles)
	}
	if id.SID != "" {
		h.Set("X-Auth-Session", id.SID)
	}
}

const defaultPermissionsPolicy = "camera=(), microphone=(), geolocation=()"

func applySecurityHeaders(h http.Header, permissionsPolicy string, denyFrame bool) {
	h.Set("X-Content-Type-Options", "nosniff")
	h.Set("Referrer-Policy", "strict-origin-when-cross-origin")
	if denyFrame {
		h.Set("X-Frame-Options", "DENY")
	}
	policy := strings.TrimSpace(permissionsPolicy)
	if policy == "" {
		policy = defaultPermissionsPolicy
	}
	h.Set("Permissions-Policy", policy)
}

// denyFraming is false for the hosts whose own UI frames itself.
func denyFraming(host string) bool {
	return !strings.HasPrefix(host, "meet.") && !strings.HasPrefix(host, "audio.")
}

// probe answers the gateway's own probes. A host that routes a literal /healthz
// keeps it: image.filenkov.store answers with its own app health.
func (s *Server) probe(w http.ResponseWriter, r *http.Request, block *config.Block) bool {
	if r.Method != http.MethodGet {
		return false
	}
	switch r.URL.Path {
	case "/healthz":
		if s.hostOwnsPath(block, "/healthz") {
			return false
		}
		s.writeJSON(w, http.StatusOK, `{"status":"ok"}`)
		return true
	case "/readyz":
		if err := s.verifier.Ready(); err != nil {
			s.writeError(w, http.StatusServiceUnavailable, "auth_unavailable")
			return true
		}
		s.writeJSON(w, http.StatusOK, `{"status":"ready"}`)
		return true
	case "/metrics":
		// The public listener never serves metrics: they belong to a second
		// listener that only the host loopback publishes.
		s.writeError(w, http.StatusNotFound, "not_found")
		return true
	}
	return false
}

func (s *Server) hostOwnsPath(block *config.Block, path string) bool {
	if block == nil {
		return false
	}
	for i := range block.Routes {
		if block.Routes[i].Path == path {
			return true
		}
	}
	return false
}

func (s *Server) writeJSON(w http.ResponseWriter, status int, body string) {
	applySecurityHeaders(w.Header(), "", true)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(body))
}

// statusWriter keeps the status and stays hijackable, so the WebSocket upgrade
// and the SSE flush survive the wrapper.
type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	if w.status == 0 {
		w.status = code
	}
	w.ResponseWriter.WriteHeader(code)
}

func (w *statusWriter) Write(b []byte) (int, error) {
	if w.status == 0 {
		w.status = http.StatusOK
	}
	return w.ResponseWriter.Write(b)
}

func (w *statusWriter) statusOr(fallback int) int {
	if w.status == 0 {
		return fallback
	}
	return w.status
}

func (w *statusWriter) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	h, ok := w.ResponseWriter.(http.Hijacker)
	if !ok {
		return nil, nil, fmt.Errorf("upstream asked for a hijack but the writer cannot")
	}
	w.status = http.StatusSwitchingProtocols
	return h.Hijack()
}

func (w *statusWriter) Flush() {
	if f, ok := w.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

func (w *statusWriter) Unwrap() http.ResponseWriter { return w.ResponseWriter }
