"""Voice embedding model port — one model for the vector space (ADR-007).

The note's voice embedding is computed with the **same** model that produces the centroids
during diarization (`speaker-diarization-community-1`): otherwise the vectors would live in
different bases and the "similarity" in suggestions would be false. The dimension is the Qdrant
collection contract (`CENTROID_DIM`); a mismatch is a `dim_mismatch` in the event, not a silent
write.

The port is separate from `DiarizerModel`: it has a different input (whole file → one vector),
and tests substitute a fake without a GPU.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingError(RuntimeError):
    """The model failed to compute the vector (corrupt decode, no audio) — `.dead`."""


class EmbeddingModel(Protocol):
    """One vector over the whole file (queue-audio-embedding/message.md, item 2)."""

    def load(self) -> None:
        """Loads the embedding weights. Raises if the weights are missing (no silent fallback)."""

    @property
    def loaded(self) -> bool:
        """True when the weights are resident."""

    @property
    def model_id(self) -> str:
        """Model identifier for `voice_embedding_model` (name + revision)."""

    def embed(self, wav_path: str) -> list[float]:
        """One normalized vector over the whole file (16 kHz mono WAV)."""
