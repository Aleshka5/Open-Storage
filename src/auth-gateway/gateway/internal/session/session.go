// Package session owns the three cookies and the one refresh in flight per
// subject. Nothing is stored server-side: the cookie is sealed, and the idp
// remembers the session (ADR-0003).
package session

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"
)

// Cookie names. The `__Secure-` prefix is required because the cookie must cross
// subdomains; `__Host-` forbids Domain, so it cannot be used here.
const (
	NameAccess  = "__Secure-open_access"
	NameSession = "__Secure-open_session"
	NameFlow    = "__Secure-open_flow"
)

// FlowTTL is the life of the half-finished login.
const FlowTTL = 10 * time.Minute

// State is what the sealed cookie carries. No roles and no email: roles are read
// from the access token on every request.
type State struct {
	Subject      string `json:"sub"`
	RefreshToken string `json:"rt"`
	SID          string `json:"sid"`
	IssuedAt     int64  `json:"iat"`
}

// Sealer seals and opens the session cookie with AES-256-GCM.
type Sealer struct {
	aead      cipher.AEAD
	domain    string
	accessTTL time.Duration
	idleTTL   time.Duration
	now       func() time.Time
}

// NewSealer builds the sealer. The key is 32 bytes, base64 encoded, as the
// contract requires; a raw 32-byte string is accepted so a hand-made stand can
// start. Rotating the key signs everyone out.
func NewSealer(key, domain string, accessTTL, idleTTL time.Duration) (*Sealer, error) {
	raw, err := decodeKey(key)
	if err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(raw)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	if accessTTL <= 0 {
		accessTTL = 5 * time.Minute
	}
	if idleTTL <= 0 {
		idleTTL = 168 * time.Hour
	}
	return &Sealer{aead: aead, domain: domain, accessTTL: accessTTL, idleTTL: idleTTL, now: time.Now}, nil
}

func decodeKey(key string) ([]byte, error) {
	key = strings.TrimSpace(key)
	if key == "" {
		return nil, fmt.Errorf("session key is empty")
	}
	for _, enc := range []*base64.Encoding{base64.StdEncoding, base64.RawStdEncoding, base64.URLEncoding, base64.RawURLEncoding} {
		if raw, err := enc.DecodeString(key); err == nil && len(raw) == 32 {
			return raw, nil
		}
	}
	if len(key) == 32 {
		return []byte(key), nil
	}
	return nil, fmt.Errorf("session key must be 32 bytes, base64 encoded")
}

// Seal encrypts the session state. The nonce is random per cookie.
func (s *Sealer) Seal(st State) (string, error) {
	if st.IssuedAt == 0 {
		st.IssuedAt = s.now().Unix()
	}
	return s.sealJSON(st)
}

// Open decrypts and verifies the cookie. An expired or forged value is an error,
// never a partial session.
func (s *Sealer) Open(value string) (*State, error) {
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(value))
	if err != nil {
		return nil, fmt.Errorf("cookie is not base64")
	}
	size := s.aead.NonceSize()
	if len(raw) < size {
		return nil, fmt.Errorf("cookie is too short")
	}
	plain, err := s.aead.Open(nil, raw[:size], raw[size:], []byte(s.domain))
	if err != nil {
		return nil, fmt.Errorf("cookie did not open")
	}
	var st State
	if err := json.Unmarshal(plain, &st); err != nil {
		return nil, fmt.Errorf("cookie payload: %w", err)
	}
	if st.Subject == "" {
		return nil, fmt.Errorf("cookie has no subject")
	}
	if s.now().After(time.Unix(st.IssuedAt, 0).Add(s.idleTTL)) {
		return nil, fmt.Errorf("session idled out")
	}
	return &st, nil
}

// AccessTTL and IdleTTL expose the configured lifetimes for the BFF.
func (s *Sealer) AccessTTL() time.Duration { return s.accessTTL }
func (s *Sealer) IdleTTL() time.Duration   { return s.idleTTL }

// AccessCookie carries the access JWT unmodified.
func (s *Sealer) AccessCookie(token string) *http.Cookie {
	return s.cookie(NameAccess, token, int(s.accessTTL.Seconds()))
}

// SessionCookie carries the sealed state.
func (s *Sealer) SessionCookie(sealed string) *http.Cookie {
	return s.cookie(NameSession, sealed, int(s.idleTTL.Seconds()))
}

// FlowCookie carries the half-finished login: state, nonce, PKCE verifier,
// return_to.
func (s *Sealer) FlowCookie(sealed string) *http.Cookie {
	return s.cookie(NameFlow, sealed, int(FlowTTL.Seconds()))
}

// ClearFlowCookie removes the half-finished login.
func (s *Sealer) ClearFlowCookie() *http.Cookie {
	c := s.cookie(NameFlow, "", -1)
	c.MaxAge = -1
	return c
}

// Clear removes every cookie this namespace sets.
func (s *Sealer) Clear() []*http.Cookie {
	out := make([]*http.Cookie, 0, 3)
	for _, name := range []string{NameAccess, NameSession, NameFlow} {
		c := s.cookie(name, "", -1)
		c.MaxAge = -1
		out = append(out, c)
	}
	return out
}

func (s *Sealer) cookie(name, value string, maxAge int) *http.Cookie {
	return &http.Cookie{
		Name:     name,
		Value:    value,
		Path:     "/",
		Domain:   s.domain,
		HttpOnly: true,
		Secure:   true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   maxAge,
	}
}

// Value reads one cookie from a request.
func Value(r *http.Request, name string) string {
	if r == nil {
		return ""
	}
	c, err := r.Cookie(name)
	if err != nil || c == nil {
		return ""
	}
	return strings.TrimSpace(c.Value)
}

// SetCookies writes the given cookies and ignores nils.
func SetCookies(w http.ResponseWriter, cookies ...*http.Cookie) {
	for _, c := range cookies {
		if c != nil {
			http.SetCookie(w, c)
		}
	}
}

// RewriteRequestCookies replaces cookie values on an in-flight request, so a
// retried request carries the cookie just minted by a refresh.
func RewriteRequestCookies(r *http.Request, updates map[string]string) {
	if r == nil || len(updates) == 0 {
		return
	}
	keep := make([]string, 0, len(r.Cookies()))
	seen := make(map[string]bool, len(updates))
	for _, c := range r.Cookies() {
		if v, ok := updates[c.Name]; ok {
			seen[c.Name] = true
			if v == "" {
				continue
			}
			c.Value = v
		}
		keep = append(keep, c.Name+"="+c.Value)
	}
	for name, v := range updates {
		if v != "" && !seen[name] {
			keep = append(keep, name+"="+v)
		}
	}
	r.Header.Set("Cookie", strings.Join(keep, "; "))
}

// Flow is the half-finished login: the values that must survive the redirect to
// the idp and back, sealed so the browser cannot edit them.
type Flow struct {
	State    string `json:"state"`
	Nonce    string `json:"nonce"`
	Verifier string `json:"verifier"`
	ReturnTo string `json:"return_to"`
	Expires  int64  `json:"exp"`
}

// SealFlow encrypts the pending login.
func (s *Sealer) SealFlow(f Flow) (string, error) {
	if f.Expires == 0 {
		f.Expires = s.now().Add(FlowTTL).Unix()
	}
	return s.sealJSON(f)
}

// OpenFlow decrypts it and refuses an expired or forged value.
func (s *Sealer) OpenFlow(value string) (*Flow, error) {
	var f Flow
	if err := s.openJSON(value, &f); err != nil {
		return nil, err
	}
	if f.State == "" || f.Expires == 0 || s.now().After(time.Unix(f.Expires, 0)) {
		return nil, fmt.Errorf("login flow expired")
	}
	return &f, nil
}

func (s *Sealer) sealJSON(v any) (string, error) {
	payload, err := json.Marshal(v)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, s.aead.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", err
	}
	out := s.aead.Seal(nonce, nonce, payload, []byte(s.domain))
	return base64.RawURLEncoding.EncodeToString(out), nil
}

func (s *Sealer) openJSON(value string, dst any) error {
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(value))
	if err != nil {
		return fmt.Errorf("cookie is not base64")
	}
	size := s.aead.NonceSize()
	if len(raw) < size {
		return fmt.Errorf("cookie is too short")
	}
	plain, err := s.aead.Open(nil, raw[:size], raw[size:], []byte(s.domain))
	if err != nil {
		return fmt.Errorf("cookie did not open")
	}
	return json.Unmarshal(plain, dst)
}

// Outcome is the result of one refresh, shared by every request waiting on it.
type Outcome struct {
	AccessToken string
	Sealed      string
	OK          bool
	// Status is the answer to give the caller when OK is false: 0 means "carry
	// on as anonymous", 401 and 403 mean "deny".
	Status int
}

// ReuseWindow is how long a finished refresh keeps answering for its key. The
// idp rotates refresh tokens and treats a second exchange of the old one as
// theft (`revokeRefreshToken`, zero reuse tolerance), so a request that was
// already in flight with the old cookie must get the same answer instead of
// starting a new exchange that would revoke the session.
const ReuseWindow = 30 * time.Second

// Flights collapses parallel refreshes of one session into a single token
// exchange, and answers a late caller from the result of the one that just ran.
type Flights struct {
	mu     sync.Mutex
	calls  map[string]*flight
	window time.Duration
	now    func() time.Time
}

type flight struct {
	done    chan struct{}
	outcome Outcome
	at      time.Time // set when the exchange finished
}

// Do runs fn once per key; concurrent callers wait for that result, and a caller
// arriving inside ReuseWindow after it finished gets the same outcome without a
// second exchange. A panic in fn is not an answer: it ends the flight as
// "continue as anonymous" instead of leaving every waiter blocked on a channel
// that never closes.
func (f *Flights) Do(key string, fn func() Outcome) Outcome {
	if f == nil {
		return safeCall(fn)
	}
	f.mu.Lock()
	if f.now == nil {
		f.now = time.Now
	}
	if f.window <= 0 {
		f.window = ReuseWindow
	}
	if f.calls == nil {
		f.calls = make(map[string]*flight)
	}
	if c, ok := f.calls[key]; ok {
		finished := !c.at.IsZero()
		if finished && f.now().Sub(c.at) < f.window {
			out := c.outcome
			f.mu.Unlock()
			return out
		}
		if finished {
			delete(f.calls, key)
		} else {
			f.mu.Unlock()
			<-c.done
			return c.outcome
		}
	}
	c := &flight{done: make(chan struct{})}
	f.calls[key] = c
	f.mu.Unlock()

	out := safeCall(fn)

	f.mu.Lock()
	c.outcome = out
	c.at = f.now()
	close(c.done)
	f.sweepLocked()
	f.mu.Unlock()
	return out
}

// sweepLocked drops finished flights whose window has passed, so the map cannot
// grow with every token the process has ever refreshed.
func (f *Flights) sweepLocked() {
	if len(f.calls) < 64 {
		return
	}
	now := f.now()
	for key, c := range f.calls {
		if !c.at.IsZero() && now.Sub(c.at) >= f.window {
			delete(f.calls, key)
		}
	}
}

// safeCall turns a panic inside the exchange into a zero outcome: the caller
// continues as anonymous and the cookies are cleared, instead of the process
// dying on one bad response.
func safeCall(fn func() Outcome) (out Outcome) {
	defer func() {
		if r := recover(); r != nil {
			out = Outcome{}
		}
	}()
	return fn()
}

// Key hashes a refresh token so the in-memory map never holds a credential.
func Key(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}
