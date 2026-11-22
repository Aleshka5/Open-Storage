// Package policy answers allow or deny for one identity. It reads already
// verified claims; it never calls another service. Route expressions are owned
// by the gateway message contract.
package policy

import (
	"fmt"
	"strings"

	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
)

// Kind is a policy family.
type Kind int

const (
	// Public allows everyone, including anonymous requests.
	Public Kind = iota
	// Session allows an authenticated account.
	Session
	// Admin allows realm role `admin` only.
	Admin
	// Deny allows nobody; the path answers 404 as if it did not exist.
	Deny
	// Service allows `svc:<service>:<level>` for one of its levels.
	Service
)

// Policy is a compiled route expression.
type Policy struct {
	Kind     Kind
	Service  string
	Levels   []string
	Original string
}

// DefaultServiceLevels is what `service(<svc>)` means: the owner level includes
// the family level.
var DefaultServiceLevels = []string{"admin", "family"}

// Parse compiles one expression. `services` is the configured service list; a
// name outside it fails startup.
func Parse(expr string, services []string) (Policy, error) {
	raw := strings.TrimSpace(expr)
	if raw == "" {
		return Policy{}, fmt.Errorf("policy is required")
	}
	switch raw {
	case "public":
		return Policy{Kind: Public, Original: raw}, nil
	case "session":
		return Policy{Kind: Session, Original: raw}, nil
	case "admin":
		return Policy{Kind: Admin, Original: raw}, nil
	case "deny":
		return Policy{Kind: Deny, Original: raw}, nil
	}
	if !strings.HasPrefix(raw, "service(") || !strings.HasSuffix(raw, ")") {
		return Policy{}, fmt.Errorf("unknown policy %q", raw)
	}
	inner := strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(raw, "service("), ")"))
	fields := strings.Split(inner, ",")
	name := strings.TrimSpace(fields[0])
	if name == "" {
		return Policy{}, fmt.Errorf("policy %q: service name is empty", raw)
	}
	if !contains(services, name) {
		return Policy{}, fmt.Errorf("policy %q: service %q is not in services", raw, name)
	}
	levels := make([]string, 0, len(fields)-1)
	for _, f := range fields[1:] {
		l := strings.TrimSpace(f)
		if l == "" {
			continue
		}
		if l != "family" && l != "admin" {
			return Policy{}, fmt.Errorf("policy %q: unknown level %q", raw, l)
		}
		levels = append(levels, l)
	}
	if len(levels) == 0 {
		levels = DefaultServiceLevels
	}
	return Policy{Kind: Service, Service: name, Levels: levels, Original: raw}, nil
}

// Allow reports whether the identity passes. A nil identity is anonymous.
func (p Policy) Allow(id *oidc.Identity) bool {
	switch p.Kind {
	case Public:
		return true
	case Deny:
		return false
	}
	if id == nil {
		return false
	}
	switch p.Kind {
	case Admin:
		return id.HasRole("admin")
	case Session:
		return true
	case Service:
		level := id.ServiceLevel(p.Service)
		if level == "" {
			return false
		}
		for _, want := range p.Levels {
			if level == want {
				return true
			}
		}
		return false
	}
	return false
}

// Blocked reports whether the account is closed for one service. On a host that
// names a service, this beats a `session` policy: the host is closed for that
// account while the account itself stays enabled.
func Blocked(id *oidc.Identity, service string) bool {
	if id == nil || service == "" {
		return false
	}
	return id.ServiceLevel(service) == "blocked"
}

func contains(list []string, want string) bool {
	for _, v := range list {
		if v == want {
			return true
		}
	}
	return false
}
