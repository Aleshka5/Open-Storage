"""Domain of voices and nicks: deterministic Qdrant point ids, the name key, payload.

The domain knows the owner_user_id field and the nick/"Me" rules, but not Qdrant as such
(the `VoiceIndex` port lives in application/ports). The vector dimension is a contract constant:
it is set by the diarization embedding model (`CENTROID_DIM` in diarizer), not by the calling code.

Defined:
- `name_key(name)` — nick name normalization: `strip` + `casefold` (data-model.md §nicks).
- `nick_point_id(owner_id, nick_id)` / `me_point_id(owner_id)` — `uuid5` with a fixed
  namespace (ADR-008), idempotent writes and isolation between owners.
- `EPOCH_OFFSET` — a warm namespace, shared by both points, so that the same
  `(nick_id)` for two different owners yields different points (the owner is part of the namespace).
- `EMBEDDING_READY` — a marker that the note's voice vector is (`processing.embedding`),
  under which "Make it my voice" is available.
- `ME_LABEL` — the owner's label in suggestions: always `Me`.
"""

from __future__ import annotations

import uuid

# "Me" key and the nick point prefix (ADR-008, external_contracts/qdrant/collection.md).
ME_KEY = "me"
NICK_PREFIX = "nick:"


def name_key(name: str) -> str:
    """Normalized nick name key: `strip` + `casefold`.

    Name uniqueness is defined by `name_key` within an owner (the index
    `{owner_user_id, name_key}` unique). `"Anya "` and `"anya"` are one nick.
    """
    return name.strip().casefold()


def me_point_id(owner_id: str) -> str:
    """Deterministic id of the "Me" point: `uuid5(uuid.UUID(owner_id), "me")` (ADR-008).

    owner_id is a valid UUID ("X-Auth-Subject"), used as the namespace directly.
    The id does not depend on recording or speaker: replacing the voice is one "upsert" by the same
    id, and two owners get two different points.
    """
    return str(uuid.uuid5(uuid.UUID(owner_id), ME_KEY))


def nick_point_id(owner_id: str, nick_id: str) -> str:
    """Deterministic id of a nick point: `uuid5(uuid.UUID(owner_id), "nick:"+nick_id)`."""
    return str(uuid.uuid5(uuid.UUID(owner_id), NICK_PREFIX + nick_id))


# Note menu item: "Make it my voice" is available once the vector is ready.
# The value is not written as a string into Qdrant payload: it is the `processing.embedding` state.
EMBEDDING_READY = "ready"

# The "Me" item in suggestions comes from a `kind=me` point, not from a search (ADR-007).
ME_LABEL = "Me"
