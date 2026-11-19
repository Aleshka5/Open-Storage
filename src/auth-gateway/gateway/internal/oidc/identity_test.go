package oidc

import "testing"

// Two mappings for one service used to resolve by token order, and /admin
// resolved them the other way round. One order, most restrictive first, for all
// readers.
func TestServiceLevelPrecedence(t *testing.T) {
	cases := []struct {
		name  string
		roles []string
		want  string
	}{
		{"single family", []string{"svc:storage:family"}, "family"},
		{"admin and family", []string{"svc:storage:family", "svc:storage:admin"}, "admin"},
		{"family and admin", []string{"svc:storage:admin", "svc:storage:family"}, "admin"},
		{"blocked beats admin", []string{"svc:storage:admin", "svc:storage:blocked"}, "blocked"},
		{"blocked beats family", []string{"svc:storage:family", "svc:storage:blocked"}, "blocked"},
		{"other service", []string{"svc:image:admin"}, ""},
		{"no roles", nil, ""},
		{"malformed", []string{"svc:storage", "svc::family", "storage:family"}, ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			id := &Identity{Subject: "s", Roles: tc.roles}
			if got := id.ServiceLevel("storage"); got != tc.want {
				t.Fatalf("ServiceLevel = %q, want %q", got, tc.want)
			}
			if got := ServiceLevelFromRoles(tc.roles, "storage"); got != tc.want {
				t.Fatalf("ServiceLevelFromRoles = %q, want %q", got, tc.want)
			}
		})
	}
}

func TestBlockedIsTheOnlyLevelThatClosesAnAccount(t *testing.T) {
	// A drifted realm can hold blocked next to a live grant; blocked has to win or
	// the closure is a suggestion.
	id := &Identity{Subject: "s", Roles: []string{"svc:audio:family", "svc:audio:blocked"}}
	if id.ServiceLevel("audio") != "blocked" {
		t.Fatalf("level = %q, want blocked", id.ServiceLevel("audio"))
	}
}
