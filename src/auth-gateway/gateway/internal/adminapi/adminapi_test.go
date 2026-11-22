package adminapi

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"testing"

	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
)

// fakeKC is a Keycloak Admin API small enough to assert on: users live in a map,
// realm-role mappings in a slice per user, and every request is recorded.
type fakeKC struct {
	t        *testing.T
	mu       sync.Mutex
	order    []string
	users    map[string]map[string]any
	mappings map[string][]string
	roles    []kcRole
	calls    []fakeCall
	down     bool
	stale    bool // answer the next admin call with 401, as a rotated token would
	tokens   int
}

type fakeCall struct {
	Method string
	Path   string
	Query  string
	Body   string
}

func newFake(t *testing.T) *fakeKC {
	return &fakeKC{
		t:        t,
		users:    map[string]map[string]any{},
		mappings: map[string][]string{},
		roles: []kcRole{
			{ID: "r-admin", Name: "admin"},
			{ID: "r-storage-admin", Name: "svc:storage:admin"},
			{ID: "r-storage-family", Name: "svc:storage:family"},
			{ID: "r-storage-blocked", Name: "svc:storage:blocked"},
			{ID: "r-image-admin", Name: "svc:image:admin"},
			{ID: "r-image-family", Name: "svc:image:family"},
			{ID: "r-image-blocked", Name: "svc:image:blocked"},
			{ID: "r-rag-admin", Name: "svc:rag:admin"},
			{ID: "r-rag-family", Name: "svc:rag:family"},
			{ID: "r-rag-blocked", Name: "svc:rag:blocked"},
			{ID: "r-audio-admin", Name: "svc:audio:admin"},
			{ID: "r-audio-family", Name: "svc:audio:family"},
			{ID: "r-audio-blocked", Name: "svc:audio:blocked"},
		},
	}
}

func (f *fakeKC) addUser(id, email, first, last string, enabled bool, roles ...string) {
	f.users[id] = map[string]any{
		"id": id, "username": email, "email": email,
		"firstName": first, "lastName": last, "enabled": enabled,
		"createdTimestamp": 1700000000000,
	}
	f.order = append(f.order, id)
	f.mappings[id] = append([]string(nil), roles...)
}

func (f *fakeKC) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /realms/filenkov/protocol/openid-connect/token", f.token)
	mux.HandleFunc("GET /admin/realms/filenkov/users", f.listUsers)
	mux.HandleFunc("GET /admin/realms/filenkov/users/{id}", f.getUser)
	mux.HandleFunc("PUT /admin/realms/filenkov/users/{id}", f.putUser)
	mux.HandleFunc("POST /admin/realms/filenkov/users/{id}/logout", f.logout)
	mux.HandleFunc("GET /admin/realms/filenkov/users/{id}/role-mappings/realm", f.mappingsFor)
	mux.HandleFunc("DELETE /admin/realms/filenkov/users/{id}/role-mappings/realm", f.mappingsFor)
	mux.HandleFunc("POST /admin/realms/filenkov/users/{id}/role-mappings/realm", f.mappingsFor)
	mux.HandleFunc("GET /admin/realms/filenkov/roles", f.roleList)
	mux.HandleFunc("GET /admin/realms/filenkov/roles/admin", f.roleList)
	mux.HandleFunc("GET /admin/realms/filenkov/roles/admin/users", f.roleMembers)
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		f.t.Errorf("unexpected keycloak call %s %s", r.Method, r.URL.Path)
		http.NotFound(w, r)
	})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		f.mu.Lock()
		f.calls = append(f.calls, fakeCall{Method: r.Method, Path: r.URL.Path, Query: r.URL.RawQuery, Body: string(body)})
		f.mu.Unlock()
		r.Body = io.NopCloser(bytes.NewReader(body))
		mux.ServeHTTP(w, r)
	})
}

func (f *fakeKC) token(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		f.t.Errorf("token form: %v", err)
	}
	if r.PostForm.Get("grant_type") != "client_credentials" ||
		r.PostForm.Get("client_id") != "gateway-admin" ||
		r.PostForm.Get("client_secret") != "s3cret" {
		f.t.Errorf("bad token request %v", r.PostForm)
	}
	f.mu.Lock()
	f.tokens++
	f.mu.Unlock()
	writeJSON(w, http.StatusOK, map[string]any{"access_token": "tok", "expires_in": 300})
}

func (f *fakeKC) guard(w http.ResponseWriter, r *http.Request) bool {
	if r.Header.Get("Authorization") != "Bearer tok" {
		f.t.Errorf("%s %s: missing bearer token", r.Method, r.URL.Path)
		w.WriteHeader(http.StatusUnauthorized)
		return false
	}
	if f.down {
		http.Error(w, "down", http.StatusInternalServerError)
		return false
	}
	if f.stale {
		f.stale = false
		w.WriteHeader(http.StatusUnauthorized)
		return false
	}
	return true
}

func (f *fakeKC) listUsers(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.guard(w, r) {
		return
	}
	out := make([]map[string]any, 0, len(f.order))
	for _, id := range f.order {
		out = append(out, f.users[id])
	}
	writeJSON(w, http.StatusOK, out)
}

func (f *fakeKC) getUser(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.guard(w, r) {
		return
	}
	u, ok := f.users[r.PathValue("id")]
	if !ok {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, http.StatusOK, u)
}

func (f *fakeKC) putUser(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.guard(w, r) {
		return
	}
	id := r.PathValue("id")
	if _, ok := f.users[id]; !ok {
		http.NotFound(w, r)
		return
	}
	var patch map[string]any
	if err := json.NewDecoder(r.Body).Decode(&patch); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	for k, v := range patch {
		f.users[id][k] = v
	}
	w.WriteHeader(http.StatusNoContent)
}

func (f *fakeKC) logout(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.guard(w, r) {
		return
	}
	if _, ok := f.users[r.PathValue("id")]; !ok {
		http.NotFound(w, r)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (f *fakeKC) roleList(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.guard(w, r) {
		return
	}
	writeJSON(w, http.StatusOK, f.roles)
}

func (f *fakeKC) roleMembers(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.guard(w, r) {
		return
	}
	limit := 200
	if m := r.URL.Query().Get("max"); m != "" {
		limit, _ = strconv.Atoi(m)
	}
	out := []map[string]any{}
	for _, id := range f.order {
		if f.has(id, "admin") {
			out = append(out, f.users[id])
		}
	}
	if len(out) > limit {
		out = out[:limit]
	}
	writeJSON(w, http.StatusOK, out)
}

func (f *fakeKC) mappingsFor(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.guard(w, r) {
		return
	}
	id := r.PathValue("id")
	if _, ok := f.users[id]; !ok {
		http.NotFound(w, r)
		return
	}
	switch r.Method {
	case http.MethodGet:
		out := []kcRole{}
		for _, name := range f.mappings[id] {
			for _, role := range f.roles {
				if role.Name == name {
					out = append(out, role)
				}
			}
		}
		writeJSON(w, http.StatusOK, out)
		return
	case http.MethodDelete:
		var drop []kcRole
		if err := json.NewDecoder(r.Body).Decode(&drop); err != nil {
			f.t.Errorf("delete body: %v", err)
		}
		for _, role := range drop {
			if role.ID == "" || role.Name == "" {
				f.t.Errorf("role needs id and name: %+v", role)
			}
			f.mappings[id] = remove(f.mappings[id], role.Name)
		}
	case http.MethodPost:
		var add []kcRole
		if err := json.NewDecoder(r.Body).Decode(&add); err != nil {
			f.t.Errorf("post body: %v", err)
		}
		for _, role := range add {
			if role.ID == "" || role.Name == "" {
				f.t.Errorf("role needs id and name: %+v", role)
			}
			if !f.has(id, role.Name) {
				f.mappings[id] = append(f.mappings[id], role.Name)
			}
		}
	}
	w.WriteHeader(http.StatusNoContent)
}

func (f *fakeKC) has(id, name string) bool {
	for _, n := range f.mappings[id] {
		if n == name {
			return true
		}
	}
	return false
}

func remove(list []string, name string) []string {
	out := list[:0]
	for _, n := range list {
		if n != name {
			out = append(out, n)
		}
	}
	return out
}

// callsOf returns every recorded call, filtered by method and path.
func (f *fakeKC) callsOf(method, path string) []fakeCall {
	f.mu.Lock()
	defer f.mu.Unlock()
	var out []fakeCall
	for _, c := range f.calls {
		if c.Method == method && c.Path == path {
			out = append(out, c)
		}
	}
	return out
}

func (f *fakeKC) rolesOf(id string) []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.mappings[id]...)
}

type harness struct {
	t   *testing.T
	kc  *fakeKC
	srv *Server
}

var allServices = []string{"storage", "image", "rag", "audio"}

func newHarness(t *testing.T) *harness {
	t.Helper()
	f := newFake(t)
	ts := httptest.NewServer(f.handler())
	t.Cleanup(ts.Close)
	srv, err := New(Config{
		BaseURL: ts.URL, Realm: "filenkov",
		ClientID: "gateway-admin", ClientSecret: "s3cret",
		Services: allServices,
	})
	if err != nil {
		t.Fatalf("new: %v", err)
	}
	return &harness{t: t, kc: f, srv: srv}
}

func (h *harness) request(method, path, body string, id *oidc.Identity) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if id != nil {
		req = req.WithContext(oidc.WithIdentity(req.Context(), id))
	}
	rec := httptest.NewRecorder()
	h.srv.Handler().ServeHTTP(rec, req)
	return rec
}

func admin(sub string) *oidc.Identity {
	return &oidc.Identity{Subject: sub, Roles: []string{"admin"}}
}

func owner(sub, svc string) *oidc.Identity {
	return &oidc.Identity{Subject: sub, Roles: []string{"svc:" + svc + ":admin"}}
}

// wantError asserts the ADR-0005 envelope: one snake_case string, not an object.
func wantError(t *testing.T, rec *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	if rec.Code != status {
		t.Fatalf("status = %d, want %d (body %s)", rec.Code, status, rec.Body.String())
	}
	var env map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &env); err != nil {
		t.Fatalf("error body is not json: %s", rec.Body.String())
	}
	got, ok := env["error"].(string)
	if !ok || got != code {
		t.Fatalf("error = %v, want string %q", env["error"], code)
	}
}

func TestListUsersShape(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "Lovelace", true, "admin", "svc:storage:family")
	h.kc.addUser("u2", "bob@example.com", "", "", true)

	rec := h.request(http.MethodGet, "/admin/users", "", admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	var got usersView
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got.Total != 2 || len(got.Users) != 2 {
		t.Fatalf("total = %d, users = %d", got.Total, len(got.Users))
	}
	ada := got.Users[0]
	if ada.ID != "u1" || ada.Email != "ada@example.com" || ada.Name != "Ada Lovelace" || !ada.Enabled || !ada.Admin {
		t.Fatalf("ada = %+v", ada)
	}
	if len(ada.Services) != len(allServices) {
		t.Fatalf("services = %+v, want every configured service", ada.Services)
	}
	for i, svc := range allServices {
		if ada.Services[i].Service != svc {
			t.Fatalf("services[%d] = %q, want %q", i, ada.Services[i].Service, svc)
		}
	}
	if lv := ada.Services[0].Level; lv == nil || *lv != "family" {
		t.Fatalf("storage level = %v, want family", lv)
	}
	for _, s := range ada.Services[1:] {
		if s.Level != nil {
			t.Fatalf("%s level = %v, want null", s.Service, *s.Level)
		}
	}
	// A level-less user renders nulls, not omitted keys.
	if !strings.Contains(rec.Body.String(), `"level":null`) {
		t.Fatalf("null level missing from body: %s", rec.Body.String())
	}
	bob := got.Users[1]
	if bob.Name != "bob@example.com" || bob.Admin {
		t.Fatalf("bob = %+v", bob)
	}
	// One service-account token covers the whole list, not one per user.
	if h.kc.tokens != 1 {
		t.Fatalf("token calls = %d, want 1", h.kc.tokens)
	}
	if n := len(h.kc.callsOf(http.MethodGet, "/admin/realms/filenkov/users/u1/role-mappings/realm")); n != 1 {
		t.Fatalf("role mapping calls = %d, want 1", n)
	}
}

func TestAdminOnlyEndpoints(t *testing.T) {
	paths := []struct {
		method, path, body string
	}{
		{http.MethodGet, "/admin/users", ""},
		{http.MethodPatch, "/admin/users/u1", `{"enabled":false}`},
		{http.MethodPut, "/admin/users/u1/admin", `{"value":true}`},
	}
	for _, tc := range paths {
		t.Run(tc.method+" "+tc.path, func(t *testing.T) {
			h := newHarness(t)
			h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "svc:storage:admin")

			wantError(t, h.request(tc.method, tc.path, tc.body, nil), http.StatusUnauthorized, "unauthorized")
			wantError(t, h.request(tc.method, tc.path, tc.body, owner("u1", "storage")), http.StatusForbidden, "forbidden")
		})
	}
}

func TestServiceRoleForeignServiceForbidden(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u2", "bob@example.com", "Bob", "", true, "svc:storage:family")

	rec := h.request(http.MethodPut, "/admin/users/u2/roles/storage", `{"level":"admin"}`, owner("u1", "image"))
	wantError(t, rec, http.StatusForbidden, "forbidden")
	if got := h.kc.rolesOf("u2"); len(got) != 1 || got[0] != "svc:storage:family" {
		t.Fatalf("roles changed on a forbidden call: %v", got)
	}
}

func TestServiceRoleOwnServiceAllowed(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u2", "bob@example.com", "Bob", "", true, "svc:storage:family")

	rec := h.request(http.MethodPut, "/admin/users/u2/roles/storage", `{"level":"admin"}`, owner("u1", "storage"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	if got := h.kc.rolesOf("u2"); len(got) != 1 || got[0] != "svc:storage:admin" {
		t.Fatalf("roles = %v, want only svc:storage:admin", got)
	}
}

func TestServiceRoleBadRequests(t *testing.T) {
	cases := []struct {
		name   string
		path   string
		body   string
		status int
		code   string
	}{
		{"admin is not a service", "/admin/users/u1/roles/admin", `{"level":"admin"}`, http.StatusBadRequest, "validation"},
		{"unknown service", "/admin/users/u1/roles/llm", `{"level":"family"}`, http.StatusNotFound, "not_found"},
		{"unknown level", "/admin/users/u1/roles/storage", `{"level":"root"}`, http.StatusBadRequest, "validation"},
		{"missing level", "/admin/users/u1/roles/storage", `{}`, http.StatusBadRequest, "validation"},
		{"level is not a string", "/admin/users/u1/roles/storage", `{"level":3}`, http.StatusBadRequest, "validation"},
		{"broken json", "/admin/users/u1/roles/storage", `{`, http.StatusBadRequest, "validation"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := newHarness(t)
			h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")
			wantError(t, h.request(http.MethodPut, tc.path, tc.body, admin("u1")), tc.status, tc.code)
		})
	}
}

func TestServiceRoleNullRemovesEveryRole(t *testing.T) {
	h := newHarness(t)
	// Two roles on one service is drift, but the contract says remove every
	// svc:<svc>:* role, so both must go.
	h.kc.addUser("u2", "bob@example.com", "Bob", "", true, "svc:storage:family", "svc:storage:blocked", "svc:image:family")

	rec := h.request(http.MethodPut, "/admin/users/u2/roles/storage", `{"level":null}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	drops := h.kc.callsOf(http.MethodDelete, "/admin/realms/filenkov/users/u2/role-mappings/realm")
	if len(drops) != 1 {
		t.Fatalf("deletes = %d, want 1", len(drops))
	}
	if !strings.Contains(drops[0].Body, "svc:storage:family") || !strings.Contains(drops[0].Body, "svc:storage:blocked") {
		t.Fatalf("delete body = %s", drops[0].Body)
	}
	if posts := h.kc.callsOf(http.MethodPost, "/admin/realms/filenkov/users/u2/role-mappings/realm"); len(posts) != 0 {
		t.Fatalf("null level granted a role: %s", posts[0].Body)
	}
	if got := h.kc.rolesOf("u2"); len(got) != 1 || got[0] != "svc:image:family" {
		t.Fatalf("roles = %v, want the image role untouched", got)
	}
}

func TestServiceRoleGrantReplaces(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u2", "bob@example.com", "Bob", "", true, "svc:storage:family")

	rec := h.request(http.MethodPut, "/admin/users/u2/roles/storage", `{"level":"blocked"}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	dels := h.kc.callsOf(http.MethodDelete, "/admin/realms/filenkov/users/u2/role-mappings/realm")
	posts := h.kc.callsOf(http.MethodPost, "/admin/realms/filenkov/users/u2/role-mappings/realm")
	if len(dels) != 1 || len(posts) != 1 {
		t.Fatalf("deletes = %d, posts = %d, want 1 and 1", len(dels), len(posts))
	}
	if !strings.Contains(posts[0].Body, "svc:storage:blocked") || !strings.Contains(posts[0].Body, "r-storage-blocked") {
		t.Fatalf("grant body = %s", posts[0].Body)
	}
	if got := h.kc.rolesOf("u2"); len(got) != 1 || got[0] != "svc:storage:blocked" {
		t.Fatalf("roles = %v", got)
	}
}

func TestServiceRoleUnknownUser(t *testing.T) {
	h := newHarness(t)
	rec := h.request(http.MethodPut, "/admin/users/nope/roles/storage", `{"level":"family"}`, admin("u1"))
	wantError(t, rec, http.StatusNotFound, "not_found")
}

func TestPatchUserDisableLogsOut(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u2", "bob@example.com", "Bob", "Jones", true, "svc:storage:family")

	rec := h.request(http.MethodPatch, "/admin/users/u2", `{"enabled":false}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	puts := h.kc.callsOf(http.MethodPut, "/admin/realms/filenkov/users/u2")
	if len(puts) != 1 {
		t.Fatalf("puts = %d, want 1", len(puts))
	}
	var sent map[string]any
	if err := json.Unmarshal([]byte(puts[0].Body), &sent); err != nil {
		t.Fatalf("put body: %v", err)
	}
	if sent["enabled"] != false {
		t.Fatalf("enabled = %v", sent["enabled"])
	}
	// The full representation goes back: a field we did not model must survive.
	for _, key := range []string{"firstName", "lastName", "email", "createdTimestamp"} {
		if _, ok := sent[key]; !ok {
			t.Fatalf("put dropped %q: %s", key, puts[0].Body)
		}
	}
	if n := len(h.kc.callsOf(http.MethodPost, "/admin/realms/filenkov/users/u2/logout")); n != 1 {
		t.Fatalf("logout calls = %d, want 1", n)
	}
	if h.kc.users["u2"]["enabled"] != false {
		t.Fatalf("user not disabled: %v", h.kc.users["u2"])
	}
}

func TestPatchUserEnableKeepsSessions(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u2", "bob@example.com", "Bob", "", false)

	rec := h.request(http.MethodPatch, "/admin/users/u2", `{"enabled":true}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	if n := len(h.kc.callsOf(http.MethodPost, "/admin/realms/filenkov/users/u2/logout")); n != 0 {
		t.Fatalf("logout called %d times on enable", n)
	}
}

func TestPatchUserUnknownUser(t *testing.T) {
	h := newHarness(t)
	wantError(t, h.request(http.MethodPatch, "/admin/users/nope", `{"enabled":false}`, admin("u1")),
		http.StatusNotFound, "not_found")
}

func TestPatchUserBadBody(t *testing.T) {
	for name, body := range map[string]string{"empty": `{}`, "not json": `nope`, "wrong type": `{"enabled":"no"}`} {
		t.Run(name, func(t *testing.T) {
			h := newHarness(t)
			h.kc.addUser("u2", "bob@example.com", "Bob", "", true)
			wantError(t, h.request(http.MethodPatch, "/admin/users/u2", body, admin("u1")), http.StatusBadRequest, "validation")
		})
	}
}

func TestLastAdminConflict(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")

	// The last admin removing their own role is the same refusal.
	rec := h.request(http.MethodPut, "/admin/users/u1/admin", `{"value":false}`, admin("u1"))
	wantError(t, rec, http.StatusConflict, "last_admin")
	if dels := h.kc.callsOf(http.MethodDelete, "/admin/realms/filenkov/users/u1/role-mappings/realm"); len(dels) != 0 {
		t.Fatalf("revoked despite the conflict: %s", dels[0].Body)
	}
	if !h.kc.has("u1", "admin") {
		t.Fatal("admin role was removed")
	}
}

func TestLastAdminAllowsSecondAdminToBeRemoved(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")
	h.kc.addUser("u2", "bob@example.com", "Bob", "", true, "admin")

	rec := h.request(http.MethodPut, "/admin/users/u2/admin", `{"value":false}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	dels := h.kc.callsOf(http.MethodDelete, "/admin/realms/filenkov/users/u2/role-mappings/realm")
	if len(dels) != 1 || !strings.Contains(dels[0].Body, `"name":"admin"`) {
		t.Fatalf("delete = %+v", dels)
	}
	if h.kc.has("u2", "admin") {
		t.Fatal("admin role survived")
	}
	if !h.kc.has("u1", "admin") {
		t.Fatal("the caller lost admin")
	}
}

func TestGrantAdmin(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")
	h.kc.addUser("u2", "bob@example.com", "Bob", "", true, "svc:storage:family")

	rec := h.request(http.MethodPut, "/admin/users/u2/admin", `{"value":true}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	if !h.kc.has("u2", "admin") {
		t.Fatal("admin role not granted")
	}
	// Granting never consults the member list.
	if n := len(h.kc.callsOf(http.MethodGet, "/admin/realms/filenkov/roles/admin/users")); n != 0 {
		t.Fatalf("member list read %d times on grant", n)
	}
}

func TestGrantAdminIsIdempotent(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin", "admin")

	rec := h.request(http.MethodPut, "/admin/users/u1/admin", `{"value":true}`, admin("u1"))
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", rec.Code, rec.Body.String())
	}
	if posts := h.kc.callsOf(http.MethodPost, "/admin/realms/filenkov/users/u1/role-mappings/realm"); len(posts) != 0 {
		t.Fatalf("granted twice: %s", posts[0].Body)
	}
}

func TestAdminBadBody(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")
	wantError(t, h.request(http.MethodPut, "/admin/users/u1/admin", `{}`, admin("u1")), http.StatusBadRequest, "validation")
}

func TestIDPUnavailable(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")
	h.kc.down = true

	rec := h.request(http.MethodGet, "/admin/users", "", admin("u1"))
	wantError(t, rec, http.StatusServiceUnavailable, "idp_unavailable")
}

// A token Keycloak rejected must not be retried until its cached expiry: the
// next request has to mint a new one.
func TestRejectedTokenIsDropped(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "admin")
	h.kc.stale = true

	wantError(t, h.request(http.MethodGet, "/admin/users", "", admin("u1")), http.StatusServiceUnavailable, "idp_unavailable")
	if rec := h.request(http.MethodGet, "/admin/users", "", admin("u1")); rec.Code != http.StatusOK {
		t.Fatalf("second call = %d: %s", rec.Code, rec.Body.String())
	}
	if h.kc.tokens != 2 {
		t.Fatalf("token calls = %d, want 2", h.kc.tokens)
	}
}

func TestListPrefersAdminLevel(t *testing.T) {
	h := newHarness(t)
	h.kc.addUser("u1", "ada@example.com", "Ada", "", true, "svc:storage:family", "svc:storage:admin")

	rec := h.request(http.MethodGet, "/admin/users", "", admin("u1"))
	var got usersView
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if lv := got.Users[0].Services[0].Level; lv == nil || *lv != "admin" {
		t.Fatalf("level = %v, want admin", lv)
	}
}

func TestNewRejectsIncompleteConfig(t *testing.T) {
	cases := map[string]Config{
		"no base url":      {Realm: "filenkov", ClientID: "c", ClientSecret: "s"},
		"no realm":         {BaseURL: "https://id.example", ClientID: "c", ClientSecret: "s"},
		"no client id":     {BaseURL: "https://id.example", Realm: "filenkov", ClientSecret: "s"},
		"no client secret": {BaseURL: "https://id.example", Realm: "filenkov", ClientID: "c"},
	}
	for name, cfg := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := New(cfg); err == nil {
				t.Fatal("want error")
			}
		})
	}
}
