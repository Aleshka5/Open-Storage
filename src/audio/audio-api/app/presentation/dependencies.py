"""The `get_current_owner` dependency — the only source of identity.

Reads the `X-Auth-Subject` header (a UUID from the gateway). Missing, empty, or any
value that is not an 8-4-4-4-12 UUID → 401 IDENTITY_MISSING. Upper-case hex is
accepted and returned lower-cased. Never takes the owner from the body, query or cookie.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Depends, Header

from app.domain.app_error import AppError
from app.domain.errors import ErrorCode

# Canonical subject: 8-4-4-4-12 hex. URN, braces, and hyphen-less forms are refused.
_SUBJECT_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def get_current_owner(
    x_auth_subject: Annotated[str | None, Header(alias="X-Auth-Subject")] = None,
) -> str:
    """Returns the owner from `X-Auth-Subject` or raises 401 IDENTITY_MISSING."""
    return owner_from_header_value(x_auth_subject)


def owner_from_header_value(value: str | None) -> str:
    """Validates the raw `X-Auth-Subject` header value (for WS Upgrade)."""
    if not value:
        raise AppError(ErrorCode.IDENTITY_MISSING, "Identity not passed by the gateway")
    if _SUBJECT_RE.fullmatch(value) is None:
        raise AppError(ErrorCode.IDENTITY_MISSING, "X-Auth-Subject is not a UUID")
    return value.lower()


OwnerId = Annotated[str, Depends(get_current_owner)]
