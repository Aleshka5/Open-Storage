#!/usr/bin/env bash
# Edge check: one request per SSO host, through the proxy and straight to the
# gateway.
#
#   ./scripts/verify-edge.sh
#   AUTH_COOKIE_SIGNED_IN=... AUTH_COOKIE_ADMIN=... ./scripts/verify-edge.sh
#
# GET only. Nothing is written outside a private temp directory, nothing is
# logged. Safe to run against a live stand.
#
# Exit: 0 when every run row matched its expected code, 1 otherwise. A missing
# cookie prints SKIP rows and never fails the run; a failed row always does.
#
# Contracts that own the numbers below:
#   docs/auth-gateway/gateway/api-contract.md (§Startup rules, §`/auth`, §Probes and metrics)
#   docs/auth-gateway/external-contracts/identity-v1.md (§Errors from the edge)

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(dirname -- "$script_dir")

GATEWAY_ADDR=${GATEWAY_ADDR:-127.0.0.1:8083} # live gateway, deploy/auth-gateway/.env.example
PROXY_SCHEME=${PROXY_SCHEME:-https}          # Caddy terminates TLS, proxy contract
CONNECT_TIMEOUT=${CONNECT_TIMEOUT:-5}
HTTP_TIMEOUT=${HTTP_TIMEOUT:-20}
TLS_VERIFY=${TLS_VERIFY:-1}                  # 0 adds --insecure; meet. and hermes. use `tls internal`

umask 077
work=$(mktemp -d "${TMPDIR:-/tmp}/verify-edge.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
curl_err=$work/curl.err

if ! command -v curl >/dev/null 2>&1; then
    printf 'verify-edge: curl is not installed\n' >&2
    exit 1
fi
: > "$curl_err"

# --- the edge, in one place ------------------------------------------------
#
# The gateway contract owns the host list (§Hosts). When
# src/auth-gateway/gateway/config.yaml exists it is the runtime copy of that
# list, and the drift check at the end of this run compares the two. Do not
# copy this list anywhere else.

HOSTS=(
    filenkov.store
    id.filenkov.store
    storage.filenkov.store
    image.filenkov.store
    rag.filenkov.store
    audio.filenkov.store
    llm.filenkov.store
    observer.filenkov.store
)

# Expected status codes, owned by the same contract (§Hosts, §Policies) and by
# identity-v1 §Errors from the edge. A space-separated list accepts any code in
# it. Rows that reach a product upstream also depend on that upstream: a 502
# means the upstream did not answer, not that policy is wrong.
#
# Anonymous: no cookie at all.
#   Browser navigation to a non-public host is 302 to /auth/login?return_to=…
#   llm.filenkov.store is admin-only: a browser gets 302, a JSON client 401,
#   a signed-in non-admin 403 — all three are contract answers.
declare -A EXPECT_ANON=(
    [filenkov.store]="200"   # public, resume page
    [mvp.filenkov.store]="200" # public, resume page (MVP stand, EXTRA_HOSTS)
    [storage.filenkov.store]="302"
    [image.filenkov.store]="302"
    [rag.filenkov.store]="302"
    [audio.filenkov.store]="302"
    [llm.filenkov.store]="302 401 403"
    [observer.filenkov.store]="302"
    [id.filenkov.store]="302 200" # Keycloak welcome; Caddy also 403s sources outside the lan gate
)

# A signed-in account with no realm roles. storage, image, rag and llm need a
# role it does not have (403); audio and observer guard /** with `session` (200).
declare -A EXPECT_SIGNED_IN=(
    [filenkov.store]="200"
    [mvp.filenkov.store]="200"
    [storage.filenkov.store]="403"
    [image.filenkov.store]="403"
    [rag.filenkov.store]="403"
    [audio.filenkov.store]="200"
    [llm.filenkov.store]="403"
    [observer.filenkov.store]="200"
    [id.filenkov.store]="302 200"
)

# The `admin` realm role opens every host.
declare -A EXPECT_ADMIN=(
    [filenkov.store]="200"
    [mvp.filenkov.store]="200"
    [storage.filenkov.store]="200"
    [image.filenkov.store]="200"
    [rag.filenkov.store]="200"
    [audio.filenkov.store]="200"
    [llm.filenkov.store]="200"
    [observer.filenkov.store]="200"
    [id.filenkov.store]="302 200"
)

# --- checks ----------------------------------------------------------------

pass=0
failures=0
skips=0
drift=0

emit() { # host surface kind code expected result
    printf '%-23s %-8s %-10s %-5s %-12s %s\n' "$1" "$2" "$3" "$4" "$5" "$6"
}

matches() { # code "expected-list"
    local code=$1 want
    for want in $2; do
        if [ "$code" = "$want" ]; then
            return 0
        fi
    done
    return 1
}

curl_reason() {
    local line
    line=$(tail -n 1 "$curl_err" 2>/dev/null || true)
    printf '%s' "$line" | cut -c1-110
}

fetch_code() { # surface host cookie-conf -> http code, "000" when unanswered
    local surface=$1 host=$2 conf=$3 code
    local -a args=(
        --silent --show-error
        --output /dev/null
        --write-out '%{http_code}'
        --connect-timeout "$CONNECT_TIMEOUT"
        --max-time "$HTTP_TIMEOUT"
    )
    if [ "$TLS_VERIFY" != "1" ]; then
        args+=(--insecure)
    fi
    if [ -n "$conf" ]; then
        args+=(--config "$conf")
    fi
    case "$surface" in
        proxy) args+=(--url "${PROXY_SCHEME}://${host}/") ;;
        gateway) args+=(--url "http://${GATEWAY_ADDR}/" --header "Host: ${host}") ;;
        *) return 1 ;;
    esac
    code=$(curl "${args[@]}" 2> "$curl_err") || code=000
    printf '%s' "${code:-000}"
}

report_row() { # kind host surface expected cookie-conf
    local kind=$1 host=$2 surface=$3 expected=$4 conf=${5-}
    local code note=''

    code=$(fetch_code "$surface" "$host" "$conf")
    if matches "$code" "$expected"; then
        emit "$host" "$surface" "$kind" "$code" "$expected" "PASS"
        pass=$((pass + 1))
        return 0
    fi

    if [ "$code" = "000" ]; then
        note=" ($(curl_reason))"
    fi
    emit "$host" "$surface" "$kind" "$code" "$expected" "FAIL${note}"
    failures=$((failures + 1))
}

skip_row() { # kind host surface expected reason
    emit "$2" "$3" "$1" "-" "$4" "SKIP ($5)"
    skips=$((skips + 1))
}

cookie_conf() { # name cookie-value -> writes a 0600 curl config, prints path
    local name=$1 value=$2 path
    case "$value" in
        *[[:space:]\"\\]*)
            printf 'verify-edge: %s must be the raw cookie value, not a header line\n' "$name" >&2
            exit 1
            ;;
    esac
    path=$work/$name.conf
    printf 'header = "Cookie: __Secure-open_access=%s"\n' "$value" > "$path"
    printf '%s' "$path"
}

# Hosts to leave out of this run. The MVP stand renames the apex, so it skips
# filenkov.store and adds mvp.filenkov.store through EXTRA_HOSTS.
if [ -n "${SKIP_HOSTS:-}" ]; then
    filtered=()
    for host in "${HOSTS[@]}"; do
        drop=0
        for skipped in $SKIP_HOSTS; do
            [ "$skipped" = "$host" ] && drop=1
        done
        [ "$drop" = "0" ] && filtered+=("$host")
    done
    HOSTS=("${filtered[@]}")
fi

# Names added for a stand whose config renames a host. They are not part of
# the committed config.yaml, so the default run does not list them.
if [ -n "${EXTRA_HOSTS:-}" ]; then
    for extra in $EXTRA_HOSTS; do
        HOSTS+=("$extra")
    done
fi

# Every host needs an expectation before anything is requested.
for host in "${HOSTS[@]}"; do
    if [ -z "${EXPECT_ANON[$host]+set}" ]; then
        printf 'verify-edge: no expected code for host %s; add it to the block at the top\n' "$host" >&2
        exit 1
    fi
    if [ -z "${EXPECT_SIGNED_IN[$host]+set}" ] || [ -z "${EXPECT_ADMIN[$host]+set}" ]; then
        printf 'verify-edge: host %s is missing a signed-in or admin expectation\n' "$host" >&2
        exit 1
    fi
done

# --- run -------------------------------------------------------------------

printf '# proxy   %s://<host>/\n' "$PROXY_SCHEME"
printf '# gateway http://%s/ with Host: <host>\n' "$GATEWAY_ADDR"
if [ "$TLS_VERIFY" != "1" ]; then
    printf '# TLS_VERIFY=0: certificates are not checked; meet. and hermes. use tls internal\n'
fi
printf '\n'
emit HOST SURFACE KIND CODE EXPECT RESULT

for host in "${HOSTS[@]}"; do
    for surface in proxy gateway; do
        report_row anon "$host" "$surface" "${EXPECT_ANON[$host]}"
    done
done

if [ -n "${AUTH_COOKIE_SIGNED_IN:-}" ]; then
    conf=$(cookie_conf signed-in "$AUTH_COOKIE_SIGNED_IN")
    for host in "${HOSTS[@]}"; do
        for surface in proxy gateway; do
            report_row signed-in "$host" "$surface" "${EXPECT_SIGNED_IN[$host]}" "$conf"
        done
    done
else
    for host in "${HOSTS[@]}"; do
        for surface in proxy gateway; do
            skip_row signed-in "$host" "$surface" "${EXPECT_SIGNED_IN[$host]}" \
                "AUTH_COOKIE_SIGNED_IN is not set"
        done
    done
fi

if [ -n "${AUTH_COOKIE_ADMIN:-}" ]; then
    conf=$(cookie_conf admin "$AUTH_COOKIE_ADMIN")
    for host in "${HOSTS[@]}"; do
        for surface in proxy gateway; do
            report_row admin "$host" "$surface" "${EXPECT_ADMIN[$host]}" "$conf"
        done
    done
else
    for host in "${HOSTS[@]}"; do
        for surface in proxy gateway; do
            skip_row admin "$host" "$surface" "${EXPECT_ADMIN[$host]}" \
                "AUTH_COOKIE_ADMIN is not set"
        done
    done
fi

# --- host list drift -------------------------------------------------------
#
# src/auth-gateway/gateway/config.yaml is the runtime owner of the host list.
# A host on one side and not the other means this check no longer covers the
# edge, so it is a failure, not a warning.

CONFIG_YAML=${GATEWAY_CONFIG:-$repo_root/src/auth-gateway/gateway/config.yaml}
# A stand that renames the apex (mvp.filenkov.store) serves a different host set
# by design, so it runs with DRIFT_CHECK=0 and says so in the Makefile target.
DRIFT_CHECK=${DRIFT_CHECK:-1}

if [ "$DRIFT_CHECK" = "1" ] && [ -f "$CONFIG_YAML" ]; then
    mapfile -t config_hosts < <(
        awk '
            /^hosts:[[:space:]]*$/ { in_hosts = 1; next }
            in_hosts && /^[^[:space:]#]/ { in_hosts = 0 }
            in_hosts && /^[[:space:]]*-[[:space:]]+host:/ {
                sub(/^[[:space:]]*-[[:space:]]+host:[[:space:]]*/, "")
                gsub(/["\047]/, "")
                sub(/[[:space:]]+$/, "")
                print
            }
        ' "$CONFIG_YAML"
    )

    for host in "${HOSTS[@]}"; do
        found=0
        for config_host in "${config_hosts[@]}"; do
            if [ "$config_host" = "$host" ]; then
                found=1
            fi
        done
        if [ "$found" = "0" ]; then
            printf 'verify-edge: host %s is in this script but not in %s\n' "$host" "$CONFIG_YAML" >&2
            drift=1
        fi
    done
    for config_host in "${config_hosts[@]}"; do
        found=0
        for host in "${HOSTS[@]}"; do
            if [ "$host" = "$config_host" ]; then
                found=1
            fi
        done
        if [ "$found" = "0" ]; then
            printf 'verify-edge: host %s is in %s but not in this script\n' "$config_host" "$CONFIG_YAML" >&2
            drift=1
        fi
    done
fi

# --- summary ---------------------------------------------------------------

total=$((pass + failures + skips))
printf '\nverify-edge: %d rows, %d passed, %d failed, %d skipped\n' \
    "$total" "$pass" "$failures" "$skips"

if [ "$failures" -gt 0 ] || [ "$drift" != "0" ]; then
    if [ "$drift" != "0" ]; then
        printf 'verify-edge: the host list and %s disagree\n' "$CONFIG_YAML" >&2
    fi
    printf 'verify-edge: FAIL\n'
    exit 1
fi

printf 'verify-edge: PASS\n'
