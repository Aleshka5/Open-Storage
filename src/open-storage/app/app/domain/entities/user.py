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

    ``object_prefix_id`` is the id embedded in object keys and the vault
    key salt. A cutover re-key changes ``id`` to the identity subject and
    leaves this value on the pre-cutover id. ``None`` means "same as ``id``".
    """

    id: UUID
    email: str
    role: Role
    is_active: bool
    created_at: datetime
    object_prefix_id: UUID | None = None

    @property
    def storage_id(self) -> UUID:
        if self.object_prefix_id is None:
            return self.id
        return self.object_prefix_id
