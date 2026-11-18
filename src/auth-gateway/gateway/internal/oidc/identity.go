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
	for _, r := range i.Roles {
		parts := strings.Split(r, ":")
		if len(parts) == 3 && parts[0] == "svc" && parts[1] == service {
			return parts[2]
		}
	}
	return ""
}
