#!/usr/bin/env bash
# Stand check used by `make verify` (deploy/auth-gateway).
#
#   ./scripts/golden.sh
#
# Four steps, in order:
#   1. scripts/verify-edge.sh — one request per SSO host, proxy and gateway.
#   2. GET /healthz on the gateway — process up, config valid.
#   3. GET /readyz  on the gateway — idp discovery and JWKS loaded.
#   4. `caddy validate` on deploy/auth-gateway/Caddyfile.
#
# Steps 2 and 3 follow docs/auth-gateway/gateway/API/Message-contract.md §Probes.
# /readyz does not check product upstreams, so a green /readyz with a red edge
# row means an upstream, not the identity layer.
#
# Exit: 0 every step passed or was skipped, 1 otherwise.

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(dirname -- "$script_dir")

GATEWAY_ADDR=${GATEWAY_ADDR:-127.0.0.1:8080}
CADDYFILE=${CADDYFILE:-$repo_root/deploy/auth-gateway/Caddyfile}
CONNECT_TIMEOUT=${CONNECT_TIMEOUT:-3}
HTTP_TIMEOUT=${HTTP_TIMEOUT:-10}

if ! command -v curl >/dev/null 2>&1; then
    printf 'golden: curl is not installed\n' >&2
    exit 1
fi

pass=0
failures=0
skips=0

report() { # STATUS message
    printf '%-5s %s\n' "$1" "$2"
}

probe() { # path expected-code
    local path=$1 expected=$2 url code
    url="http://${GATEWAY_ADDR}${path}"
    code=$(curl --silent --show-error --output /dev/null \
        --write-out '%{http_code}' \
        --connect-timeout "$CONNECT_TIMEOUT" --max-time "$HTTP_TIMEOUT" \
        --url "$url" 2>/dev/null) || code=000
    if [ "$code" = "$expected" ]; then
        report PASS "${url} ${code}"
        pass=$((pass + 1))
        return 0
    fi
    report FAIL "${url} ${code:-000} (expected ${expected})"
    failures=$((failures + 1))
}

edge_check() {
    if [ ! -f "$script_dir/verify-edge.sh" ]; then
        report FAIL "scripts/verify-edge.sh is missing"
        failures=$((failures + 1))
        return 0
    fi
    if bash "$script_dir/verify-edge.sh"; then
        report PASS "scripts/verify-edge.sh"
        pass=$((pass + 1))
    else
        report FAIL "scripts/verify-edge.sh"
        failures=$((failures + 1))
    fi
}

caddy_check() {
    local out
    if [ ! -f "$CADDYFILE" ]; then
        # Allowed only while the proxy is not written yet.
        report SKIP "caddy validate: ${CADDYFILE#"$repo_root"/} does not exist yet"
        skips=$((skips + 1))
        return 0
    fi
    if ! command -v caddy >/dev/null 2>&1; then
        report SKIP "caddy validate: caddy is not installed"
        skips=$((skips + 1))
        return 0
    fi
    if out=$(caddy validate --adapter caddyfile --config "$CADDYFILE" 2>&1); then
        report PASS "caddy validate ${CADDYFILE#"$repo_root"/}"
        pass=$((pass + 1))
    else
        report FAIL "caddy validate ${CADDYFILE#"$repo_root"/}"
        printf '%s\n' "$out" | sed -n '/"level":"info"/!p' | tail -n 6
        failures=$((failures + 1))
    fi
}

printf 'golden: stand check at http://%s\n\n' "$GATEWAY_ADDR"
edge_check
probe /healthz 200
probe /readyz 200
caddy_check

printf '\n'
if [ "$failures" -gt 0 ]; then
    printf 'golden: %d passed, %d failed, %d skipped — FAIL\n' "$pass" "$failures" "$skips"
    exit 1
fi
printf 'golden: %d passed, %d failed, %d skipped — PASS\n' "$pass" "$failures" "$skips"
