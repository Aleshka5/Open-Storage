// Package bff is the OIDC client inside the gateway. Tokens never reach
// JavaScript: they live in `HttpOnly` cookies sealed here (ADR-0002). One refresh
// runs at a time per subject, because Keycloak rotates refresh tokens.
package bff

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/aleshka5/open-storage/auth-gateway/internal/config"
	"github.com/aleshka5/open-storage/auth-gateway/internal/oidc"
	"github.com/aleshka5/open-storage/auth-gateway/internal/session"
)

// Metrics is the counter set the contract names for this package.
type Metrics interface {
	Refresh(result string)
	IdP(op string, status int)
}

type nopMetrics struct{}

func (nopMetrics) Refresh(string)  {}
func (nopMetrics) IdP(string, int) {}

// Config wires the BFF.
type Config struct {
	File       *config.File
	Provider   *oidc.Provider
	Verifier   *oidc.Verifier
	Sealer     *session.Sealer
	Logger     *slog.Logger
	Metrics    Metrics
	HTTPClient *http.Client
	// DevHTTP relaxes the https requirement on return_to in tests only.
	DevHTTP bool
}

// Server serves the four /auth endpoints and the refresh hook the edge calls.
type Server struct {
	file        *config.File
	provider    *oidc.Provider
	verifier    *oidc.Verifier
	sealer      *session.Sealer
	log         *slog.Logger
	metrics     Metrics
	client      *http.Client
	flights     *session.Flights
	callbackURL string
	devHTTP     bool
}

// New builds the BFF. Every value it needs comes from the configuration file.
func New(cfg Config) (*Server, error) {
	if cfg.File == nil || cfg.Provider == nil || cfg.Verifier == nil || cfg.Sealer == nil {
		return nil, fmt.Errorf("config, provider, verifier and sealer are required")
	}
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	if cfg.Metrics == nil {
		cfg.Metrics = nopMetrics{}
	}
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{
			Timeout: 10 * time.Second,
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		}
	}
	return &Server{
		file:        cfg.File,
		provider:    cfg.Provider,
		verifier:    cfg.Verifier,
		sealer:      cfg.Sealer,
		log:         cfg.Logger,
		metrics:     cfg.Metrics,
		client:      cfg.HTTPClient,
		flights:     &session.Flights{},
		callbackURL: strings.TrimRight(cfg.File.PublicOrigin, "/") + "/auth/callback",
		devHTTP:     cfg.DevHTTP,
	}, nil
}

// Handler serves the /auth routes. Everything else is a 404: the edge matched a
// `bff: true` route, so an unknown path here is a contract defect, not a page.
func (s *Server) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/auth/login":
			s.login(w, r)
		case "/auth/callback":
			s.handleCallback(w, r)
		case "/auth/logout":
			s.logout(w, r)
		case "/auth/session":
			s.profile(w, r)
		default:
			writeError(w, http.StatusNotFound, "not_found")
		}
	})
}

// login starts the code flow with PKCE and a nonce. The pending values travel in
// a sealed cookie, so the browser cannot edit the state or the verifier.
func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	state, err := random(16)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "internal")
		return
	}
	nonce, err := random(16)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "internal")
		return
	}
	verifier, err := random(32)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "internal")
		return
	}
	sealed, err := s.sealer.SealFlow(session.Flow{
		State:    state,
		Nonce:    nonce,
		Verifier: verifier,
		ReturnTo: s.returnTo(r),
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "internal")
		return
	}
	session.SetCookies(w, s.sealer.FlowCookie(sealed))

	q := url.Values{
		"client_id":             {s.file.IdP.ClientID},
		"redirect_uri":          {s.callbackURL},
		"response_type":         {"code"},
		"scope":                 {strings.Join(s.file.IdP.Scopes, " ")},
		"state":                 {state},
		"nonce":                 {nonce},
		"code_challenge":        {challenge(verifier)},
		"code_challenge_method": {"S256"},
		// Google is the only login. The Keycloak form is never shown.
		"kc_idp_hint": {"google"},
	}
	target := s.provider.AuthURL + "?" + q.Encode()
	http.Redirect(w, r, target, http.StatusFound)
}

func (s *Server) handleCallback(w http.ResponseWriter, r *http.Request) {
	flowCookie := session.Value(r, session.NameFlow)
	// One-shot: the flow cookie is gone whatever happens next.
	session.SetCookies(w, s.sealer.ClearFlowCookie())
	fail := func(code string) {
		http.Redirect(w, r, strings.TrimRight(s.file.PublicOrigin, "/")+"/?auth_error="+url.QueryEscape(code), http.StatusFound)
	}
	if flowCookie == "" {
		fail("invalid_state")
		return
	}
	flow, err := s.sealer.OpenFlow(flowCookie)
	if err != nil {
		fail("invalid_state")
		return
	}
	if r.URL.Query().Get("state") != flow.State {
		fail("invalid_state")
		return
	}
	if e := r.URL.Query().Get("error"); e != "" {
		fail(e)
		return
	}
	code := r.URL.Query().Get("code")
	if code == "" {
		fail("invalid_request")
		return
	}
	tokens, status, err := s.token(r.Context(), url.Values{
		"grant_type":    {"authorization_code"},
		"code":          {code},
		"redirect_uri":  {s.callbackURL},
		"client_id":     {s.file.IdP.ClientID},
		"client_secret": {s.file.Secrets().IdPClient},
		"code_verifier": {flow.Verifier},
	})
	if err != nil || tokens == nil {
		s.log.Warn("bff_exchange_failed", "err", err, "status", status)
		fail("exchange_failed")
		return
	}
	id, err := s.verifier.VerifyID(r.Context(), tokens.IDToken, flow.Nonce)
	if err != nil {
		s.log.Warn("bff_id_token_rejected", "err", err)
		fail("invalid_id_token")
		return
	}
	access, err := s.verifier.Verify(r.Context(), tokens.AccessToken)
	if err != nil {
		s.log.Warn("bff_access_token_rejected", "err", err)
		fail("invalid_access_token")
		return
	}
	sid := access.SID
	if sid == "" {
		sid = id.SID
	}
	sealed, err := s.sealer.Seal(session.State{Subject: id.Subject, RefreshToken: tokens.RefreshToken, SID: sid})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "internal")
		return
	}
	session.SetCookies(w, s.sealer.AccessCookie(tokens.AccessToken), s.sealer.SessionCookie(sealed))
	http.Redirect(w, r, flow.ReturnTo, http.StatusFound)
}

func (s *Server) logout(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusNotFound, "not_found")
		return
	}
	// A cross-site form can post without a body it controls; the header is the
	// only proof that the request came from our own page.
	if r.Header.Get("Origin") == "" && r.Header.Get("X-Requested-With") == "" {
		writeError(w, http.StatusForbidden, "forbidden")
		return
	}
	if sealed := session.Value(r, session.NameSession); sealed != "" {
		if st, err := s.sealer.Open(sealed); err == nil && st.RefreshToken != "" {
			// Logout at the idp is best effort: the local cookies go either way,
			// and a dead idp must not trap the user in a signed-in page.
			if err := s.endSession(r.Context(), st.RefreshToken); err != nil {
				s.log.Warn("bff_logout_idp", "err", err)
			}
		}
	}
	session.SetCookies(w, s.sealer.Clear()...)
	writeJSON(w, http.StatusOK, `{"status":"ok"}`)
}

// profile is the only identity call the page makes.
func (s *Server) profile(w http.ResponseWriter, r *http.Request) {
	id := oidc.FromContext(r.Context())
	if id == nil {
		// The access cookie lives 5 minutes; the page reloads far less often than
		// that. A silent refresh here keeps one call per load honest.
		if token, status := s.Refresh(w, r); token != "" {
			if verified, err := s.verifier.Verify(r.Context(), token); err == nil {
				id = verified
			}
		} else if status >= 500 {
			writeError(w, status, "auth_unavailable")
			return
		}
	}
	if id == nil {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	type service struct {
		Service string  `json:"service"`
		Level   *string `json:"level"`
	}
	out := struct {
		Subject  string    `json:"subject"`
		Email    string    `json:"email"`
		Name     string    `json:"name"`
		Roles    []string  `json:"roles"`
		Services []service `json:"services"`
	}{Subject: id.Subject, Email: id.Email, Name: id.Name, Roles: id.Roles, Services: make([]service, 0, len(s.file.Services))}
	if out.Roles == nil {
		out.Roles = []string{}
	}
	for _, name := range s.file.Services {
		item := service{Service: name}
		if level := id.ServiceLevel(name); level != "" {
			lvl := level
			item.Level = &lvl
		}
		out.Services = append(out.Services, item)
	}
	body, err := json.Marshal(out)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "internal")
		return
	}
	writeJSON(w, http.StatusOK, string(body))
}

// Refresh is the edge hook: it exchanges the session cookie for an access token.
// The caller sets the returned cookies on its own response.
func (s *Server) Refresh(w http.ResponseWriter, r *http.Request) (string, int) {
	sealed := session.Value(r, session.NameSession)
	if sealed == "" {
		return "", 0
	}
	st, err := s.sealer.Open(sealed)
	if err != nil || st.RefreshToken == "" {
		session.SetCookies(w, s.sealer.Clear()...)
		return "", 0
	}
	out := s.flights.Do(session.Key(st.RefreshToken), func() session.Outcome {
		return s.exchange(r.Context(), *st)
	})
	if out.OK {
		session.SetCookies(w, s.sealer.AccessCookie(out.AccessToken), s.sealer.SessionCookie(out.Sealed))
		return out.AccessToken, 0
	}
	if out.Status == 0 {
		// invalid_grant: the session is over, the caller continues anonymous.
		session.SetCookies(w, s.sealer.Clear()...)
	}
	return "", out.Status
}

func (s *Server) exchange(ctx context.Context, st session.State) session.Outcome {
	tokens, status, err := s.token(ctx, url.Values{
		"grant_type":    {"refresh_token"},
		"refresh_token": {st.RefreshToken},
		"client_id":     {s.file.IdP.ClientID},
		"client_secret": {s.file.Secrets().IdPClient},
	})
	if err != nil || tokens == nil {
		if status >= 500 || status == 0 {
			return session.Outcome{Status: http.StatusServiceUnavailable}
		}
		return session.Outcome{Status: 0}
	}
	access, err := s.verifier.Verify(ctx, tokens.AccessToken)
	if err != nil {
		s.log.Warn("bff_refresh_bad_access", "err", err)
		return session.Outcome{Status: 0}
	}
	sid := access.SID
	if sid == "" {
		sid = st.SID
	}
	refresh := tokens.RefreshToken
	if refresh == "" {
		refresh = st.RefreshToken
	}
	sealed, err := s.sealer.Seal(session.State{Subject: access.Subject, RefreshToken: refresh, SID: sid})
	if err != nil {
		return session.Outcome{Status: http.StatusServiceUnavailable}
	}
	return session.Outcome{AccessToken: tokens.AccessToken, Sealed: sealed, OK: true}
}

// endSession ends the idp session, which also kills everything tied to `sid`.
func (s *Server) endSession(ctx context.Context, refreshToken string) error {
	endpoint := s.provider.EndSessionURL
	if endpoint == "" {
		endpoint = strings.TrimRight(s.provider.Issuer, "/") + "/protocol/openid-connect/logout"
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	form := url.Values{
		"client_id":     {s.file.IdP.ClientID},
		"client_secret": {s.file.Secrets().IdPClient},
		"refresh_token": {refreshToken},
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, strings.NewReader(form.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	res, err := s.client.Do(req)
	if err != nil {
		s.metrics.IdP("logout", 0)
		return err
	}
	defer res.Body.Close()
	s.metrics.IdP("logout", res.StatusCode)
	if res.StatusCode >= 400 {
		return fmt.Errorf("logout endpoint answered %d", res.StatusCode)
	}
	return nil
}

// tokenResponse is the subset of the Keycloak token answer this namespace reads.
type tokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	IDToken      string `json:"id_token"`
	ExpiresIn    int    `json:"expires_in"`
}

// token posts a token request. A 4xx is an invalid grant; a transport error or a
// 5xx is an idp that is not answering. The distinction decides 401 versus 503.
func (s *Server) token(ctx context.Context, form url.Values) (*tokenResponse, int, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.provider.TokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "application/json")
	res, err := s.client.Do(req)
	if err != nil {
		s.metrics.IdP("token", 0)
		return nil, 0, err
	}
	defer res.Body.Close()
	s.metrics.IdP("token", res.StatusCode)
	if res.StatusCode != http.StatusOK {
		s.metrics.Refresh("invalid_grant")
		var body json.RawMessage
		_ = json.NewDecoder(res.Body).Decode(&body)
		return nil, res.StatusCode, fmt.Errorf("token endpoint answered %d: %s", res.StatusCode, truncate(string(body), 200))
	}
	var out tokenResponse
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, res.StatusCode, err
	}
	s.metrics.Refresh("ok")
	if out.AccessToken == "" {
		return nil, res.StatusCode, fmt.Errorf("token answer has no access_token")
	}
	return &out, res.StatusCode, nil
}

func (s *Server) returnTo(r *http.Request) string {
	origin := strings.TrimRight(s.file.PublicOrigin, "/")
	raw := strings.TrimSpace(r.URL.Query().Get("return_to"))
	if raw == "" {
		return origin + "/"
	}
	u, err := url.Parse(raw)
	if err != nil {
		return origin + "/"
	}
	if u.Scheme != "https" && !s.devHTTP {
		return origin + "/"
	}
	if !s.file.AllowsHost(u.Host) {
		return origin + "/"
	}
	return u.String()
}

func random(n int) (string, error) {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}

func challenge(verifier string) string {
	sum := sha256.Sum256([]byte(verifier))
	return base64.RawURLEncoding.EncodeToString(sum[:])
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

func writeJSON(w http.ResponseWriter, status int, body string) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(body))
}

func writeError(w http.ResponseWriter, status int, value string) {
	writeJSON(w, status, `{"error":"`+value+`"}`)
}
