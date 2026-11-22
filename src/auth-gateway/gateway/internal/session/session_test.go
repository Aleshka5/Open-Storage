package session

import (
	"crypto/rand"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func key(t *testing.T) string {
	t.Helper()
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		t.Fatal(err)
	}
	return base64.StdEncoding.EncodeToString(raw)
}

func sealer(t *testing.T) *Sealer {
	t.Helper()
	s, err := NewSealer(key(t), ".filenkov.store", 5*time.Minute, 168*time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestSealOpenRoundTrip(t *testing.T) {
	s := sealer(t)
	sealed, err := s.Seal(State{Subject: "sub-1", RefreshToken: "rt-1", SID: "sid-1"})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(sealed, "rt-1") || strings.Contains(sealed, "sub-1") {
		t.Fatal("the sealed value must not carry plaintext")
	}
	got, err := s.Open(sealed)
	if err != nil {
		t.Fatal(err)
	}
	if got.Subject != "sub-1" || got.RefreshToken != "rt-1" || got.SID != "sid-1" {
		t.Fatalf("state = %+v", got)
	}
}

func TestOpenRejectsForgedAndExpired(t *testing.T) {
	s := sealer(t)
	sealed, err := s.Seal(State{Subject: "sub-1"})
	if err != nil {
		t.Fatal(err)
	}
	// Flip one byte of the ciphertext.
	raw, _ := base64.RawURLEncoding.DecodeString(sealed)
	raw[len(raw)-1] ^= 0xff
	if _, err := s.Open(base64.RawURLEncoding.EncodeToString(raw)); err == nil {
		t.Fatal("a tampered cookie must not open")
	}
	if _, err := s.Open("not base64 at all"); err == nil {
		t.Fatal("a garbage cookie must not open")
	}

	// A cookie sealed by another key must not open here.
	other := sealer(t)
	foreign, _ := other.Seal(State{Subject: "sub-1"})
	if _, err := s.Open(foreign); err == nil {
		t.Fatal("a cookie from another key must not open")
	}

	clock := time.Now()
	s.now = func() time.Time { return clock }
	old, _ := s.Seal(State{Subject: "sub-1"})
	clock = clock.Add(169 * time.Hour)
	if _, err := s.Open(old); err == nil {
		t.Fatal("an idled-out session must not open")
	}
}

func TestCookieAttributes(t *testing.T) {
	s := sealer(t)
	for _, c := range []*http.Cookie{s.AccessCookie("a"), s.SessionCookie("b"), s.FlowCookie("c")} {
		if !c.HttpOnly || !c.Secure || c.SameSite != http.SameSiteLaxMode || c.Path != "/" {
			t.Fatalf("cookie %s attributes = %+v", c.Name, c)
		}
		if c.Domain != ".filenkov.store" {
			t.Fatalf("cookie %s domain = %q", c.Name, c.Domain)
		}
		if !strings.HasPrefix(c.Name, "__Secure-") {
			t.Fatalf("cookie name %q must carry the __Secure- prefix", c.Name)
		}
	}
	if got := int(s.AccessCookie("a").MaxAge); got != 300 {
		t.Fatalf("access max-age = %d", got)
	}
	if s.SessionCookie("b").MaxAge != int((168 * time.Hour).Seconds()) {
		t.Fatalf("session max-age = %d", s.SessionCookie("b").MaxAge)
	}
	for _, c := range s.Clear() {
		if c.MaxAge != -1 || c.Value != "" {
			t.Fatalf("clear cookie %s = %+v", c.Name, c)
		}
	}
}

func TestFlightsCollapseToOneExchange(t *testing.T) {
	f := &Flights{}
	var calls int32
	const callers = 8
	var wg sync.WaitGroup
	outcomes := make([]Outcome, callers)
	start := make(chan struct{})
	for i := 0; i < callers; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			<-start
			outcomes[i] = f.Do("key-1", func() Outcome {
				atomic.AddInt32(&calls, 1)
				time.Sleep(20 * time.Millisecond)
				return Outcome{AccessToken: "fresh", OK: true}
			})
		}(i)
	}
	close(start)
	wg.Wait()
	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Fatalf("%d exchanges for %d parallel refreshes, want 1", got, callers)
	}
	for i, o := range outcomes {
		if !o.OK || o.AccessToken != "fresh" {
			t.Fatalf("caller %d got %+v", i, o)
		}
	}
	// A call that arrives right after the flight finished is answered from it: the
	// idp rotates refresh tokens, so a second exchange of the same one would
	// revoke the session (see TestFlightsAnswerALateCaller).
	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Fatal("flights leaked")
	}
	if late := f.Do("key-1", func() Outcome { atomic.AddInt32(&calls, 1); return Outcome{} }); !late.OK {
		t.Fatalf("late caller got %+v", late)
	}
	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Fatalf("a late caller started a second exchange (calls = %d)", got)
	}
}

func TestRewriteRequestCookies(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	r.AddCookie(&http.Cookie{Name: NameAccess, Value: "stale"})
	r.AddCookie(&http.Cookie{Name: "other", Value: "keep"})
	RewriteRequestCookies(r, map[string]string{NameAccess: "fresh", NameSession: "new"})
	if got := Value(r, NameAccess); got != "fresh" {
		t.Fatalf("access = %q", got)
	}
	if got := Value(r, NameSession); got != "new" {
		t.Fatalf("session = %q", got)
	}
	if got := Value(r, "other"); got != "keep" {
		t.Fatalf("unrelated cookie = %q", got)
	}
}
