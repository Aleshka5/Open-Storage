package config

import (
	"strings"
	"testing"
)

const header = `
listen: ":8080"
public_origin: "https://filenkov.store"
idp:
  issuer: "https://id.filenkov.store/realms/filenkov"
  client_id: gateway
  client_secret: "env:IDP_CLIENT_SECRET"
session:
  key: "env:GATEWAY_SESSION_KEY"
services: [storage]
defaults:
  timeouts: { connect: 5s, read_header: 15s, response_header: 60s, idle: 120s }
  rate_limit: { requests: 600, per: 1m }
upstreams:
  resume: "resume:80"
  app: "app:8000"
`

func parse(t *testing.T, hosts string) (*File, error) {
	t.Helper()
	return Parse([]byte(header + "hosts:\n" + hosts))
}

func mustParse(t *testing.T, hosts string) *File {
	t.Helper()
	f, err := parse(t, hosts)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	return f
}

func wantError(t *testing.T, hosts, contains string) {
	t.Helper()
	_, err := parse(t, hosts)
	if err == nil {
		t.Fatalf("expected a startup error mentioning %q, got none", contains)
	}
	if !strings.Contains(err.Error(), contains) {
		t.Fatalf("error %q does not mention %q", err, contains)
	}
}

// The eight startup rules, one failing fixture each.

func TestRule1CatchAllRequired(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /health, policy: public }
`, "a /** route is required")
}

func TestRule2NothingAfterCatchAll(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /**, policy: public }
      - { path: /health, policy: public }
`, "/** must be the last route")
}

func TestRule3DuplicateRoute(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /api/**, methods: [GET, POST], policy: public }
      - { path: /api/**, methods: [POST], policy: public }
      - { path: /**, policy: public }
`, "duplicates route")
}

func TestRule4UnknownUpstream(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /api/**, upstream: nowhere, policy: public }
      - { path: /**, policy: public }
`, `upstream "nowhere" is not declared`)
}

func TestRule5UnknownService(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /**, policy: "service(image, family)" }
`, `service "image" is not in services`)
}

func TestRule6LiteralSecret(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /api/**, policy: public, inject_headers: { X-Service-Token: "abc123" } }
      - { path: /**, policy: public }
`, "must be env:NAME")
}

func TestRule6SecretFieldNeedsEnvRef(t *testing.T) {
	bad := strings.Replace(header, `client_secret: "env:IDP_CLIENT_SECRET"`, `client_secret: "s3cret"`, 1)
	if _, err := Parse([]byte(bad + "hosts:\n  - host: a.example\n    upstream: resume\n    routes:\n      - { path: /**, policy: public }\n")); err == nil {
		t.Fatal("a literal client secret must fail startup")
	}
}

func TestRule7AliasOverlap(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    aliases: [b.example]
    routes:
      - { path: /**, policy: public }
  - host: b.example
    upstream: resume
    routes:
      - { path: /**, policy: public }
`, "declared twice")
}

func TestRule8StripPrefixEmptiesPath(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /api, strip_prefix: /api, policy: public }
      - { path: /**, policy: public }
`, "leaves an empty path")
}

func TestPolicyRequiredUnlessBFF(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /**, upstream: resume }
`, "policy is required")
}

func TestBFFRouteNeedsNoPolicy(t *testing.T) {
	f := mustParse(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /auth/**, bff: true }
      - { path: /**, policy: public }
`)
	if _, rt, ok := f.Router().Match("a.example", "GET", "/auth/login"); !ok || !rt.BFF {
		t.Fatalf("bff route did not match: ok=%v", ok)
	}
}

func TestResolveEnv(t *testing.T) {
	f := mustParse(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /api/**, policy: public, inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" } }
      - { path: /**, policy: public }
`)
	env := map[string]string{
		"IDP_CLIENT_SECRET":   "idp-secret",
		"GATEWAY_SESSION_KEY": "0123456789abcdef0123456789abcdef",
		"SWITCH_TOKEN":        "switch-token",
	}
	if err := f.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err != nil {
		t.Fatalf("resolve: %v", err)
	}
	if got := f.Secrets().IdPClient; got != "idp-secret" {
		t.Fatalf("idp secret = %q", got)
	}
	_, rt, ok := f.Router().Match("a.example", "GET", "/api/files")
	if !ok || rt.Headers["X-Service-Token"] != "switch-token" {
		t.Fatalf("injected header = %v", rt.Headers)
	}
}

func TestResolveEnvFailsOnMissingHeaderVar(t *testing.T) {
	f := mustParse(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /**, policy: public, inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" } }
`)
	env := map[string]string{"IDP_CLIENT_SECRET": "s", "GATEWAY_SESSION_KEY": "k"}
	if err := f.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err == nil {
		t.Fatal("an unset injected header variable must fail startup")
	}
}

func TestResolveEnvFailsOnMissing(t *testing.T) {
	f := mustParse(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /**, policy: public }
`)
	if err := f.ResolveEnv(func(string) (string, bool) { return "", false }); err == nil {
		t.Fatal("a missing variable must fail startup")
	}
}

func TestMatchPrecedenceAndMethods(t *testing.T) {
	f := mustParse(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /health, policy: public }
      - { path: /api/**, methods: [POST], upstream: app, policy: session }
      - { path: /**, policy: public }
`)
	r := f.Router()
	cases := []struct {
		method, path string
		want         string
	}{
		{"GET", "/health", "/health"},
		{"GET", "/health/deep", "/**"},
		{"POST", "/api/x/y", "/api/**"},
		{"GET", "/api/x", "/**"},
		{"GET", "/", "/**"},
	}
	for _, c := range cases {
		_, rt, ok := r.Match("a.example", c.method, c.path)
		if !ok {
			t.Fatalf("%s %s: no match", c.method, c.path)
		}
		if rt.Path != c.want {
			t.Fatalf("%s %s matched %q, want %q", c.method, c.path, rt.Path, c.want)
		}
	}
}

func TestHostNormalizationAndAliases(t *testing.T) {
	f := mustParse(t, `  - host: A.example
    upstream: resume
    aliases: [alias.example]
    routes:
      - { path: /**, policy: public }
`)
	for _, h := range []string{"a.example", "A.EXAMPLE:8443", "a.example.", "alias.example"} {
		if f.Router().HostBlock(h) == nil {
			t.Fatalf("host %q did not resolve", h)
		}
	}
	if f.Router().HostBlock("other.example") != nil {
		t.Fatal("an undeclared host must not resolve")
	}
	if !f.AllowsHost("alias.example") || f.AllowsHost("other.example") {
		t.Fatal("return_to allowlist is wrong")
	}
}

// --- the owl chat ---------------------------------------------------------

// A chat route is served in this process and names no upstream. Both together
// would mean two things at once.
func TestChatRouteCannotAlsoNameAnUpstream(t *testing.T) {
	wantError(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /api/chat, methods: [POST], chat: true, upstream: app, policy: public }
      - { path: /**, policy: public }
`, "chat and upstream are exclusive")
}

func TestChatRouteCompiles(t *testing.T) {
	f := mustParse(t, `  - host: a.example
    upstream: resume
    routes:
      - { path: /api/chat, methods: [POST], chat: true, policy: public }
      - { path: /**, policy: public }
`)
	_, rt, ok := f.Router().Match("a.example", "POST", "/api/chat")
	if !ok || rt == nil || !rt.Chat {
		t.Fatalf("chat route did not compile: %+v ok=%v", rt, ok)
	}
}

// The model key is optional: an unset variable leaves the chat disabled instead
// of failing the start, because sign-in does not depend on the owl.
func TestLLMKeyIsOptional(t *testing.T) {
	f, err := Parse([]byte(strings.Replace(header,
		`  resume: "resume:80"`,
		`  resume: "resume:80"`+"\n"+`llm:
  host: "http://litellm:4000/v1"
  model: "gpt-4o-mini"
  api_key: "env:LLM_API_KEY"`, 1) + "hosts:\n  - host: a.example\n    upstream: resume\n    routes:\n      - { path: /**, policy: public }\n"))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	env := map[string]string{
		"IDP_CLIENT_SECRET":   "idp",
		"GATEWAY_SESSION_KEY": "k",
		"IDP_ADMIN_SECRET":    "admin",
	}
	if err := f.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err != nil {
		t.Fatalf("an unset LLM_API_KEY must not fail startup: %v", err)
	}
	if f.Secrets().LLMAPIKey != "" {
		t.Fatalf("key %q", f.Secrets().LLMAPIKey)
	}
	env["LLM_API_KEY"] = "sk-1"
	if err := f.ResolveEnv(func(k string) (string, bool) { v, ok := env[k]; return v, ok }); err != nil {
		t.Fatalf("resolve: %v", err)
	}
	if f.Secrets().LLMAPIKey != "sk-1" {
		t.Fatalf("key %q", f.Secrets().LLMAPIKey)
	}
}
