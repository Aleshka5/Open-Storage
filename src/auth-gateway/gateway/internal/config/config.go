// Package config owns the gateway configuration file. It is read once at start,
// validated, and never re-read: a change is a restart (ADR-0004). The shape and
// the eight startup rules are owned by the gateway message contract.
package config

import (
	"bytes"
	"fmt"
	"net/url"
	"os"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	"github.com/aleshka5/open-storage/auth-gateway/internal/policy"
)

// Duration accepts a Go duration string in YAML.
type Duration time.Duration

func (d *Duration) UnmarshalYAML(v *yaml.Node) error {
	var raw string
	if err := v.Decode(&raw); err != nil {
		return err
	}
	raw = strings.TrimSpace(raw)
	if raw == "" {
		*d = 0
		return nil
	}
	parsed, err := time.ParseDuration(raw)
	if err != nil {
		return err
	}
	if parsed < 0 {
		return fmt.Errorf("duration must not be negative")
	}
	*d = Duration(parsed)
	return nil
}

// D returns the value as a standard duration.
func (d Duration) D() time.Duration { return time.Duration(d) }

// Trimmed is the smallest set of values the proxy and the BFF need.
type Trimmed struct {
	Connect        time.Duration
	ReadHeader     time.Duration
	ResponseHeader time.Duration
	Idle           time.Duration
}

// File is the on-disk configuration.
type File struct {
	Listen       string            `yaml:"listen"`
	PublicOrigin string            `yaml:"public_origin"`
	IdP          IdP               `yaml:"idp"`
	Session      Session           `yaml:"session"`
	Admin        Admin             `yaml:"admin"`
	Services     []string          `yaml:"services"`
	Defaults     Defaults          `yaml:"defaults"`
	Upstreams    map[string]string `yaml:"upstreams"`
	LLM          LLM               `yaml:"llm"`
	Hosts        []Host            `yaml:"hosts"`

	secrets Secrets
	router  *Router
}

// IdP is the identity provider block.
type IdP struct {
	Issuer string `yaml:"issuer"`
	// InternalURL is where this process reaches the idp, when that differs from
	// the public issuer. Server-side calls (discovery, JWKS, token, logout, the
	// admin API) use it; the browser still sees the public endpoints, and `iss`
	// stays the public issuer. Empty means "use the issuer".
	InternalURL     string   `yaml:"internal_url"`
	ClientID        string   `yaml:"client_id"`
	ClientSecretRef string   `yaml:"client_secret"`
	Scopes          []string `yaml:"scopes"`
	Audience        string   `yaml:"audience"`
	AuthorizedParty string   `yaml:"authorized_party"`
	JWKSTTL         Duration `yaml:"jwks_ttl"`
}

// Session is the sealed cookie block.
type Session struct {
	CookieDomain string   `yaml:"cookie_domain"`
	AccessTTL    Duration `yaml:"access_ttl"`
	IdleTTL      Duration `yaml:"idle_ttl"`
	KeyRef       string   `yaml:"key"`
}

// Admin is the Keycloak service account used by /admin.
type Admin struct {
	ClientID        string `yaml:"client_id"`
	ClientSecretRef string `yaml:"client_secret"`
}

// Defaults apply to every host unless it overrides them.
type Defaults struct {
	Timeouts  Timeouts  `yaml:"timeouts"`
	RateLimit RateLimit `yaml:"rate_limit"`
}

// Timeouts are per-hop waits. ResponseHeader is time to the first response byte,
// not the life of a body.
type Timeouts struct {
	Connect        Duration `yaml:"connect"`
	ReadHeader     Duration `yaml:"read_header"`
	ResponseHeader Duration `yaml:"response_header"`
	Idle           Duration `yaml:"idle"`
}

// RateLimit is an in-process counter per client IP.
type RateLimit struct {
	Requests int      `yaml:"requests"`
	Per      Duration `yaml:"per"`
}

// Host is one site on the block.
type Host struct {
	Host     string   `yaml:"host"`
	Upstream string   `yaml:"upstream"`
	Aliases  []string `yaml:"aliases"`
	Service  string   `yaml:"service"`
	// Frame is `deny` (default) or `self`: an app that frames its own UI must
	// not be sent X-Frame-Options: DENY.
	Frame string `yaml:"frame"`
	// Identity is `inject` (default) or `passthrough`. A passthrough host is not
	// an application under identity v1 — the idp's own console is the only one —
	// so its `Authorization` and `X-Auth-*` headers are neither stripped nor
	// written: the client's own bearer is what the upstream needs.
	Identity          string    `yaml:"identity"`
	PermissionsPolicy string    `yaml:"permissions_policy"`
	Timeouts          *Timeouts `yaml:"timeouts"`
	Routes            []Route   `yaml:"routes"`
}

// Route is one host+path+method rule.
type Route struct {
	Path        string   `yaml:"path"`
	Methods     []string `yaml:"methods"`
	Policy      string   `yaml:"policy"`
	Upstream    string   `yaml:"upstream"`
	StripPrefix string   `yaml:"strip_prefix"`
	BFF         bool     `yaml:"bff"`
	Admin       bool     `yaml:"admin"`
	// Chat serves the owl's question in this process (POST /api/chat). It takes
	// no upstream: the model host comes from `llm`, which needs a prompt and a
	// node map that a route table cannot carry.
	Chat          bool              `yaml:"chat"`
	InjectHeaders map[string]string `yaml:"inject_headers"`
	Timeouts      *Timeouts         `yaml:"timeouts"`
}

// LLM is the owl's model endpoint. Every field is optional: an incomplete block
// leaves POST /api/chat answering 503 and the rest of the edge untouched, because
// the chat is not load-bearing for sign-in.
type LLM struct {
	// Host is the OpenAI-compatible base URL, e.g. http://litellm-proxy-server:4000/v1
	Host   string `yaml:"host"`
	APIKey string `yaml:"api_key"`
	Model  string `yaml:"model"`
	// ReasoningEffort is sent as `reasoning_effort`; "none" keeps a reasoning
	// model from thinking before a two-sentence answer.
	ReasoningEffort string   `yaml:"reasoning_effort"`
	Timeout         Duration `yaml:"timeout"`
}

// Secrets are the resolved values of every `env:NAME` reference.
type Secrets struct {
	IdPClient   string
	AdminClient string
	SessionKey  string
	LLMAPIKey   string
}

// Block is a compiled host.
type Block struct {
	Name     string
	Upstream *url.URL
	Service  string
	// FrameDeny is true unless the host declares `frame: self`.
	FrameDeny bool
	// IdentityPass is true for a host that is not an application under identity
	// v1: headers are forwarded untouched and nothing is injected.
	IdentityPass      bool
	PermissionsPolicy string
	Timeouts          Trimmed
	Routes            []Compiled
}

// Compiled is a compiled route.
type Compiled struct {
	Path        string
	Methods     []string
	Policy      policy.Policy
	Upstream    *url.URL
	StripPrefix string
	BFF         bool
	Admin       bool
	// Chat is served in this process by the gateway's own handler.
	Chat     bool
	Headers  map[string]string
	Timeouts Trimmed
}

// Router is a validated host+path lookup table. First matching route wins.
type Router struct {
	file  *File
	hosts map[string]*Block
}

// Parse decodes and compiles. Environment references stay unresolved: call
// ResolveEnv before serving, or Load does both.
func Parse(data []byte) (*File, error) {
	var f File
	dec := yaml.NewDecoder(bytes.NewReader(data))
	if err := dec.Decode(&f); err != nil {
		return nil, err
	}
	f.applyDefaults()
	if err := f.compile(); err != nil {
		return nil, err
	}
	return &f, nil
}

// Load reads, compiles, and resolves the file. An unset variable fails startup.
func Load(path string) (*File, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	f, err := Parse(data)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if err := f.ResolveEnv(os.LookupEnv); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return f, nil
}

func (f *File) applyDefaults() {
	if strings.TrimSpace(f.Listen) == "" {
		f.Listen = ":8080"
	}
	if f.IdP.JWKSTTL == 0 {
		f.IdP.JWKSTTL = Duration(15 * time.Minute)
	}
	if len(f.IdP.Scopes) == 0 {
		f.IdP.Scopes = []string{"openid", "profile", "email"}
	}
	if f.IdP.Audience == "" {
		f.IdP.Audience = "account"
	}
	if f.IdP.AuthorizedParty == "" {
		f.IdP.AuthorizedParty = "gateway"
	}
	if f.Session.AccessTTL == 0 {
		f.Session.AccessTTL = Duration(5 * time.Minute)
	}
	if f.Session.IdleTTL == 0 {
		f.Session.IdleTTL = Duration(168 * time.Hour)
	}
	d := &f.Defaults.Timeouts
	if d.Connect == 0 {
		d.Connect = Duration(5 * time.Second)
	}
	if d.ReadHeader == 0 {
		d.ReadHeader = Duration(15 * time.Second)
	}
	if d.ResponseHeader == 0 {
		d.ResponseHeader = Duration(60 * time.Second)
	}
	if d.Idle == 0 {
		d.Idle = Duration(120 * time.Second)
	}
	if f.Defaults.RateLimit.Requests == 0 {
		f.Defaults.RateLimit.Requests = 600
	}
	if f.Defaults.RateLimit.Per == 0 {
		f.Defaults.RateLimit.Per = Duration(time.Minute)
	}
	if f.Upstreams == nil {
		f.Upstreams = map[string]string{}
	}
}

func (f *File) compile() error {
	if strings.TrimSpace(f.PublicOrigin) == "" {
		return fmt.Errorf("public_origin is required")
	}
	origin, err := url.Parse(f.PublicOrigin)
	if err != nil || origin.Host == "" || origin.Scheme != "https" {
		return fmt.Errorf("public_origin must be an https URL")
	}
	if strings.TrimSpace(f.IdP.Issuer) == "" || f.IdP.ClientID == "" {
		return fmt.Errorf("idp.issuer and idp.client_id are required")
	}
	if raw := strings.TrimSpace(f.IdP.InternalURL); raw != "" {
		u, err := url.Parse(raw)
		if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") {
			return fmt.Errorf("idp.internal_url must be an absolute http or https URL")
		}
		if _, err := url.ParseRequestURI(strings.TrimRight(raw, "/") + "/.well-known/openid-configuration"); err != nil {
			return fmt.Errorf("idp.internal_url %q cannot carry a discovery path", raw)
		}
		f.IdP.InternalURL = strings.TrimRight(raw, "/")
	}
	if _, err := envRef("idp.client_secret", f.IdP.ClientSecretRef); err != nil {
		return err
	}
	if _, err := envRef("session.key", f.Session.KeyRef); err != nil {
		return err
	}
	if f.Admin.ClientID != "" {
		if _, err := envRef("admin.client_secret", f.Admin.ClientSecretRef); err != nil {
			return err
		}
	}
	if len(f.Services) == 0 {
		return fmt.Errorf("services is required")
	}
	if len(f.Hosts) == 0 {
		return fmt.Errorf("hosts: at least one host is required")
	}
	r := &Router{file: f, hosts: make(map[string]*Block, len(f.Hosts))}
	for i := range f.Hosts {
		b, err := f.compileHost(&f.Hosts[i], i)
		if err != nil {
			return err
		}
		names := append([]string{b.Name}, f.Hosts[i].Aliases...)
		for _, raw := range names {
			name := NormalizeHost(raw)
			if name == "" {
				return fmt.Errorf("hosts[%d]: empty hostname", i)
			}
			if _, taken := r.hosts[name]; taken {
				return fmt.Errorf("hosts[%d]: host or alias %q is declared twice", i, name)
			}
			r.hosts[name] = b
		}
	}
	f.router = r
	return nil
}

func (f *File) compileHost(h *Host, i int) (*Block, error) {
	prefix := fmt.Sprintf("hosts[%d]", i)
	name := NormalizeHost(h.Host)
	if name == "" {
		return nil, fmt.Errorf("%s: host is required", prefix)
	}
	prefix = "hosts." + name
	upstream, ok := f.upstream(h.Upstream)
	if !ok {
		return nil, fmt.Errorf("%s: upstream %q is not declared", prefix, h.Upstream)
	}
	if h.Service != "" && !contains(f.Services, h.Service) {
		return nil, fmt.Errorf("%s: service %q is not in services", prefix, h.Service)
	}
	b := &Block{Name: name, Upstream: upstream, Service: h.Service, PermissionsPolicy: strings.TrimSpace(h.PermissionsPolicy)}
	switch frame := strings.ToLower(strings.TrimSpace(h.Frame)); frame {
	case "", "deny":
		b.FrameDeny = true
	case "self":
		b.FrameDeny = false
	default:
		return nil, fmt.Errorf("%s: frame %q must be deny or self", prefix, h.Frame)
	}
	switch identity := strings.ToLower(strings.TrimSpace(h.Identity)); identity {
	case "", "inject":
		b.IdentityPass = false
	case "passthrough":
		b.IdentityPass = true
	default:
		return nil, fmt.Errorf("%s: identity %q must be inject or passthrough", prefix, h.Identity)
	}
	b.Timeouts = mergeTimeouts(f.Defaults.Timeouts, h.Timeouts)
	if len(h.Routes) == 0 {
		return nil, fmt.Errorf("%s: at least one route is required", prefix)
	}
	// Rule 1 and 2: exactly one /**, and nothing after it.
	catchAll := -1
	for j, rt := range h.Routes {
		if strings.TrimSpace(rt.Path) == "/**" {
			if catchAll >= 0 {
				return nil, fmt.Errorf("%s: a second /%s after route %d", prefix, "**", catchAll)
			}
			catchAll = j
		}
	}
	if catchAll < 0 {
		return nil, fmt.Errorf("%s: a /** route is required", prefix)
	}
	if catchAll != len(h.Routes)-1 {
		return nil, fmt.Errorf("%s: /** must be the last route", prefix)
	}
	seen := make([]Compiled, 0, len(h.Routes))
	hostTimeouts := mergeTimeouts(f.Defaults.Timeouts, h.Timeouts)
	for j := range h.Routes {
		c, err := f.compileRoute(prefix, &h.Routes[j], j, hostTimeouts)
		if err != nil {
			return nil, err
		}
		// A route that names no upstream uses its host's, which is the common case.
		if c.Upstream == nil && !c.BFF && !c.Admin {
			c.Upstream = b.Upstream
		}
		// Rule 3: no two routes with the same path and overlapping methods.
		for k := range seen {
			if seen[k].Path == c.Path && methodsOverlap(seen[k].Methods, c.Methods) {
				return nil, fmt.Errorf("%s.routes[%d]: duplicates route %d (%s)", prefix, j, k, c.Path)
			}
		}
		seen = append(seen, c)
	}
	b.Routes = seen
	return b, nil
}

func (f *File) compileRoute(host string, rt *Route, i int, hostTimeouts Trimmed) (Compiled, error) {
	prefix := fmt.Sprintf("%s.routes[%d]", host, i)
	path := strings.TrimSpace(rt.Path)
	if !strings.HasPrefix(path, "/") {
		return Compiled{}, fmt.Errorf("%s: path %q must start with /", prefix, path)
	}
	c := Compiled{Path: path, StripPrefix: strings.TrimSpace(rt.StripPrefix), BFF: rt.BFF, Admin: rt.Admin}
	c.Methods, _ = normalizeMethods(rt.Methods)
	// A route inherits the host's timeouts, which inherit the defaults.
	c.Timeouts = mergeTrimmed(hostTimeouts, rt.Timeouts)
	if path != "/**" && strings.Contains(path, "*") && !strings.HasSuffix(path, "/**") {
		return Compiled{}, fmt.Errorf("%s: path %q: only a literal, /prefix/**, or /**", prefix, path)
	}
	if c.StripPrefix != "" {
		if !strings.HasPrefix(c.StripPrefix, "/") || c.StripPrefix == "/" {
			return Compiled{}, fmt.Errorf("%s: strip_prefix %q must start with / and keep a path", prefix, c.StripPrefix)
		}
		if path == c.StripPrefix {
			return Compiled{}, fmt.Errorf("%s: strip_prefix leaves an empty path", prefix)
		}
	}
	// BFF and admin routes are served in this process and handle their own
	// authentication; every other route must state a policy.
	if !rt.BFF {
		p, err := policy.Parse(rt.Policy, f.Services)
		if err != nil {
			return Compiled{}, fmt.Errorf("%s: %w", prefix, err)
		}
		c.Policy = p
	}
	if rt.Upstream != "" {
		up, ok := f.upstream(rt.Upstream)
		if !ok {
			return Compiled{}, fmt.Errorf("%s: upstream %q is not declared", prefix, rt.Upstream)
		}
		c.Upstream = up
	}
	// `chat` without an upstream serves the request in this process; with one,
	// the rule would mean two things at once and one of them would silently win.
	c.Chat = rt.Chat
	if rt.Chat && rt.Upstream != "" {
		return Compiled{}, fmt.Errorf("%s: chat and upstream are exclusive", prefix)
	}
	headers, err := compileHeaders(prefix, rt.InjectHeaders)
	if err != nil {
		return Compiled{}, err
	}
	c.Headers = headers
	return c, nil
}

// compileHeaders resolves `env:NAME` and refuses a literal that looks like a
// secret. The file is in git; a token in it is a defect.
func compileHeaders(prefix string, raw map[string]string) (map[string]string, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	out := make(map[string]string, len(raw))
	for name, value := range raw {
		key := strings.TrimSpace(name)
		if key == "" || strings.ContainsAny(key, " :\t\r\n") {
			return nil, fmt.Errorf("%s: inject_headers: invalid name %q", prefix, name)
		}
		value = strings.TrimSpace(value)
		if strings.ContainsAny(value, "\r\n") {
			return nil, fmt.Errorf("%s: inject_headers.%s: must be one line", prefix, key)
		}
		if strings.HasPrefix(value, "env:") {
			if _, err := envRef(prefix+": inject_headers."+key, value); err != nil {
				return nil, err
			}
			out[key] = value
			continue
		}
		if looksSecret(key) {
			return nil, fmt.Errorf("%s: inject_headers.%s must be env:NAME", prefix, key)
		}
		out[key] = value
	}
	return out, nil
}

func (f *File) upstream(name string) (*url.URL, bool) {
	raw, ok := f.Upstreams[name]
	if !ok {
		return nil, false
	}
	return ParseUpstream(raw)
}

// ParseUpstream accepts "host:port" (http) and a full URL.
func ParseUpstream(raw string) (*url.URL, bool) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, false
	}
	if !strings.Contains(raw, "://") {
		raw = "http://" + raw
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return nil, false
	}
	return u, true
}

// ResolveEnv fills the secrets and the injected headers from the environment.
func (f *File) ResolveEnv(lookup func(string) (string, bool)) error {
	get := func(field, ref string) (string, error) {
		name, err := envRef(field, ref)
		if err != nil {
			return "", err
		}
		v, ok := lookup(name)
		if !ok || v == "" {
			return "", fmt.Errorf("%s: environment variable %s is not set", field, name)
		}
		return v, nil
	}
	var err error
	if f.secrets.IdPClient, err = get("idp.client_secret", f.IdP.ClientSecretRef); err != nil {
		return err
	}
	if f.secrets.SessionKey, err = get("session.key", f.Session.KeyRef); err != nil {
		return err
	}
	if f.Admin.ClientID != "" {
		if f.secrets.AdminClient, err = get("admin.client_secret", f.Admin.ClientSecretRef); err != nil {
			return err
		}
	}
	// The owl's key is optional: without it the chat answers 503 and nothing
	// else changes. A key that is written as env:NAME-but-unset is the same case.
	if ref := strings.TrimSpace(f.LLM.APIKey); strings.HasPrefix(ref, "env:") {
		name, err := envRef("llm.api_key", ref)
		if err != nil {
			return err
		}
		if v, ok := lookup(name); ok {
			f.secrets.LLMAPIKey = v
		}
	}
	for _, b := range f.router.hosts {
		for i := range b.Routes {
			for name, value := range b.Routes[i].Headers {
				if !strings.HasPrefix(value, "env:") {
					continue
				}
				v, err := get("inject_headers."+name, value)
				if err != nil {
					return err
				}
				b.Routes[i].Headers[name] = v
			}
		}
	}
	return nil
}

// Secrets returns the resolved secret values.
func (f *File) Secrets() Secrets { return f.secrets }

// Router returns the compiled lookup table.
func (f *File) Router() *Router { return f.router }

// Hostnames is the return_to allowlist: every declared name and alias.
func (f *File) Hostnames() []string {
	out := make([]string, 0, len(f.router.hosts))
	for name := range f.router.hosts {
		out = append(out, name)
	}
	return out
}

// AllowsHost reports whether a host may be used as return_to.
func (f *File) AllowsHost(host string) bool {
	_, ok := f.router.hosts[NormalizeHost(host)]
	return ok
}

// NormalizeHost lowercases a Host header and drops any port.
func NormalizeHost(raw string) string {
	raw = strings.TrimSpace(strings.ToLower(raw))
	if i := strings.IndexByte(raw, ':'); i >= 0 {
		raw = raw[:i]
	}
	return strings.TrimSuffix(raw, ".")
}

// MergeTimeouts exposes the host+default merge for the edge.
func MergeTimeouts(def Timeouts, override *Timeouts) Trimmed { return mergeTimeouts(def, override) }

func mergeTimeouts(def Timeouts, override *Timeouts) Trimmed {
	t := Trimmed{
		Connect:        pick(def.Connect, 0),
		ReadHeader:     pick(def.ReadHeader, 0),
		ResponseHeader: pick(def.ResponseHeader, 0),
		Idle:           pick(def.Idle, 0),
	}
	if override == nil {
		return t
	}
	t.Connect = pick(override.Connect, t.Connect)
	t.ReadHeader = pick(override.ReadHeader, t.ReadHeader)
	t.ResponseHeader = pick(override.ResponseHeader, t.ResponseHeader)
	t.Idle = pick(override.Idle, t.Idle)
	return t
}

// mergeTrimmed applies route-level overrides on top of the effective host values.
func mergeTrimmed(base Trimmed, override *Timeouts) Trimmed {
	if override == nil {
		return base
	}
	out := base
	if override.Connect > 0 {
		out.Connect = override.Connect.D()
	}
	if override.ReadHeader > 0 {
		out.ReadHeader = override.ReadHeader.D()
	}
	if override.ResponseHeader > 0 {
		out.ResponseHeader = override.ResponseHeader.D()
	}
	if override.Idle > 0 {
		out.Idle = override.Idle.D()
	}
	return out
}

func pick(v Duration, fallback time.Duration) time.Duration {
	if v > 0 {
		return v.D()
	}
	return fallback
}

func envRef(field, raw string) (string, error) {
	raw = strings.TrimSpace(raw)
	if !strings.HasPrefix(raw, "env:") || len(raw) == len("env:") {
		return "", fmt.Errorf("%s must be env:NAME (a secret does not live in this file)", field)
	}
	return strings.TrimPrefix(raw, "env:"), nil
}

func looksSecret(header string) bool {
	h := strings.ToLower(header)
	for _, marker := range []string{"token", "secret", "password", "api-key", "apikey", "authorization", "-key"} {
		if strings.Contains(h, marker) {
			return true
		}
	}
	return false
}

func normalizeMethods(raw []string) ([]string, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	out := make([]string, 0, len(raw))
	seen := map[string]struct{}{}
	for _, m := range raw {
		m = strings.ToUpper(strings.TrimSpace(m))
		if m == "" {
			continue
		}
		if _, dup := seen[m]; dup {
			continue
		}
		seen[m] = struct{}{}
		out = append(out, m)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("methods: empty after trim")
	}
	return out, nil
}

func methodsOverlap(a, b []string) bool {
	if len(a) == 0 || len(b) == 0 {
		return true
	}
	for _, x := range a {
		for _, y := range b {
			if x == y {
				return true
			}
		}
	}
	return false
}

func contains(list []string, want string) bool {
	for _, v := range list {
		if v == want {
			return true
		}
	}
	return false
}

// MatchPath reports whether a path pattern matches a request path: a literal,
// `/prefix/**`, or `/**`.
func MatchPath(pattern, path string) bool {
	if path == "" {
		path = "/"
	}
	if pattern == "/**" || pattern == "*" || pattern == "/*" {
		return true
	}
	if strings.HasSuffix(pattern, "/**") {
		prefix := strings.TrimSuffix(pattern, "/**")
		if prefix == "" {
			return true
		}
		return path == prefix || strings.HasPrefix(path, prefix+"/")
	}
	if strings.HasSuffix(pattern, "/*") {
		prefix := strings.TrimSuffix(pattern, "/*")
		if prefix == "" {
			return true
		}
		return path == prefix || strings.HasPrefix(path, prefix+"/")
	}
	return path == pattern
}

// StripPath removes a strip_prefix from a request path, keeping a leading /.
func StripPath(path, prefix string) string {
	if prefix == "" {
		return path
	}
	if path == prefix {
		return "/"
	}
	if strings.HasPrefix(path, prefix+"/") {
		return path[len(prefix):]
	}
	return path
}

// Match returns the first matching route for a Host header and request path.
func (r *Router) Match(host, method, path string) (*Block, *Compiled, bool) {
	if r == nil {
		return nil, nil, false
	}
	b := r.HostBlock(host)
	if b == nil {
		return nil, nil, false
	}
	for i := range b.Routes {
		c := &b.Routes[i]
		if !MatchPath(c.Path, path) {
			continue
		}
		if !matchMethods(c.Methods, method) {
			continue
		}
		return b, c, true
	}
	return b, nil, false
}

// HostBlock returns the block for a Host header, or nil for an unknown host.
func (r *Router) HostBlock(host string) *Block {
	if r == nil {
		return nil
	}
	return r.hosts[NormalizeHost(host)]
}

func matchMethods(allowed []string, method string) bool {
	if len(allowed) == 0 || method == "" {
		return true
	}
	method = strings.ToUpper(method)
	for _, m := range allowed {
		if m == method {
			return true
		}
	}
	return false
}
