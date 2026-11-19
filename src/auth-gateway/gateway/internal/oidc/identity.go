// Package oidc verifies Keycloak access tokens. The gateway never signs a token:
// the idp issues them and this package only answers "who is this, and what may
// they do". Claims policy is owned by the idp message contract.
package oidc

import (
	"context"
	"sort"
	"strings"
)

type contextKey int

const identityKey contextKey = 1

// WithIdentity puts a verified identity in the request context. Only the edge
// writes it, and only after the token verified.
func WithIdentity(ctx context.Context, id *Identity) context.Context {
	return context.WithValue(ctx, identityKey, id)
}

// FromContext reads the identity the edge put on the request. Nil means
// anonymous.
func FromContext(ctx context.Context) *Identity {
	id, _ := ctx.Value(identityKey).(*Identity)
	return id
}

// Identity is the caller, reduced to what the edge needs. It is built from a
// verified access token only.
type Identity struct {
	Subject string
	Email   string
	Name    string
	SID     string
	// Roles are the realm roles, sorted, as they appear in the token.
	Roles []string
}

// HasRole reports whether the identity carries the exact realm role.
func (i *Identity) HasRole(role string) bool {
	if i == nil {
		return false
	}
	for _, r := range i.Roles {
		if r == role {
			return true
		}
	}
	return false
}

// RoleHeader is the value of X-Auth-Roles: sorted, space separated, and empty
// when there is no role. An empty string means the header is omitted.
func (i *Identity) RoleHeader() string {
	if i == nil || len(i.Roles) == 0 {
		return ""
	}
	roles := make([]string, len(i.Roles))
	copy(roles, i.Roles)
	sort.Strings(roles)
	return strings.Join(roles, " ")
}

// ServiceLevel returns the level granted for one service, or "" when the account
// has no `svc:<service>:*` role.
func (i *Identity) ServiceLevel(service string) string {
	if i == nil {
		return ""
	}
	return ServiceLevelFromRoles(i.Roles, service)
}

// LevelPrecedence is how two `svc:<service>:*` roles on one account resolve,
// most restrictive first. `blocked` wins over everything: a closed account stays
// closed even if another mapping still grants it. Both the edge and `/admin`
// read this order, so the table and the decision can never disagree.
var LevelPrecedence = []string{"blocked", "admin", "family"}

// ServiceLevelFromRoles answers the same question for a bare role list, which is
// what the Keycloak Admin API hands back for /admin.
func ServiceLevelFromRoles(roles []string, service string) string {
	prefix := "svc:" + service + ":"
	held := make(map[string]bool, len(LevelPrecedence))
	for _, r := range roles {
		if !strings.HasPrefix(r, prefix) {
			continue
		}
		held[strings.TrimPrefix(r, prefix)] = true
	}
	for _, level := range LevelPrecedence {
		if held[level] {
			return level
		}
	}
	return ""
}
