"""Identity from the identity v1 contract.

File Collector and Chat read the user only from ``X-Auth-Subject``, and the
role family only from ``X-Auth-Roles``. Cookies and ``Authorization`` do not
select a user. ``svc:rag:blocked`` in ``X-Auth-Roles`` is ``403 forbidden``
when the subject is a UUID. A missing or non-UUID ``X-Auth-Subject`` is
``401 unauthenticated``. No header from the pre-v1 identity is read.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from re import compile
from typing import Any

from rag_common.errors import ErrorCode, http_error

AUTH_USER_HEADER = "X-Auth-Subject"
AUTH_ROLES_HEADER = "X-Auth-Roles"
BLOCKED_ROLE = "svc:rag:blocked"

_UUID_TEXT = compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class AuthOk:
    user_id: str


@dataclass(frozen=True)
class AuthError:
    status: int
    body: dict[str, Any]


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            text = value.strip()
            return text or None
    return None


def canonical_uuid(value: str) -> str | None:
    """Return lowercase ``8-4-4-4-12`` or ``None`` when ``value`` is not a UUID."""
    if not _UUID_TEXT.fullmatch(value):
        return None
    return value.lower()


def _role_tokens(value: str | None) -> set[str]:
    """Split a space-separated realm-role list into exact tokens."""
    if value is None:
        return set()
    return {token for token in value.split() if token}


def authenticate(headers: Mapping[str, str]) -> AuthOk | AuthError:
    """Resolve the RAG user from identity v1 headers.

    Email and name headers are not read. The UUID version is not checked: the
    edge delivers the stored ``user_id``. The role test matches a whole token
    in ``X-Auth-Roles``, never a substring of it.
    """
    user_raw = _header(headers, AUTH_USER_HEADER)
    user_id = canonical_uuid(user_raw) if user_raw is not None else None
    if user_id is None:
        status, body = http_error(ErrorCode.UNAUTHENTICATED)
        return AuthError(status, body)
    if BLOCKED_ROLE in _role_tokens(_header(headers, AUTH_ROLES_HEADER)):
        status, body = http_error(ErrorCode.FORBIDDEN)
        return AuthError(status, body)
    return AuthOk(user_id)
