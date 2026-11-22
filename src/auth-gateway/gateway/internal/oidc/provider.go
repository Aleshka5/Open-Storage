package oidc

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Provider is the part of the discovery document the gateway uses.
type Provider struct {
	Issuer        string `json:"issuer"`
	AuthURL       string `json:"authorization_endpoint"`
	TokenURL      string `json:"token_endpoint"`
	JWKSURL       string `json:"jwks_uri"`
	RevokeURL     string `json:"revocation_endpoint"`
	EndSessionURL string `json:"end_session_endpoint"`
}

// Discover reads `.well-known/openid-configuration` and refuses a document whose
// issuer differs from the configured one: a mismatch would verify tokens the idp
// did not issue.
func Discover(ctx context.Context, issuer string, hc *http.Client) (*Provider, error) {
	return DiscoverServerSide(ctx, issuer, "", hc)
}

// DiscoverServerSide does the same read, but fetches and then rewrites the
// endpoints this process calls to `serverBase`. The browser is sent to
// `AuthorizationURL` and must keep the public origin; discovery, JWKS, token,
// revocation, logout and the admin API are server-side, so they may take an
// address that only the container can reach. `iss` is still the public issuer,
// which is what every token carries.
func DiscoverServerSide(ctx context.Context, issuer, serverBase string, hc *http.Client) (*Provider, error) {
	issuer = strings.TrimRight(strings.TrimSpace(issuer), "/")
	if issuer == "" {
		return nil, fmt.Errorf("issuer is required")
	}
	if hc == nil {
		hc = &http.Client{Timeout: 10 * time.Second}
	}
	serverBase = strings.TrimRight(strings.TrimSpace(serverBase), "/")
	fetchFrom := issuer
	if serverBase != "" {
		fetchFrom = serverBase
	}
	url := fetchFrom + "/.well-known/openid-configuration"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	res, err := hc.Do(req)
	if err != nil {
		return nil, fmt.Errorf("discovery: %w", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("discovery: %s answered %d", url, res.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(res.Body, 1<<20))
	if err != nil {
		return nil, fmt.Errorf("discovery: %w", err)
	}
	var p Provider
	if err := json.Unmarshal(body, &p); err != nil {
		return nil, fmt.Errorf("discovery: %w", err)
	}
	if strings.TrimRight(p.Issuer, "/") != issuer {
		return nil, fmt.Errorf("discovery: document issuer %q does not match %q", p.Issuer, issuer)
	}
	if p.JWKSURL == "" || p.AuthURL == "" || p.TokenURL == "" {
		return nil, fmt.Errorf("discovery: document is missing an endpoint")
	}
	if serverBase != "" {
		for _, field := range []*string{&p.TokenURL, &p.JWKSURL, &p.RevokeURL, &p.EndSessionURL} {
			if *field == "" {
				continue
			}
			rewritten, err := rebase(*field, issuer, serverBase)
			if err != nil {
				return nil, fmt.Errorf("discovery: %w", err)
			}
			*field = rewritten
		}
	}
	return &p, nil
}

// rebase points one endpoint at serverBase. An endpoint outside the issuer is
// left alone: the idp is free to host its token endpoint elsewhere.
func rebase(endpoint, issuer, serverBase string) (string, error) {
	u, err := url.Parse(endpoint)
	if err != nil {
		return "", fmt.Errorf("endpoint %q: %w", endpoint, err)
	}
	iss, err := url.Parse(issuer)
	if err != nil {
		return "", fmt.Errorf("issuer %q: %w", issuer, err)
	}
	if !strings.EqualFold(u.Scheme, iss.Scheme) || !strings.EqualFold(u.Host, iss.Host) {
		return endpoint, nil
	}
	if !strings.HasPrefix(u.Path, iss.Path) {
		return endpoint, nil
	}
	base := strings.TrimRight(serverBase, "/")
	if iss.Path == "" {
		return base + u.Path, nil
	}
	return base + strings.TrimPrefix(u.Path, iss.Path), nil
}

// JWKSKeys reports how many keys the endpoint publishes. Used at start and on
// every cache rotation to answer /readyz honestly.
func JWKSKeys(ctx context.Context, url string, hc *http.Client) (int, error) {
	if hc == nil {
		hc = &http.Client{Timeout: 10 * time.Second}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return 0, err
	}
	res, err := hc.Do(req)
	if err != nil {
		return 0, err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("jwks: %s answered %d", url, res.StatusCode)
	}
	var doc struct {
		Keys []json.RawMessage `json:"keys"`
	}
	if err := json.NewDecoder(io.LimitReader(res.Body, 1<<20)).Decode(&doc); err != nil {
		return 0, fmt.Errorf("jwks: %w", err)
	}
	if len(doc.Keys) == 0 {
		return 0, fmt.Errorf("jwks: %s publishes no key", url)
	}
	return len(doc.Keys), nil
}
