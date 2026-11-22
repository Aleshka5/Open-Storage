from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.value_objects.role import Role


@dataclass(frozen=True)
class User:
    """Local projection plus the storage role for this request.

    ``role`` is never loaded from the database. It is the projection of
    ``X-Auth-Roles`` for the current request. A row read from ``users``
    carries ``STRANGER`` because the table has no role column.
    """

    id: UUID
    email: str
    role: Role
    is_active: bool
    created_at: datetime
