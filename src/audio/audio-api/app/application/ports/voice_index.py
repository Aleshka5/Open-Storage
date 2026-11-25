"""Voice index port (`VoiceIndex`) — the Qdrant `audio_voices` collection.

The only way to search and write voice points. The method signatures **have no**
variant without `owner_id`: search and writes without an owner filter are impossible by
construction (constitution §3, AGENTS.md "no Qdrant query without a filter"). A method able to
scan without an owner is simply not declared here — an attempt to call it in code yields
a type error, not a silent scan (US-06 acceptance criterion).

All vectors share one space (ADR-007): diarization centroids, note embedding.
The dimension is set by the model; a mismatch with the collection — `VOICE_INDEX_INCOMPATIBLE`.
"""

from __future__ import annotations

from typing import Protocol


class VoiceIndexError(Exception):
    """Base error of a voice index call."""


class VoiceIndexUnavailable(VoiceIndexError):
    """Qdrant is unavailable (network/5xx) — `503 VOICE_INDEX_UNAVAILABLE`."""


class VoiceIndexIncompatible(VoiceIndexError):
    """Collection dimension ≠ vector dimension — `503 VOICE_INDEX_INCOMPATIBLE`."""


class VoicePoint(Protocol):
    """A stored voice point returned by a search (used to build the suggestion list)."""

    @property
    def point_id(self) -> str: ...

    @property
    def score(self) -> float: ...


class VoiceIndex(Protocol):
    """Qdrant `audio_voices`: collection creation, filtered search, point writes."""

    async def ensure_collection(self, vector_size: int) -> None:
        """Creates the collection at startup if it does not exist; otherwise verifies the dimension.

        Raises `VoiceIndexIncompatible` if the dimension of the existing collection does not
        match `vector_size` (does not recreate and does not "fix" it — ADR-007).
        """

    async def search(
        self, owner_id: str, vector: list[float], *, limit: int
    ) -> list[VoicePoint]:
        """Searches the nearest points by centroid. The `owner_id` filter is mandatory.

        There is no variant without `owner_id`. There is no threshold: the nearest `limit`
        points of the owner are returned (ADR-007).
        """

    async def has_me(self, owner_id: str) -> bool:
        """True if the owner has a `kind=me` point (the "Me" voice exists)."""

    async def upsert_nick(
        self,
        owner_id: str,
        *,
        point_id: str,
        vector: list[float],
        payload: dict,
    ) -> None:
        """Writes a nick point (immutable — a repeat yields the same point_id)."""

    async def upsert_me(
        self,
        owner_id: str,
        *,
        point_id: str,
        vector: list[float],
        payload: dict,
    ) -> None:
        """Upsert of the "Me" point with a deterministic id (voice replacement, ADR-008)."""
