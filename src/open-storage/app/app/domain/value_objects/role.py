from enum import StrEnum

STORAGE_ROLE_BLOCKED = "svc:storage:blocked"
STORAGE_ROLE_ADMIN = "svc:storage:admin"
STORAGE_ROLE_FAMILY = "svc:storage:family"


class Role(StrEnum):
    STRANGER = "STRANGER"
    FAMILY = "FAMILY"
    ADMIN = "ADMIN"
    BLOCKED = "BLOCKED"


def role_from_auth_roles(header: str | None) -> Role:
    """Project ``X-Auth-Roles`` onto the four storage roles.

    Most restrictive wins: blocked, then admin, then family, else stranger.
    Tokens that are not a known ``svc:storage:*`` value are ignored.
    A missing or empty header is stranger.
    """
    tokens = [] if header is None else header.split()
    if STORAGE_ROLE_BLOCKED in tokens:
        return Role.BLOCKED
    if STORAGE_ROLE_ADMIN in tokens:
        return Role.ADMIN
    if STORAGE_ROLE_FAMILY in tokens:
        return Role.FAMILY
    return Role.STRANGER
