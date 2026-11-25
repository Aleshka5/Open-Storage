"""Transcription model port: an abstraction over Parakeet, testable without a GPU.

The production implementation loads `nvidia/parakeet-tdt-0.6b-v3` pinned to `ASR_REVISION`
(fp16 on CUDA). Tests substitute a synthetic model that returns a fixed
text per turn. The language (RU/EN) is detected by the model; the job's `language_hint` does
not override the detection.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.transcription import TranscriptionOutput


class AsrModel(Protocol):
    """A batch of turns → text. The model holds the language per batch, not per turn."""

    def load(self) -> None:
        """Loads the weights (fp16 on CUDA). Raises on hf_auth_failed / incompatibility."""

    @property
    def loaded(self) -> bool:
        """True when the weights are resident and ready for inference."""

    def transcribe_windows(
        self,
        windows: list[bytes],
        *,
        seqs: list[int],
        language_hint: str | None = None,
    ) -> TranscriptionOutput:
        """Transcribes PCM windows (16 kHz mono s16le), one per turn.

        `windows` and `seqs` are parallel: `seqs[i]` is the `seq` of the turn whose window
        is in `windows[i]`. Returns text per `seq` and the model language (per batch).

        The implementation must raise CUDA OOM errors as a regular exception (the message
        contains `out of memory`) so the handler can shrink the batch.
        """


class ModelLoadError(RuntimeError):
    """Failed to load the model; the service is not considered ready (no silent fallback)."""
