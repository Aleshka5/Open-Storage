"""GPU lease port (Redis `SET NX PX`), ADR-006.

Three classes: `stream > interactive > offline`. Transcription batches run `offline`: they
cannot preempt the stream and wait for the lease themselves. No lease — the job goes to
`.retry` without bumping `attempt` (a wait, not an error).
"""

from __future__ import annotations

from typing import Protocol


class LeaseDenied(Exception):
    """Lease not obtained. This is a wait, not a job error (attempt does not grow)."""


GpuClass = str  # "stream" | "interactive" | "offline"


class GpuLease(Protocol):
    def acquire(self, klass: GpuClass) -> None:
        """Takes the `gpu:lease` lease (SET NX PX). Raises LeaseDenied if busy."""

    @property
    def held(self) -> bool:
        """True while this process holds the lease."""

    def heartbeat(self) -> None:
        """Extends the TTL (PX). Called every 5 s during the computation."""

    def release(self) -> None:
        """Releases the lease early (after the step or on error)."""
