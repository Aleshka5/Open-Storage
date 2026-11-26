package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/policy"
)

// TestStorageHostDeclaration locks the storage.filenkov.store block that
// US-07 leaves in config.yaml. A change to the upstream, the host, the
// routes, the 30m response-header timeout, or the other hosts' timeouts
// fails here. The file itself is not rewritten by this test.
func TestStorageHostDeclaration(t *testing.T) {
	data, err := os.ReadFile(repoPath(t, "src/auth-gateway/gateway/config.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	f, err := Parse(data)
	if err != nil {
		t.Fatalf("config.yaml: %v", err)
	}

	if got := f.Upstreams["storage"]; got != "app:8000" {
		t.Fatalf("upstreams.storage = %q, want app:8000", got)
	}
	if !contains(f.Services, "storage") {
		t.Fatalf("services = %v, want storage included", f.Services)
	}
	parsed, err := policy.Parse("service(storage, family, admin)", f.Services)
	if err != nil {
		t.Fatalf("policy.Parse service(storage, family, admin): %v", err)
	}
	if parsed.Kind != policy.Service || parsed.Service != "storage" {
		t.Fatalf("parsed policy = %+v", parsed)
	}

	var host *Host
	for i := range f.Hosts {
		if f.Hosts[i].Host == "storage.filenkov.store" {
			host = &f.Hosts[i]
			break
		}
	}
	if host == nil {
		t.Fatal("host storage.filenkov.store is missing")
	}
	if host.Upstream != "storage" || host.Service != "storage" {
		t.Fatalf("host upstream=%q service=%q", host.Upstream, host.Service)
	}
	if host.Timeouts == nil || host.Timeouts.ResponseHeader.D() != 30*time.Minute {
		t.Fatalf("storage response_header = %v, want 30m", host.Timeouts)
	}
	if len(host.Routes) != 2 ||
		host.Routes[0].Path != "/health" || host.Routes[0].Policy != "public" ||
		host.Routes[1].Path != "/**" || host.Routes[1].Policy != "service(storage, family, admin)" {
		t.Fatalf("routes = %+v", host.Routes)
	}

	block := f.Router().HostBlock("storage.filenkov.store")
	if block == nil || block.Service != "storage" || block.Upstream == nil || block.Upstream.Host != "app:8000" {
		t.Fatalf("compiled block = %+v", block)
	}
	if block.Timeouts.ResponseHeader != 30*time.Minute {
		t.Fatalf("compiled response_header = %s, want 30m", block.Timeouts.ResponseHeader)
	}
	_, health, ok := f.Router().Match("storage.filenkov.store", "GET", "/health")
	if !ok || health.Policy.Kind != policy.Public {
		t.Fatalf("/health policy = %+v ok=%v", health, ok)
	}
	_, rest, ok := f.Router().Match("storage.filenkov.store", "GET", "/api/files")
	if !ok || rest.Policy.Original != "service(storage, family, admin)" || rest.Path != "/**" {
		t.Fatalf("/api/files matched %+v ok=%v", rest, ok)
	}

	// Lock every other host at the response_header it declares today, including
	// the 60s default where the host sets none. This test does not assign 30m
	// to a host that does not already have it.
	want := map[string]time.Duration{
		"storage.filenkov.store":  30 * time.Minute,
		"filenkov.store":          60 * time.Second,
		"id.filenkov.store":       60 * time.Second,
		"image.filenkov.store":    30 * time.Minute,
		"rag.filenkov.store":      5 * time.Minute,
		"audio.filenkov.store":    30 * time.Minute,
		"llm.filenkov.store":      10 * time.Minute,
		"observer.filenkov.store": 5 * time.Minute,
		"demo.filenkov.store":     60 * time.Second,
	}
	if len(f.Hosts) != len(want) {
		t.Fatalf("host count = %d, locked set has %d", len(f.Hosts), len(want))
	}
	for _, h := range f.Hosts {
		expect, ok := want[h.Host]
		if !ok {
			t.Fatalf("host %s has no locked response_header", h.Host)
		}
		got := f.Router().HostBlock(h.Host)
		if got == nil || got.Timeouts.ResponseHeader != expect {
			t.Fatalf("%s response_header = %s, want %s", h.Host, got.Timeouts.ResponseHeader, expect)
		}
	}
}

// TestStorageRealmRoles locks the three storage roles already in realm.json
// and fails if another svc:storage:* name is added.
func TestStorageRealmRoles(t *testing.T) {
	data, err := os.ReadFile(repoPath(t, "src/auth-gateway/idp/realm.json"))
	if err != nil {
		t.Fatal(err)
	}
	var realm struct {
		Roles struct {
			Realm []struct {
				Name string `json:"name"`
			} `json:"realm"`
		} `json:"roles"`
	}
	if err := json.Unmarshal(data, &realm); err != nil {
		t.Fatal(err)
	}
	want := map[string]int{
		"svc:storage:admin":   0,
		"svc:storage:family":  0,
		"svc:storage:blocked": 0,
	}
	for _, role := range realm.Roles.Realm {
		if len(role.Name) >= len("svc:storage:") && role.Name[:len("svc:storage:")] == "svc:storage:" {
			if _, ok := want[role.Name]; !ok {
				t.Fatalf("unexpected storage role %q", role.Name)
			}
			want[role.Name]++
		}
	}
	for name, n := range want {
		if n != 1 {
			t.Fatalf("role %s appears %d times, want 1", name, n)
		}
	}
}

func repoPath(t *testing.T, rel string) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "..", ".."))
	return filepath.Join(root, rel)
}
