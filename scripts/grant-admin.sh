#!/usr/bin/env bash
# Grant the realm role `admin` to one account, through the Keycloak Admin API.
#
#   scripts/grant-admin.sh <email>
#
# Contract: docs/auth-gateway/idp/init.md — §Roles, §Bootstrap.
# Keycloak has no "first user is admin" rule, so an operator grants `admin` to
# the first Google account by hand, with this script, after its first login.
#
# Credentials: the `gateway-admin` service account. IDP_ADMIN_SECRET is read
# from the environment first, then from deploy/auth-gateway/.env. It is never
# printed, and it never reaches argv: the token request body and the bearer
# header are written to 0600 files inside a 0700 temporary directory.
#
# Exit: 0 the role is present (granted now or before), 1 error, 2 no user with
# that email.

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(dirname -- "$script_dir")

ENV_FILE=${ENV_FILE:-$repo_root/deploy/auth-gateway/.env}
ROLE='admin'
HTTP_TIMEOUT=${HTTP_TIMEOUT:-15}

umask 077
work=$(mktemp -d "${TMPDIR:-/tmp}/grant-admin.XXXXXX")
trap 'rm -rf -- "$work"' EXIT

die() {
    printf 'grant-admin: %s\n' "$*" >&2
    exit 1
}

die_code() {
    local code=$1
    shift
    printf 'grant-admin: %s\n' "$*" >&2
    exit "$code"
}

# Percent-encode stdin, without a trailing newline. Values never have to
# travel as an argument.
urlencode() { jq -Rjr '@uri'; }

# Value of NAME from the env file. Empty when the file or the key is absent.
env_file_value() {
    local name=$1 line
    [ -r "$ENV_FILE" ] || return 0
    line=$(sed -n "s/^[[:space:]]*${name}[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" | tail -n 1)
    line=${line%$'\r'}
    line=${line#\"}
    line=${line%\"}
    line=${line#\'}
    line=${line%\'}
    printf '%s' "$line"
}

# Environment wins over the env file, which wins over the default.
setting() {
    local name=$1 default=${2-} value
    value=${!name-}
    if [ -z "$value" ]; then
        value=$(env_file_value "$name")
    fi
    if [ -z "$value" ]; then
        value=$default
    fi
    printf '%s' "$value"
}

for tool in curl jq; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is not installed"
done

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    printf 'usage: %s <email>\n' "$(basename -- "$0")" >&2
    exit 1
fi
email=$1

KEYCLOAK_URL=$(setting KEYCLOAK_URL https://id.filenkov.store)
KEYCLOAK_URL=${KEYCLOAK_URL%/}
REALM=$(setting REALM filenkov)
IDP_ADMIN_CLIENT_ID=$(setting IDP_ADMIN_CLIENT_ID gateway-admin)
IDP_ADMIN_SECRET=$(setting IDP_ADMIN_SECRET)

[ -n "$IDP_ADMIN_SECRET" ] ||
    die "IDP_ADMIN_SECRET is empty: set it in the environment or in $ENV_FILE"
[ -n "$KEYCLOAK_URL" ] || die "KEYCLOAK_URL is empty"
[ -n "$REALM" ] || die "REALM is empty"

response=$work/response.json
bearer_conf=$work/bearer.conf
curl_err=$work/curl.err

# --- service token ---------------------------------------------------------

{
    printf 'grant_type=client_credentials&client_id='
    printf '%s' "$IDP_ADMIN_CLIENT_ID" | urlencode
    printf '&client_secret='
    printf '%s' "$IDP_ADMIN_SECRET" | urlencode
} > "$work/token-request"

http=$(
    curl --silent --show-error --request POST \
        --url "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
        --header 'Content-Type: application/x-www-form-urlencoded' \
        --data-binary "@$work/token-request" \
        --output "$response" --write-out '%{http_code}' --max-time "$HTTP_TIMEOUT" \
        2> "$curl_err"
) || http=000
rm -f -- "$work/token-request"

error_detail() {
    jq -r 'if type == "object"
           then (.error // .errorMessage // .error_description // "no error field")
           else "unexpected body" end' "$response" 2>/dev/null || printf 'unparsable body'
}

if [ "$http" != "200" ]; then
    detail=$(error_detail)
    reason=''
    if [ -s "$curl_err" ]; then
        reason=" $(tail -n 1 "$curl_err")"
    fi
    die "token request failed: HTTP ${http} to ${KEYCLOAK_URL} as ${IDP_ADMIN_CLIENT_ID} (${detail})${reason}"
fi

ACCESS_TOKEN=$(jq -er '.access_token' "$response" 2>/dev/null) ||
    die "the idp answered 200 without an access_token"

printf 'header = "Authorization: Bearer %s"\n' "$ACCESS_TOKEN" > "$bearer_conf"

# --- Admin API -------------------------------------------------------------

# admin_request <method> <path> [body-file] [content-type]
admin_request() {
    local method=$1 path=$2 body=${3-} ctype=${4-} code
    local -a args=(
        --silent --show-error
        --config "$bearer_conf"
        --request "$method"
        --url "${KEYCLOAK_URL}${path}"
        --output "$response"
        --write-out '%{http_code}'
        --max-time "$HTTP_TIMEOUT"
    )
    if [ -n "$ctype" ]; then
        args+=(--header "Content-Type: ${ctype}")
    fi
    if [ -n "$body" ]; then
        args+=(--data-binary "@${body}")
    fi
    code=$(curl "${args[@]}" 2> "$curl_err") || code=000
    printf '%s' "${code:-000}"
}

# --- find the user ---------------------------------------------------------

lookup_path="/admin/realms/${REALM}/users?exact=true&email=$(printf '%s' "$email" | urlencode)"
http=$(admin_request GET "$lookup_path")
case "$http" in
    200) ;;
    401 | 403)
        die "the admin client was refused (HTTP ${http}): check the roles view-users, query-users and manage-users on ${IDP_ADMIN_CLIENT_ID}"
        ;;
    *) die "user lookup failed: HTTP ${http} ($(error_detail))" ;;
esac

case "$(jq -r 'if type == "array" then length else -1 end' "$response" 2>/dev/null || printf '%s' -1)" in
    0)
        die_code 2 "no user with email ${email} in realm ${REALM}. The account is created by the first Google login: ask them to sign in first."
        ;;
    1) ;;
    -1) die "unexpected response for the user lookup ($(error_detail))" ;;
    *)
        die "more than one user matches ${email} in realm ${REALM}. Duplicate emails are forbidden: fix that in the console first."
        ;;
esac

user_id=$(jq -er '.[0].id' "$response" 2>/dev/null) ||
    die "the user lookup returned no id"

# --- find the role ---------------------------------------------------------

http=$(admin_request GET "/admin/realms/${REALM}/roles/${ROLE}")
if [ "$http" = "404" ]; then
    die "realm role ${ROLE} does not exist in realm ${REALM}: apply src/auth-gateway/idp/realm.json first"
fi
[ "$http" = "200" ] || die "role lookup failed: HTTP ${http} ($(error_detail))"
role_id=$(jq -er '.id' "$response" 2>/dev/null) || die "role ${ROLE} came back without an id"

# --- idempotency -----------------------------------------------------------

has_role() {
    jq -e --arg role "$ROLE" 'any(.[]?; .name == $role)' "$response" >/dev/null 2>&1
}

http=$(admin_request GET "/admin/realms/${REALM}/users/${user_id}/role-mappings/realm")
[ "$http" = "200" ] || die "role mapping lookup failed: HTTP ${http} ($(error_detail))"
if has_role; then
    printf 'grant-admin: %s (%s) already has realm role %s; nothing to do\n' "$email" "$user_id" "$ROLE"
    exit 0
fi

# --- grant -----------------------------------------------------------------

jq -cn --arg id "$role_id" --arg name "$ROLE" '[{id: $id, name: $name}]' > "$work/mapping.json"
http=$(admin_request POST "/admin/realms/${REALM}/users/${user_id}/role-mappings/realm" \
    "$work/mapping.json" 'application/json')
case "$http" in
    200 | 201 | 204) ;;
    *) die "granting the role failed: HTTP ${http} ($(error_detail))" ;;
esac

# Read it back: a 204 is not proof that Keycloak stored the mapping.
http=$(admin_request GET "/admin/realms/${REALM}/users/${user_id}/role-mappings/realm")
if [ "$http" = "200" ] && has_role; then
    printf 'grant-admin: granted realm role %s to %s (%s)\n' "$ROLE" "$email" "$user_id"
    exit 0
fi

die "the idp accepted the mapping but does not report role ${ROLE} on ${email}"
