package oidc

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
)

// Verifier checks a Keycloak access token. Signatures come from the realm JWKS,
// cached by kid; every other rule comes from the idp contract and is checked
// here, not by a library default.
type Verifier struct {
	provider *Provider
	audience string
	azp      string
	clientID string
	ttl      time.Duration
	client   *http.Client
	now      func() time.Time

	mu      sync.Mutex
	keys    *oidc.RemoteKeySet
	builtAt time.Time
	probeEr error
}

// NewVerifier returns a verifier for one provider. It warms the JWKS cache and
// fails when the keys cannot be read, so a broken idp is a startup error rather
// than a 401 for the first visitor.
func NewVerifier(ctx context.Context, p *Provider, audience, authorizedParty, clientID string, ttl time.Duration, hc *http.Client) (*Verifier, error) {
	if p == nil {
		return nil, fmt.Errorf("provider is required")
	}
	if ttl <= 0 {
		ttl = 15 * time.Minute
	}
	if hc == nil {
		hc = &http.Client{Timeout: 10 * time.Second}
	}
	v := &Verifier{provider: p, audience: audience, azp: authorizedParty, clientID: clientID, ttl: ttl, client: hc, now: time.Now}
	if err := v.rotate(ctx); err != nil {
		return nil, err
	}
	return v, nil
}

// Provider returns the discovery document for the BFF.
func (v *Verifier) Provider() *Provider { return v.provider }

// Ready reports whether the last JWKS read succeeded. /readyz uses it.
func (v *Verifier) Ready() error {
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.probeEr
}

// rotate rebuilds the key set. A cache older than the TTL is dropped before use,
// so a rotated signing key is picked up within the TTL even when nobody presents
// an unknown kid.
func (v *Verifier) rotate(ctx context.Context) error {
	v.mu.Lock()
	defer v.mu.Unlock()
	if _, err := JWKSKeys(ctx, v.provider.JWKSURL, v.client); err != nil {
		v.probeEr = err
		return err
	}
	v.probeEr = nil
	v.keys = oidc.NewRemoteKeySet(ctx, v.provider.JWKSURL)
	v.builtAt = v.now()
	return nil
}

func (v *Verifier) keySet(ctx context.Context) *oidc.RemoteKeySet {
	v.mu.Lock()
	defer v.mu.Unlock()
	if v.keys == nil || v.now().Sub(v.builtAt) >= v.ttl {
		// Rebuild outside the lock is not worth the complexity: the fetch is one
		// request per TTL, and a concurrent verify blocks for it.
		if err := v.rotateLocked(ctx); err != nil {
			// A failed rotation keeps the previous key set: an idp blip must not
			// log every visitor out.
			return v.keys
		}
	}
	return v.keys
}

func (v *Verifier) rotateLocked(ctx context.Context) error {
	if _, err := JWKSKeys(ctx, v.provider.JWKSURL, v.client); err != nil {
		v.probeEr = err
		return err
	}
	v.probeEr = nil
	v.keys = oidc.NewRemoteKeySet(ctx, v.provider.JWKSURL)
	v.builtAt = v.now()
	return nil
}

// Claims are the parts of a Keycloak access token this namespace reads.
type Claims struct {
	Issuer   string   `json:"iss"`
	Audience audience `json:"aud"`
	Expiry   int64    `json:"exp"`
	NotBefer int64    `json:"nbf"`
	Type     string   `json:"typ"`
	AZP      string   `json:"azp"`
	Subject  string   `json:"sub"`
	Email    string   `json:"email"`
	Name     string   `json:"name"`
	SID      string   `json:"sid"`
	Nonce    string   `json:"nonce"`
	Realm    struct {
		Roles []string `json:"roles"`
	} `json:"realm_access"`
}

// audience accepts a string or an array, which Keycloak uses for both.
type audience []string

func (a *audience) UnmarshalJSON(b []byte) error {
	var one string
	if err := json.Unmarshal(b, &one); err == nil {
		*a = audience{one}
		return nil
	}
	var many []string
	if err := json.Unmarshal(b, &many); err != nil {
		return err
	}
	*a = audience(many)
	return nil
}

// Verify checks an access token: signature, issuer, audience, azp, type, expiry.
// It is the only way in for a product request.
func (v *Verifier) Verify(ctx context.Context, raw string) (*Identity, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, fmt.Errorf("empty token")
	}
	payload, err := v.keySet(ctx).VerifySignature(ctx, raw)
	if err != nil {
		return nil, err
	}
	var c Claims
	if err := json.Unmarshal(payload, &c); err != nil {
		return nil, fmt.Errorf("claims: %w", err)
	}
	now := v.now()
	if err := v.check(&c, now); err != nil {
		return nil, err
	}
	return &Identity{
		Subject: c.Subject,
		Email:   c.Email,
		Name:    c.Name,
		SID:     c.SID,
		Roles:   c.Realm.Roles,
	}, nil
}

// VerifyID checks the id_token of the code exchange: signature, issuer,
// audience equal to the client, the nonce from the flow, and expiry. It carries
// no roles, so it is only good for finishing a login.
func (v *Verifier) VerifyID(ctx context.Context, raw, nonce string) (*Identity, error) {
	payload, err := v.keySet(ctx).VerifySignature(ctx, strings.TrimSpace(raw))
	if err != nil {
		return nil, err
	}
	var c Claims
	if err := json.Unmarshal(payload, &c); err != nil {
		return nil, fmt.Errorf("claims: %w", err)
	}
	now := v.now()
	if strings.TrimRight(c.Issuer, "/") != strings.TrimRight(v.provider.Issuer, "/") {
		return nil, fmt.Errorf("id_token iss %q does not match the realm", c.Issuer)
	}
	if v.clientID != "" && !contains(c.Audience, v.clientID) {
		return nil, fmt.Errorf("id_token aud does not contain %q", v.clientID)
	}
	if c.Nonce != nonce {
		return nil, fmt.Errorf("id_token nonce does not match the flow")
	}
	if c.Subject == "" {
		return nil, fmt.Errorf("id_token has no subject")
	}
	if c.Expiry == 0 || now.Add(-clockSkew).After(time.Unix(c.Expiry, 0)) {
		return nil, fmt.Errorf("id_token expired")
	}
	return &Identity{Subject: c.Subject, Email: c.Email, Name: c.Name, SID: c.SID}, nil
}

const clockSkew = 30 * time.Second

func (v *Verifier) check(c *Claims, now time.Time) error {
	if strings.TrimRight(c.Issuer, "/") != strings.TrimRight(v.provider.Issuer, "/") {
		return fmt.Errorf("iss %q does not match the realm", c.Issuer)
	}
	if !contains(c.Audience, v.audience) {
		return fmt.Errorf("aud does not contain %q", v.audience)
	}
	if v.azp != "" && c.AZP != v.azp {
		return fmt.Errorf("azp %q is not %q", c.AZP, v.azp)
	}
	// `aud=account` is shared by every client in the realm, so `azp` above and the
	// token type here carry the weight.
	if c.Type != "Bearer" {
		return fmt.Errorf("typ %q is not an access token", c.Type)
	}
	if c.Subject == "" {
		return fmt.Errorf("sub is empty")
	}
	if c.Expiry == 0 || now.Add(-clockSkew).After(time.Unix(c.Expiry, 0)) {
		return fmt.Errorf("token expired")
	}
	if c.NotBefer != 0 && time.Unix(c.NotBefer, 0).After(now.Add(clockSkew)) {
		return fmt.Errorf("token not valid yet")
	}
	return nil
}

func contains(list audience, want string) bool {
	for _, v := range list {
		if v == want {
			return true
		}
	}
	return false
}
