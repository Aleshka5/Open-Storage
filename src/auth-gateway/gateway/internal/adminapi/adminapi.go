// Package adminapi serves `/admin`: the user list and the three writes the UI
// needs. Reads come from the verified access token, writes go to the Keycloak
// Admin API, and nothing is cached — a catalog copied here would let one
// request undo another.
package adminapi

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
)

// Config is what the process hands over from config.yaml. BaseURL is the issuer
// base without `/realms`.
type Config struct {
	BaseURL      string
	Realm        string
	ClientID     string
	ClientSecret string
	Services     []string
	HTTPClient   *http.Client
}

// Server answers /admin. One per process; the token cache and its lock live
// here, not per request.
type Server struct {
	cfg      Config
	http     *http.Client
	services []string

	mu       sync.Mutex
	token    string
	tokenExp time.Time
}

// New validates the config. A missing client secret is a startup error, not a
// 503 on the first click.
func New(cfg Config) (*Server, error) {
	cfg.BaseURL = strings.TrimRight(strings.TrimSpace(cfg.BaseURL), "/")
	cfg.Realm = strings.TrimSpace(cfg.Realm)
	switch {
	case cfg.BaseURL == "":
		return nil, errors.New("adminapi: base url is required")
	case cfg.Realm == "":
		return nil, errors.New("adminapi: realm is required")
	case cfg.ClientID == "":
		return nil, errors.New("adminapi: client id is required")
	case cfg.ClientSecret == "":
		return nil, errors.New("adminapi: client secret is required")
	}
	hc := cfg.HTTPClient
	if hc == nil {
		hc = &http.Client{Timeout: 15 * time.Second}
	}
	return &Server{cfg: cfg, http: hc, services: append([]string(nil), cfg.Services...)}, nil
}

// Handler is the /admin mux. The edge mounts it and owns probes and the access
// log.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /admin/users", s.listUsers)
	mux.HandleFunc("PUT /admin/users/{id}/roles/{svc}", s.putServiceRole)
	mux.HandleFunc("PATCH /admin/users/{id}", s.patchUser)
	mux.HandleFunc("PUT /admin/users/{id}/admin", s.putAdmin)
	return mux
}

type userView struct {
	ID       string        `json:"id"`
	Email    string        `json:"email"`
	Name     string        `json:"name"`
	Enabled  bool          `json:"enabled"`
	Admin    bool          `json:"admin"`
	Services []serviceView `json:"services"`
}

type serviceView struct {
	Service string  `json:"service"`
	Level   *string `json:"level"`
}

type usersView struct {
	Users []userView `json:"users"`
	Total int        `json:"total"`
}

type statusView struct {
	Status string `json:"status"`
}

var statusOK = statusView{Status: "ok"}

func (s *Server) listUsers(w http.ResponseWriter, r *http.Request) {
	if _, ok := realmAdmin(w, r); !ok {
		return
	}
	users, err := s.fetchUsers(r.Context())
	if err != nil {
		s.failErr(w, err)
		return
	}
	out := usersView{Users: make([]userView, 0, len(users)), Total: len(users)}
	for _, u := range users {
		mappings, err := s.realmMappings(r.Context(), u.ID)
		if err != nil {
			s.failErr(w, err)
			return
		}
		out.Users = append(out.Users, s.view(u, mappings))
	}
	writeJSON(w, http.StatusOK, out)
}

// view fills every configured service, in config order, so the UI renders a
// stable table and never has to know a service by name. A nil level means the
// account holds no role for that service.
func (s *Server) view(u kcUser, mappings []kcRole) userView {
	v := userView{
		ID: u.ID, Email: u.Email, Enabled: u.Enabled,
		Name:     strings.TrimSpace(u.FirstName + " " + u.LastName),
		Admin:    hasRole(mappings, roleAdmin),
		Services: make([]serviceView, 0, len(s.services)),
	}
	if v.Name == "" {
		v.Name = u.Username
	}
	for _, svc := range s.services {
		v.Services = append(v.Services, serviceView{Service: svc, Level: levelFor(mappings, svc)})
	}
	return v
}

// putServiceRole replaces the whole svc:<svc>:* set with one level, or with
// nothing. A realm admin may edit any service; a service owner only its own.
func (s *Server) putServiceRole(w http.ResponseWriter, r *http.Request) {
	id, ok := caller(w, r)
	if !ok {
		return
	}
	svc := r.PathValue("svc")
	switch {
	case svc == "admin":
		fail(w, errValidation) // admin is a realm role, not a service
		return
	case !s.hasService(svc):
		fail(w, errNotFound)
		return
	case !id.HasRole(roleAdmin) && !id.HasRole("svc:"+svc+":admin"):
		fail(w, errForbidden)
		return
	}
	level, err := levelBody(r)
	if err != nil {
		fail(w, errValidation)
		return
	}
	ctx, uid := r.Context(), r.PathValue("id")
	mappings, err := s.realmMappings(ctx, uid)
	if err != nil {
		s.failErr(w, err)
		return
	}
	if drop := withPrefix(mappings, "svc:"+svc+":"); len(drop) > 0 {
		if err := s.changeMappings(ctx, http.MethodDelete, uid, drop); err != nil {
			s.failErr(w, err)
			return
		}
	}
	if level != nil {
		role, err := s.realmRole(ctx, "svc:"+svc+":"+*level)
		if err != nil {
			s.failErr(w, err)
			return
		}
		if err := s.changeMappings(ctx, http.MethodPost, uid, []kcRole{*role}); err != nil {
			s.failErr(w, err)
			return
		}
	}
	writeJSON(w, http.StatusOK, statusOK)
}

func (s *Server) patchUser(w http.ResponseWriter, r *http.Request) {
	if _, ok := realmAdmin(w, r); !ok {
		return
	}
	var body struct {
		Enabled *bool `json:"enabled"`
	}
	if err := decodeBody(r, &body); err != nil || body.Enabled == nil {
		fail(w, errValidation)
		return
	}
	ctx, uid := r.Context(), r.PathValue("id")
	obj, err := s.userObject(ctx, uid)
	if err != nil {
		s.failErr(w, err)
		return
	}
	// The whole representation goes back, not a struct of ours: anything we do
	// not model would otherwise be dropped on the round trip.
	obj["enabled"] = *body.Enabled
	if err := s.updateUser(ctx, uid, obj); err != nil {
		s.failErr(w, err)
		return
	}
	if !*body.Enabled {
		if err := s.logoutUser(ctx, uid); err != nil {
			s.failErr(w, err)
			return
		}
	}
	writeJSON(w, http.StatusOK, statusOK)
}

func (s *Server) putAdmin(w http.ResponseWriter, r *http.Request) {
	if _, ok := realmAdmin(w, r); !ok {
		return
	}
	var body struct {
		Value *bool `json:"value"`
	}
	if err := decodeBody(r, &body); err != nil || body.Value == nil {
		fail(w, errValidation)
		return
	}
	ctx, uid := r.Context(), r.PathValue("id")
	mappings, err := s.realmMappings(ctx, uid)
	if err != nil {
		s.failErr(w, err)
		return
	}
	// A repeated click changes nothing, and a no-op must not trip the last-admin
	// guard: that would refuse a harmless request.
	if granted := hasRole(mappings, roleAdmin); *body.Value == granted {
		writeJSON(w, http.StatusOK, statusOK)
		return
	}
	role, err := s.realmRole(ctx, roleAdmin)
	if err != nil {
		s.failErr(w, err)
		return
	}
	method := http.MethodPost
	if !*body.Value {
		n, err := s.adminCount(ctx)
		if err != nil {
			s.failErr(w, err)
			return
		}
		if n <= 1 {
			fail(w, errLastAdmin)
			return
		}
		method = http.MethodDelete
	}
	if err := s.changeMappings(ctx, method, uid, []kcRole{*role}); err != nil {
		s.failErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, statusOK)
}

const roleAdmin = "admin"

// apiError is the whole envelope: a status and one snake_case code, per
// ADR-0005.
type apiError struct {
	code   string
	status int
}

func (e apiError) Error() string { return e.code }

var (
	errUnauthorized = apiError{status: http.StatusUnauthorized, code: "unauthorized"}
	errForbidden    = apiError{status: http.StatusForbidden, code: "forbidden"}
	errNotFound     = apiError{status: http.StatusNotFound, code: "not_found"}
	errValidation   = apiError{status: http.StatusBadRequest, code: "validation"}
	errLastAdmin    = apiError{status: http.StatusConflict, code: "last_admin"}
	errIDP          = apiError{status: http.StatusServiceUnavailable, code: "idp_unavailable"}
)

func fail(w http.ResponseWriter, e apiError) {
	writeJSON(w, e.status, map[string]string{"error": e.code})
}

func (s *Server) failErr(w http.ResponseWriter, err error) {
	var e apiError
	if errors.As(err, &e) {
		fail(w, e)
		return
	}
	fail(w, errIDP)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

// caller writes 401 for anonymous. That is not a 403 on purpose: the page needs
// to know it should offer a login rather than a denial.
func caller(w http.ResponseWriter, r *http.Request) (*oidc.Identity, bool) {
	id := oidc.FromContext(r.Context())
	if id == nil {
		fail(w, errUnauthorized)
		return nil, false
	}
	return id, true
}

func realmAdmin(w http.ResponseWriter, r *http.Request) (*oidc.Identity, bool) {
	id, ok := caller(w, r)
	if !ok {
		return nil, false
	}
	if !id.HasRole(roleAdmin) {
		fail(w, errForbidden)
		return nil, false
	}
	return id, true
}

// levelBody reads {"level": "family"|"admin"|"blocked"|null}. An absent key is a
// bad body; an explicit null means remove only.
func levelBody(r *http.Request) (*string, error) {
	var raw map[string]json.RawMessage
	if err := decodeBody(r, &raw); err != nil {
		return nil, err
	}
	v, ok := raw["level"]
	if !ok {
		return nil, errors.New("level is required")
	}
	var level *string
	if err := json.Unmarshal(v, &level); err != nil {
		return nil, err
	}
	if level != nil && *level != "family" && *level != "admin" && *level != "blocked" {
		return nil, errors.New("unknown level")
	}
	return level, nil
}

func decodeBody(r *http.Request, v any) error {
	return json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(v)
}

func (s *Server) hasService(name string) bool {
	for _, svc := range s.services {
		if svc == name {
			return true
		}
	}
	return false
}

func hasRole(roles []kcRole, name string) bool {
	for _, r := range roles {
		if r.Name == name {
			return true
		}
	}
	return false
}

func withPrefix(roles []kcRole, prefix string) []kcRole {
	var out []kcRole
	for _, r := range roles {
		if strings.HasPrefix(r.Name, prefix) {
			out = append(out, r)
		}
	}
	return out
}

// levelFor reads the one level the account holds for a service. Admin wins over
// family if the realm ever drifted into holding two.
func levelFor(roles []kcRole, svc string) *string {
	for _, level := range []string{"admin", "family", "blocked"} {
		if hasRole(roles, "svc:"+svc+":"+level) {
			l := level
			return &l
		}
	}
	return nil
}
