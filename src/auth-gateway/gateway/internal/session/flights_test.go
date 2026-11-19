package session

import (
	"testing"
	"time"
)

// The idp rotates refresh tokens and treats a second exchange of the old one as
// theft, so a late caller with the same key must get the finished answer.
func TestFlightsAnswerALateCaller(t *testing.T) {
	calls := 0
	f := &Flights{}
	first := f.Do("k", func() Outcome { calls++; return Outcome{AccessToken: "t1", OK: true} })
	if !first.OK || first.AccessToken != "t1" {
		t.Fatalf("first = %+v", first)
	}
	second := f.Do("k", func() Outcome { calls++; return Outcome{AccessToken: "t2", OK: true} })
	if calls != 1 {
		t.Fatalf("the exchange ran %d times, want 1", calls)
	}
	if second.AccessToken != "t1" {
		t.Fatalf("late caller got %q, want the finished answer", second.AccessToken)
	}
}

// After the window the key is spent: a new exchange is the right answer again.
func TestFlightsForgetAfterTheWindow(t *testing.T) {
	now := time.Now()
	calls := 0
	f := &Flights{window: time.Minute, now: func() time.Time { return now }}
	f.Do("k", func() Outcome { calls++; return Outcome{OK: true} })
	now = now.Add(2 * time.Minute)
	f.Do("k", func() Outcome { calls++; return Outcome{OK: true} })
	if calls != 2 {
		t.Fatalf("the exchange ran %d times, want 2", calls)
	}
}

// A panic is not an answer: it must end the flight, not hang it. The zero
// outcome is cached for the window, so a retry does not start a second exchange
// of a refresh token the idp has already rotated.
func TestFlightsSurviveAPanic(t *testing.T) {
	now := time.Now()
	calls := 0
	f := &Flights{window: time.Minute, now: func() time.Time { return now }}
	out := f.Do("k", func() Outcome { calls++; panic("boom") })
	if out.OK || out.AccessToken != "" || out.Status != 0 {
		t.Fatalf("panic produced %+v, want the anonymous outcome", out)
	}
	out = f.Do("k", func() Outcome { calls++; return Outcome{AccessToken: "t", OK: true} })
	if out.OK || calls != 1 {
		t.Fatalf("inside the window the panic answer must hold: %+v, calls = %d", out, calls)
	}
	now = now.Add(2 * time.Minute)
	if out = f.Do("k", func() Outcome { calls++; return Outcome{AccessToken: "t", OK: true} }); !out.OK {
		t.Fatalf("the key stayed poisoned after the window: %+v", out)
	}
}

// Waiters on a panicking exchange are released too.
func TestFlightsPanicReleasesWaiters(t *testing.T) {
	f := &Flights{}
	started := make(chan struct{})
	release := make(chan struct{})
	go func() {
		f.Do("k", func() Outcome {
			close(started)
			<-release
			panic("boom")
		})
	}()
	<-started

	waiter := make(chan Outcome, 1)
	go func() { waiter <- f.Do("k", func() Outcome { return Outcome{OK: true} }) }()
	close(release)

	select {
	case got := <-waiter:
		if got.OK {
			t.Fatalf("waiter got %+v, want the panic's anonymous outcome", got)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("a panicking exchange left a waiter blocked")
	}
}

// The map cannot grow with every token the process has ever refreshed.
func TestFlightsSweepFinishedEntries(t *testing.T) {
	now := time.Now()
	f := &Flights{window: time.Second, now: func() time.Time { return now }}
	for i := 0; i < 100; i++ {
		key := string(rune('a'+i%26)) + time.Duration(i).String()
		f.Do(key, func() Outcome { return Outcome{OK: true} })
	}
	now = now.Add(time.Minute)
	f.Do("trigger", func() Outcome { return Outcome{OK: true} })
	if len(f.calls) > 64 {
		t.Fatalf("map still holds %d finished flights", len(f.calls))
	}
}
