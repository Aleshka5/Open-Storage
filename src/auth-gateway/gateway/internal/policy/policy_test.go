package policy

import (
	"testing"

	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
)

var services = []string{"storage", "image", "rag", "audio"}

func compile(t *testing.T, expr string) Policy {
	t.Helper()
	p, err := Parse(expr, services)
	if err != nil {
		t.Fatalf("parse %q: %v", expr, err)
	}
	return p
}

func TestParse(t *testing.T) {
	if p := compile(t, "service(storage)"); p.Kind != Service || p.Service != "storage" || len(p.Levels) != 2 {
		t.Fatalf("service(storage) = %+v", p)
	}
	if p := compile(t, "service(storage, admin)"); len(p.Levels) != 1 || p.Levels[0] != "admin" {
		t.Fatalf("service(storage, admin) = %+v", p)
	}
	bad := []string{"", "nobody", "service()", "service(ghost)", "service(storage, owner)"}
	for _, expr := range bad {
		if _, err := Parse(expr, services); err == nil {
			t.Fatalf("%q must not parse", expr)
		}
	}
}

func TestAllowTable(t *testing.T) {
	admin := &oidc.Identity{Subject: "s", Roles: []string{"admin"}}
	family := &oidc.Identity{Subject: "s", Roles: []string{"svc:storage:family"}}
	serviceAdmin := &oidc.Identity{Subject: "s", Roles: []string{"svc:storage:admin"}}
	blocked := &oidc.Identity{Subject: "s", Roles: []string{"svc:storage:blocked"}}
	stranger := &oidc.Identity{Subject: "s"}
	otherService := &oidc.Identity{Subject: "s", Roles: []string{"svc:image:family"}}

	cases := []struct {
		expr string
		id   *oidc.Identity
		want bool
	}{
		{"public", nil, true},
		{"public", stranger, true},
		{"deny", admin, false},
		{"deny", nil, false},
		{"session", nil, false},
		{"session", stranger, true},
		{"session", blocked, true},
		{"admin", admin, true},
		{"admin", family, false},
		{"admin", nil, false},
		{"service(storage, family, admin)", family, true},
		{"service(storage, family, admin)", serviceAdmin, true},
		{"service(storage, family, admin)", blocked, false},
		{"service(storage, family, admin)", stranger, false},
		{"service(storage, family, admin)", otherService, false},
		{"service(storage, admin)", serviceAdmin, true},
		{"service(storage, admin)", family, false},
		{"service(storage, family)", family, true},
		{"service(storage, family)", serviceAdmin, false},
	}
	for _, c := range cases {
		if got := compile(t, c.expr).Allow(c.id); got != c.want {
			name := "anonymous"
			if c.id != nil {
				name = c.id.Subject + " " + c.id.RoleHeader()
			}
			t.Fatalf("%s for %s = %v, want %v", c.expr, name, got, c.want)
		}
	}
}

func TestBlockedBeatsSession(t *testing.T) {
	blocked := &oidc.Identity{Subject: "s", Roles: []string{"svc:audio:blocked"}}
	if !Blocked(blocked, "audio") {
		t.Fatal("a blocked account must be reported blocked for its service")
	}
	if Blocked(blocked, "storage") {
		t.Fatal("blocked is per service")
	}
	storageBlocked := &oidc.Identity{Subject: "s", Roles: []string{"svc:storage:family", "svc:storage:blocked"}}
	if !Blocked(storageBlocked, "storage") {
		t.Fatal("svc:storage:blocked closes storage even when family is also present")
	}
	if Blocked(storageBlocked, "audio") {
		t.Fatal("a storage block does not close audio")
	}
	if Blocked(nil, "audio") || Blocked(blocked, "") {
		t.Fatal("blocked must need an identity and a service")
	}
}
