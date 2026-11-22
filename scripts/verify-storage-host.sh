#!/usr/bin/env bash
# Prove storage.filenkov.store the way US-07 task 07 describes.
#
#   BASE_URL=https://storage.filenkov.store ./scripts/verify-storage-host.sh
#
# The script curls BASE_URL and prints the status and body it received. It
# does not invent a pass: a probe that was not sent is SKIP, and the run
# exits 2. A probe that was sent and did not match exits 1.
#
# Cookies are raw __Secure-open_access values from the operator's environment.
# None are stored in this file.
#   AUTH_COOKIE_FAMILY AUTH_COOKIE_ADMIN AUTH_COOKIE_STRANGER AUTH_COOKIE_BLOCKED
#
# A download past 60s is timed only when DOWNLOAD_URL is set (a URL that
# actually streams for longer than a minute). Otherwise that row is NOT RUN.
# DNS, the certificate, and gateway logs are not checked here.
#
# Exit: 0 every probe ran and matched; 1 a sent probe did not match; 2 a
# required probe was not run.

set -euo pipefail

CONNECT_TIMEOUT=${CONNECT_TIMEOUT:-5}
HTTP_TIMEOUT=${HTTP_TIMEOUT:-20}
DOWNLOAD_MAX_TIME=${DOWNLOAD_MAX_TIME:-120}
TLS_VERIFY=${TLS_VERIFY:-1}

if ! command -v curl >/dev/null 2>&1; then
    printf 'verify-storage-host: curl is not installed\n' >&2
    exit 1
fi
if [ -z "${BASE_URL:-}" ]; then
    printf 'verify-storage-host: set BASE_URL (for example https://storage.filenkov.store). This script does not pick a host.\n' >&2
    exit 1
fi
BASE_URL=${BASE_URL%/}

umask 077
work=$(mktemp -d "${TMPDIR:-/tmp}/verify-storage-host.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
body=$work/body
err=$work/curl.err

failures=0
incomplete=0

emit() { # kind path code expected result
    printf '%-12s %-18s %-6s %-14s %s\n' "$1" "$2" "$3" "$4" "$5"
}

# curl_probe path [cookie-value] -> prints "CODE" and writes the body.
# CODE is 000 when curl cannot get an answer.
curl_probe() {
    local path=$1 cookie=${2-}
    local -a args=(
        --silent --show-error
        --output "$body"
        --write-out '%{http_code}'
        --connect-timeout "$CONNECT_TIMEOUT"
        --max-time "$HTTP_TIMEOUT"
        --url "${BASE_URL}${path}"
    )
    if [ "$TLS_VERIFY" != "1" ]; then
        args+=(--insecure)
    fi
    if [ -n "$cookie" ]; then
        case "$cookie" in
            *[[:space:]\"\\]*)
                printf 'verify-storage-host: a cookie must be the raw value, not a header line\n' >&2
                exit 1
                ;;
        esac
        args+=(--header "Cookie: __Secure-open_access=${cookie}")
    fi
    local code
    code=$(curl "${args[@]}" 2>"$err") || code=000
    printf '%s' "${code:-000}"
}

show_body() {
    printf '  body: '
    if [ -s "$body" ]; then
        tr '\n' ' ' < "$body" | cut -c1-240
        printf '\n'
    else
        printf '(empty)\n'
    fi
    if [ -s "$err" ]; then
        printf '  curl: '
        tr '\n' ' ' < "$err" | cut -c1-200
        printf '\n'
    fi
}

# expect_status kind path want [cookie]
expect_status() {
    local kind=$1 path=$2 want=$3 cookie=${4-}
    : >"$body"
    : >"$err"
    local code
    code=$(curl_probe "$path" "$cookie")
    if [ "$code" = "$want" ]; then
        emit "$kind" "$path" "$code" "$want" "PASS"
        show_body
        return 0
    fi
    local note=""
    if [ "$code" = "000" ]; then
        note=" (no answer)"
    fi
    emit "$kind" "$path" "$code" "$want" "FAIL${note}"
    show_body
    failures=$((failures + 1))
}

# expect_json kind path code error-name [cookie]
expect_json() {
    local kind=$1 path=$2 want_code=$3 want_name=$4 cookie=${5-}
    : >"$body"
    : >"$err"
    local code got want
    code=$(curl_probe "$path" "$cookie")
    got=$(tr -d '\n' <"$body" 2>/dev/null || true)
    want="{\"error\":\"${want_name}\"}"
    if [ "$code" = "$want_code" ] && [ "$got" = "$want" ]; then
        emit "$kind" "$path" "$code" "$want_code $want_name" "PASS"
        show_body
        return 0
    fi
    emit "$kind" "$path" "$code" "$want_code $want_name" "FAIL"
    show_body
    failures=$((failures + 1))
}

skip_row() { # kind path expected reason
    emit "$1" "$2" "-" "$3" "SKIP ($4)"
    incomplete=$((incomplete + 1))
}

printf '# base %s\n' "$BASE_URL"
printf '# anonymous /health and /api/files always run. Identity rows run only when the matching cookie is set.\n'
printf '# a download past 60s runs only when DOWNLOAD_URL is set.\n\n'
emit KIND PATH CODE EXPECT RESULT

expect_status anon /health 200
expect_json anon /api/files 401 unauthorized

identity_pair() { # kind cookie-value
    local kind=$1 cookie=$2
    local forbidden=forbidden
    case "$kind" in
        blocked) forbidden=blocked ;;
    esac
    case "$kind" in
        family|admin)
            expect_status "$kind" / 200 "$cookie"
            expect_status "$kind" /api/files 200 "$cookie"
            ;;
        stranger|blocked)
            expect_json "$kind" / 403 "$forbidden" "$cookie"
            expect_json "$kind" /api/files 403 "$forbidden" "$cookie"
            ;;
    esac
}

if [ -n "${AUTH_COOKIE_FAMILY:-}" ]; then
    identity_pair family "$AUTH_COOKIE_FAMILY"
else
    skip_row family / "200" "AUTH_COOKIE_FAMILY is not set"
    skip_row family /api/files "200" "AUTH_COOKIE_FAMILY is not set"
fi
if [ -n "${AUTH_COOKIE_ADMIN:-}" ]; then
    identity_pair admin "$AUTH_COOKIE_ADMIN"
else
    skip_row admin / "200" "AUTH_COOKIE_ADMIN is not set"
    skip_row admin /api/files "200" "AUTH_COOKIE_ADMIN is not set"
fi
if [ -n "${AUTH_COOKIE_STRANGER:-}" ]; then
    identity_pair stranger "$AUTH_COOKIE_STRANGER"
else
    skip_row stranger / "403 forbidden" "AUTH_COOKIE_STRANGER is not set"
    skip_row stranger /api/files "403 forbidden" "AUTH_COOKIE_STRANGER is not set"
fi
if [ -n "${AUTH_COOKIE_BLOCKED:-}" ]; then
    identity_pair blocked "$AUTH_COOKIE_BLOCKED"
else
    skip_row blocked / "403 blocked" "AUTH_COOKIE_BLOCKED is not set"
    skip_row blocked /api/files "403 blocked" "AUTH_COOKIE_BLOCKED is not set"
fi

if [ -n "${DOWNLOAD_URL:-}" ]; then
    : >"$body"
    : >"$err"
    dl_meta=$work/dl
    dl_args=(
        --silent --show-error
        --output /dev/null
        --write-out '%{http_code} %{time_total}'
        --connect-timeout "$CONNECT_TIMEOUT"
        --max-time "$DOWNLOAD_MAX_TIME"
        --url "$DOWNLOAD_URL"
    )
    if [ "$TLS_VERIFY" != "1" ]; then
        dl_args+=(--insecure)
    fi
    if [ -n "${AUTH_COOKIE_FAMILY:-}" ]; then
        dl_args+=(--header "Cookie: __Secure-open_access=${AUTH_COOKIE_FAMILY}")
    elif [ -n "${AUTH_COOKIE_ADMIN:-}" ]; then
        dl_args+=(--header "Cookie: __Secure-open_access=${AUTH_COOKIE_ADMIN}")
    fi
    if ! dl_line=$(curl "${dl_args[@]}" 2>"$err"); then
        dl_line="000 0"
    fi
    dl_code=${dl_line%% *}
    dl_time=${dl_line##* }
    # bash cannot compare decimals. awk prints 1 when the transfer ran past 60s.
    past=$(awk -v t="$dl_time" 'BEGIN { print (t+0 > 60) ? 1 : 0 }')
    if [ "$dl_code" = "200" ] && [ "$past" = "1" ]; then
        emit download "${DOWNLOAD_URL}" "$dl_code" ">60s" "PASS ${dl_time}s"
    else
        emit download "${DOWNLOAD_URL}" "$dl_code" ">60s 200" "FAIL ${dl_time}s"
        if [ -s "$err" ]; then
            printf '  curl: '
            tr '\n' ' ' <"$err" | cut -c1-200
            printf '\n'
        fi
        failures=$((failures + 1))
    fi
else
    emit download "-" "-" ">60s" "NOT RUN (set DOWNLOAD_URL to a transfer that lasts past 60s)"
    incomplete=$((incomplete + 1))
fi

printf '\nverify-storage-host: %d probe(s) failed, %d not run\n' "$failures" "$incomplete"
if [ "$failures" -gt 0 ]; then
    printf 'verify-storage-host: FAIL\n'
    exit 1
fi
if [ "$incomplete" -gt 0 ]; then
    printf 'verify-storage-host: NOT PROVEN\n'
    exit 2
fi
printf 'verify-storage-host: PASS\n'
