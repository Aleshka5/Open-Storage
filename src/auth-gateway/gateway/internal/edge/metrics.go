package edge

import (
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
)

// limiter is a fixed-window counter per client IP. In process, one replica: the
// contract forbids a second counter in front of the idp's brute-force protection.
type limiter struct {
	limit  int
	window time.Duration
	mu     sync.Mutex
	seen   map[string]*window
}

type window struct {
	start time.Time
	count int
}

func newLimiter(limit int, per time.Duration) *limiter {
	if per <= 0 {
		per = time.Minute
	}
	return &limiter{limit: limit, window: per, seen: make(map[string]*window)}
}

func (l *limiter) allow(ip string) bool {
	if l == nil || l.limit <= 0 {
		return true
	}
	now := time.Now()
	l.mu.Lock()
	defer l.mu.Unlock()
	w, ok := l.seen[ip]
	if !ok || now.Sub(w.start) >= l.window {
		l.seen[ip] = &window{start: now, count: 1}
		if len(l.seen) > 10000 {
			l.pruneLocked(now)
		}
		return true
	}
	w.count++
	return w.count <= l.limit
}

func (l *limiter) pruneLocked(now time.Time) {
	for ip, w := range l.seen {
		if now.Sub(w.start) >= l.window {
			delete(l.seen, ip)
		}
	}
}

// metrics is a small Prometheus text endpoint. It holds only what the contract
// names, so a dashboard cannot depend on something this process invents.
type metrics struct {
	mu       sync.Mutex
	requests map[requestKey]int64
	duration map[string]time.Duration
	observed map[string]int64
	wsActive map[string]int

	refresh     map[string]int64
	idpRequests map[string]map[int]int64
}

type requestKey struct {
	host, route, policy string
	status              int
}

func newMetrics() *metrics {
	return &metrics{
		requests:    make(map[requestKey]int64),
		duration:    make(map[string]time.Duration),
		observed:    make(map[string]int64),
		wsActive:    make(map[string]int),
		refresh:     make(map[string]int64),
		idpRequests: make(map[string]map[int]int64),
	}
}

func (m *metrics) count(host, route, policy string, status int) {
	m.mu.Lock()
	m.requests[requestKey{host, route, policy, status}]++
	m.mu.Unlock()
}

func (m *metrics) observe(host, route string, d time.Duration) {
	key := host + "|" + route
	m.mu.Lock()
	m.duration[key] += d
	m.observed[key]++
	m.mu.Unlock()
}

// wsActive tracks WebSocket upgrades in flight per host.
func (m *metrics) wsDelta(host string, delta int) {
	m.mu.Lock()
	m.wsActive[host] += delta
	if m.wsActive[host] < 0 {
		m.wsActive[host] = 0
	}
	m.mu.Unlock()
}

// Refresh counts one token exchange by honest result: `ok`, `invalid_grant`
// (the idp said no), `idp_error` (it answered 5xx) or `transport_error` (it did
// not answer). Folding an outage into `invalid_grant` made a dead idp look like a
// signed-out user.
func (m *metrics) Refresh(result string) {
	if result == "" {
		result = "unknown"
	}
	m.mu.Lock()
	m.refresh[result]++
	m.mu.Unlock()
}

// IdP counts one call to the identity provider.
func (m *metrics) IdP(op string, status int) {
	m.mu.Lock()
	if m.idpRequests[op] == nil {
		m.idpRequests[op] = make(map[int]int64)
	}
	m.idpRequests[op][status]++
	m.mu.Unlock()
}

func (m *metrics) render() []byte {
	m.mu.Lock()
	defer m.mu.Unlock()
	var b strings.Builder

	b.WriteString("# TYPE gateway_requests_total counter\n")
	keys := make([]requestKey, 0, len(m.requests))
	for k := range m.requests {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool { return fmt.Sprint(keys[i]) < fmt.Sprint(keys[j]) })
	for _, k := range keys {
		fmt.Fprintf(&b, "gateway_requests_total{host=%q,route=%q,policy=%q,status=\"%d\"} %d\n",
			k.host, k.route, k.policy, k.status, m.requests[k])
	}

	b.WriteString("# TYPE gateway_request_duration_seconds_sum counter\n")
	obs := make([]string, 0, len(m.duration))
	for k := range m.duration {
		obs = append(obs, k)
	}
	sort.Strings(obs)
	for _, k := range obs {
		host, route, _ := strings.Cut(k, "|")
		fmt.Fprintf(&b, "gateway_request_duration_seconds_sum{host=%q,route=%q} %.3f\n", host, route, m.duration[k].Seconds())
		fmt.Fprintf(&b, "gateway_request_duration_seconds_count{host=%q,route=%q} %d\n", host, route, m.observed[k])
	}

	b.WriteString("# TYPE gateway_ws_active gauge\n")
	hosts := make([]string, 0, len(m.wsActive))
	for h := range m.wsActive {
		hosts = append(hosts, h)
	}
	sort.Strings(hosts)
	for _, h := range hosts {
		fmt.Fprintf(&b, "gateway_ws_active{host=%q} %d\n", h, m.wsActive[h])
	}

	b.WriteString("# TYPE gateway_token_refresh_total counter\n")
	results := make([]string, 0, len(m.refresh))
	for result := range m.refresh {
		results = append(results, result)
	}
	sort.Strings(results)
	for _, result := range results {
		fmt.Fprintf(&b, "gateway_token_refresh_total{result=%q} %d\n", result, m.refresh[result])
	}

	b.WriteString("# TYPE gateway_idp_request_total counter\n")
	ops := make([]string, 0, len(m.idpRequests))
	for op := range m.idpRequests {
		ops = append(ops, op)
	}
	sort.Strings(ops)
	for _, op := range ops {
		for status, n := range m.idpRequests[op] {
			fmt.Fprintf(&b, "gateway_idp_request_total{op=%q,status=\"%d\"} %d\n", op, status, n)
		}
	}
	return []byte(b.String())
}
