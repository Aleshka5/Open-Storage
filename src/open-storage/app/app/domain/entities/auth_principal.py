from dataclasses import dataclass

from app.domain.value_objects.role import Role


@dataclass(frozen=True)
class AuthPrincipal:
    """Request identity from identity v1 headers.

    ``id`` is ``X-Auth-Subject`` as received. The reader does not parse it
    into a UUID. The local ``users.id`` column is still a UUID; the
    repository stores a subject only when that column can hold it.
    """

    id: str
    email: str
    name: str
    role: Role
    session_id: str = ""
