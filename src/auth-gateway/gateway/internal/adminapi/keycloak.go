package adminapi

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// kcUser is the part of the Keycloak user representation the list needs.
type kcUser struct {
	ID        string `json:"id"`
	Username  string `json:"username"`
	Email     string `json:"email"`
	FirstName string `json:"firstName"`
	LastName  string `json:"lastName"`
	Enabled   bool   `json:"enabled"`
}

// kcRole is a realm role. Keycloak wants both fields on a mapping change.
type kcRole struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

// accessToken is the gateway-admin service account token, cached until shortly
// before it dies. The lock doubles as single flight: a burst of /admin clicks
// must not mint one token each.
func (s *Server) accessToken(ctx context.Context) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.token != "" && time.Now().Before(s.tokenExp) {
		return s.token, nil
	}
	form := url.Values{
		"grant_type":    {"client_credentials"},
		"client_id":     {s.cfg.ClientID},
		"client_secret": {s.cfg.ClientSecret},
	}
	endpoint := s.cfg.BaseURL + "/realms/" + urlPath(s.cfg.Realm) + "/protocol/openid-connect/token"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, strings.NewReader(form.Encode()))
	if err != nil {
		return "", errIDP
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := s.http.Do(req)
	if err != nil {
		return "", errIDP
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", errIDP
	}
	var tr struct {
		AccessToken string `json:"access_token"`
		ExpiresIn   int    `json:"expires_in"`
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&tr); err != nil || tr.AccessToken == "" {
		return "", errIDP
	}
	ttl := time.Duration(tr.ExpiresIn) * time.Second
	if ttl <= 0 {
		ttl = time.Minute
	}
	// Renew early so a call never leaves with a token that expires on the wire.
	s.token, s.tokenExp = tr.AccessToken, time.Now().Add(ttl-30*time.Second)
	return s.token, nil
}

// dropToken forgets a token Keycloak rejected, so the next call re-mints
// instead of retrying a dead one until its cached expiry.
func (s *Server) dropToken(token string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.token == token {
		s.token, s.tokenExp = "", time.Time{}
	}
}

// call performs one Admin API request. `path` is relative to
// /admin/realms/{realm}. A 404 stays distinct from an idp failure so handlers
// can answer not_found.
func (s *Server) call(ctx context.Context, method, path string, body any) ([]byte, error) {
	token, err := s.accessToken(ctx)
	if err != nil {
		return nil, err
	}
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, s.cfg.BaseURL+"/admin/realms/"+urlPath(s.cfg.Realm)+path, rdr)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := s.http.Do(req)
	if err != nil {
		return nil, errIDP
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	switch {
	case resp.StatusCode == http.StatusNotFound:
		return nil, errNotFound
	case resp.StatusCode == http.StatusUnauthorized:
		s.dropToken(token)
		return nil, errIDP
	case resp.StatusCode < 200 || resp.StatusCode > 299:
		return nil, errIDP
	}
	return data, nil
}

func urlPath(segment string) string { return url.PathEscape(segment) }

func (s *Server) getJSON(ctx context.Context, path string, v any) error {
	data, err := s.call(ctx, http.MethodGet, path, nil)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(data, v); err != nil {
		return errIDP
	}
	return nil
}

// fetchUsers reads the first 200 accounts. The contract stops there rather than
// paginating, and the caller reports whatever came back as the total.
func (s *Server) fetchUsers(ctx context.Context) ([]kcUser, error) {
	var users []kcUser
	return users, s.getJSON(ctx, "/users?first=0&max=200", &users)
}

func (s *Server) realmMappings(ctx context.Context, uid string) ([]kcRole, error) {
	var roles []kcRole
	return roles, s.getJSON(ctx, "/users/"+urlPath(uid)+"/role-mappings/realm", &roles)
}

func (s *Server) changeMappings(ctx context.Context, method, uid string, roles []kcRole) error {
	_, err := s.call(ctx, method, "/users/"+urlPath(uid)+"/role-mappings/realm", roles)
	return err
}

// realmRole looks the name up in the realm catalog. A role missing there means
// the realm drifted from the configured service list, so it is an idp failure,
// not a user error.
func (s *Server) realmRole(ctx context.Context, name string) (*kcRole, error) {
	var roles []kcRole
	if err := s.getJSON(ctx, "/roles", &roles); err != nil {
		return nil, err
	}
	for i := range roles {
		if roles[i].Name == name {
			return &roles[i], nil
		}
	}
	return nil, errIDP
}

// userObject is the account exactly as Keycloak returned it.
func (s *Server) userObject(ctx context.Context, uid string) (map[string]any, error) {
	obj := map[string]any{}
	return obj, s.getJSON(ctx, "/users/"+urlPath(uid), &obj)
}

func (s *Server) updateUser(ctx context.Context, uid string, obj map[string]any) error {
	_, err := s.call(ctx, http.MethodPut, "/users/"+urlPath(uid), obj)
	return err
}

// logoutUser drops every session the account has; already issued access tokens
// still live out their five minutes.
func (s *Server) logoutUser(ctx context.Context, uid string) error {
	_, err := s.call(ctx, http.MethodPost, "/users/"+urlPath(uid)+"/logout", nil)
	return err
}

// adminCount reads at most two members: enough to tell "one" from "more than
// one" without pulling a list we would only count.
func (s *Server) adminCount(ctx context.Context) (int, error) {
	var users []kcUser
	if err := s.getJSON(ctx, "/roles/"+roleAdmin+"/users?first=0&max=2", &users); err != nil {
		return 0, err
	}
	return len(users), nil
}
