"""Diarization model port: an abstraction over Pyannote, testable without a GPU.

The production implementation loads `pyannote/speaker-diarization-community-1` pinned to
`DIARIZATION_REVISION` (fp16 on CUDA). Tests substitute a synthetic model that
splits fixtures into known speakers.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.diarization import DiarizationResult


class DiarizerModel(Protocol):
    """One cluster per file, no `num_speakers` (ADR-002)."""

    def load(self) -> None:
        """Loads the weights (fp16 on CUDA). Raises on hf_auth_failed / incompatibility."""

    @property
    def loaded(self) -> bool:
        """True when the weights are resident and ready for inference."""

    def diarize(self, wav_path: str) -> DiarizationResult:
        """Annotation of one file: exclusive-track turns + centroid per speaker."""


class ModelLoadError(RuntimeError):
    """Failed to load the model; the service is not considered ready (no silent fallback)."""
