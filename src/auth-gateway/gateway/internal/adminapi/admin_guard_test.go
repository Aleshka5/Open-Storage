package adminapi

import (
	"net/http"
	"testing"
)

// Disabling an account is the second way to lose the last admin, so it carries
// the same guard as removing the role.
func TestPatchUserCannotDisableTheLastAdmin(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")

	rec := h.request(http.MethodPatch, "/admin/users/u1", `{"enabled":false}`, admin("u1"))
	wantError(t, rec, http.StatusConflict, "last_admin")
	if puts := h.kc.callsOf(http.MethodPut, "/admin/realms/filenkov/users/u1"); len(puts) != 0 {
		t.Fatalf("the account was updated anyway: %s", puts[0].Body)
	}
	if !h.kc.users["u1"]["enabled"].(bool) {
		t.Fatal("the last admin was disabled")
	}
}

// A disabled admin is not a way in, so it does not count as a second one.
func TestPatchUserCountsOnlyEnabledAdmins(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")
	h.kc.addUser("u2", "bob@example.com", "Bob", "", false, "admin")

	rec := h.request(http.MethodPatch, "/admin/users/u1", `{"enabled":false}`, admin("u1"))
	wantError(t, rec, http.StatusConflict, "last_admin")
}

// With another enabled admin the disable goes through, and the sessions go too.
func TestPatchUserDisablesAnAdminWhenAnotherRemains(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")
	h.kc.addUser("u2", "bob@example.com", "Bob", "", true, "admin")

	rec := h.request(http.MethodPatch, "/admin/users/u2", `{"enabled":false}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	if len(h.kc.callsOf(http.MethodPost, "/admin/realms/filenkov/users/u2/logout")) != 1 {
		t.Fatal("a disabled account kept its sessions")
	}
}

// A re-enable is not a way to lose anything.
func TestPatchUserEnableIsNotGuarded(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", false, "admin")

	rec := h.request(http.MethodPatch, "/admin/users/u1", `{"enabled":true}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
}
