"""Streaming recognition session (US-05): 10s-left + 2s-chunk + 2s-right buffer.

Pure logic without GPU/Mongo/WS — tested with synthetic data. The model port
(`StreamModel`) transcribes a PCM window; the session owns the windows, `partial`
every ~2 s, `final` on `stop`, monotonic `revision`/`end_ms` (ADR-003).

Sizes (asr-worker/api.md): `partial` every 2 s, window 10 s left + 2 s chunk + 2 s
right. Memory is O(window), not O(recording): after every step the consumed part is cut
out of the buffer (see `_trim_consumed`). `end_ms` is derived from the **consumed** bytes
(`consumed_bytes`), not from the buffer length, and only grows.
"""

from __future__ import annotations

from typing import Protocol

# PCM s16le 16 kHz mono: 32000 bytes/s.
BYTES_PER_SEC = 32000

# Recognition window (asr-worker/api.md).
LEFT_S = 10
CHUNK_S = 2
RIGHT_S = 2
PARTIAL_INTERVAL_S = 2

# Model window: left + chunk + right. Anything longer — the model does not need it.
MAX_BUFFER_BYTES = (LEFT_S + CHUNK_S + RIGHT_S) * BYTES_PER_SEC
# Slack for frames arriving between steps: 4 × 64 KB (max client frame, asr-worker/api.md).
FRAME_SLACK_BYTES = 4 * 64 * 1024
# After a step exactly the model window stays in the buffer.
TRIM_KEEP_BYTES = MAX_BUFFER_BYTES
# Size trigger — only when the buffer exceeds the window by one chunk: otherwise the
# buffer sticks to the threshold and a step fires on every frame instead of every 2 s.
TRIM_TRIGGER_BYTES = MAX_BUFFER_BYTES + CHUNK_S * BYTES_PER_SEC


def _ms(n_bytes: int) -> int:
    return n_bytes * 1000 // BYTES_PER_SEC


class StreamModel(Protocol):
    """Transcribes a PCM window into text (the implementation is Parakeet on GPU)."""

    def transcribe_pcm(self, pcm: bytes) -> tuple[str, str | None]:
        """Returns (text, language) for the given window. The text is full, not an increment."""


class StreamSession:
    """Sliding PCM window and `partial`/`final` output with monotonic revision/end_ms."""

    def __init__(self, model: StreamModel) -> None:
        self._model = model
        # Sliding window: the tail of the received audio the model window is cut from.
        self._buf = bytearray()
        self._revision = 0
        self._last_text = ""
        self._last_end_ms = 0
        self._last_language: str | None = None
        self._since_last_partial_bytes = 0
        # Consumed (chunk-closed) bytes — the source of end_ms.
        self.consumed_bytes = 0
        # Dropped from the left of the buffer (trim) — the memory invariant tests check.
        self.trimmed_bytes = 0
        # Total PCM bytes received (independent of trimming): the source of received_ms.
        self.received_bytes = 0
        self.model_calls = 0

    # -- counters -------------------------------------------------------------

    @property
    def buffered_bytes(self) -> int:
        return len(self._buf)

    @property
    def buffer_limit_bytes(self) -> int:
        """Buffer ceiling: the trigger threshold plus slack for frames arriving between steps."""
        return TRIM_TRIGGER_BYTES + FRAME_SLACK_BYTES

    @property
    def end_ms(self) -> int:
        """Duration of the consumed audio (never more than received), monotonic."""
        return _ms(self.consumed_bytes)

    @property
    def received_ms(self) -> int:
        """Total audio received (everything that came through `feed`, including dropped data)."""
        return _ms(self.received_bytes)

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def text(self) -> str:
        return self._last_text

    @property
    def language(self) -> str | None:
        return self._last_language

    # -- input ----------------------------------------------------------------

    def feed(self, data: bytes) -> None:
        self.received_bytes += len(data)
        self._buf.extend(data)
        self._since_last_partial_bytes += len(data)

    def should_emit_partial(self) -> bool:
        """True when ≥ 2 s of new audio accumulated since the last step or the window is full."""
        if len(self._buf) == 0:
            return False
        return (
            self._since_last_partial_bytes >= CHUNK_S * BYTES_PER_SEC
            # The buffer reached the window size: it cannot grow further (memory is
            # O(window)): the step fires at the threshold (see _trim_consumed).
            or len(self._buf) >= TRIM_TRIGGER_BYTES
        )

    # -- output ---------------------------------------------------------------

    def _drop_left(self, keep_bytes: int) -> None:
        """Keeps the last `keep_bytes` of the buffer; the dropped part counts in trimmed_bytes."""
        if len(self._buf) > keep_bytes:
            excess = len(self._buf) - keep_bytes
            # Positive stop: `del buf[0:-N]` on a short buffer would be a silently empty slice.
            del self._buf[:excess]
            self.trimmed_bytes += excess

    def transcribe(self) -> tuple[str, int, int]:
        """Runs the model over the window and advances `end_ms`: (text, end_ms, revision).

        The next chunk of audio becomes consumed, but never more than received:
        `end_ms` is the time of the last received sample at the moment of the step (monotonic).
        After the step the old prefix is cut off: memory is O(window), not O(recording).
        """
        # `len(...)`, not `if not self._buf`: StreamSession has its own `__bool__`/`__len__`,
        # and `not self` would mean "the buffer is full".
        if len(self._buf) == 0:
            return self._last_text, self.end_ms, self._revision
        # Already received (including what trimming dropped) — the end_ms ceiling.
        self.consumed_bytes = min(
            self.consumed_bytes + CHUNK_S * BYTES_PER_SEC, self.received_bytes
        )
        # Trim BEFORE the model: the window is taken from the already trimmed buffer.
        self._trim_consumed()
        window = bytes(self._buf)
        text, lang = self._model.transcribe_pcm(window)
        self.model_calls += 1
        if text.strip():
            self._last_text = text.strip()
        if lang:
            self._last_language = lang
        self._revision += 1
        self._since_last_partial_bytes = 0
        self._last_end_ms = self.end_ms
        return self._last_text, self._last_end_ms, self._revision

    def _trim_consumed(self) -> None:
        """Drops everything older than the model window (left+chunk+right).

        Keeps exactly the window, which is BELOW the size trigger
        (`TRIM_TRIGGER_BYTES`); otherwise the buffer sticks to the threshold and `partial`
        fires on every frame instead of every 2 s (`CHUNK_S`).
        """
        self._drop_left(TRIM_KEEP_BYTES)

    def finalize(self) -> tuple[str, int, int, str | None]:
        """Last run over the remainder and `final`: (text, end_ms, revision, language).

        `final` always gets its own, higher `revision`, even if the previous step already
        caught up with the received audio: the client tells "the last partial" and "final" apart
        by revision (ADR-003), so the final pass never degenerates into a no-op. The model
        sees the tail (≤ window), `end_ms` covers everything received; the buffer is released.
        """
        window = bytes(self._buf[-TRIM_KEEP_BYTES:])
        if window:
            text, lang = self._model.transcribe_pcm(window)
            self.model_calls += 1
            if text.strip():
                self._last_text = text.strip()
            if lang:
                self._last_language = lang
        # The final covers everything received, including the look-ahead already read:
        # audio_ms at the final = the length of the recorded audio.
        if self.received_bytes > self.consumed_bytes:
            self.consumed_bytes = self.received_bytes
        self._revision += 1
        self._since_last_partial_bytes = 0
        self._buf.clear()
        self._last_end_ms = max(self._last_end_ms, self.end_ms)
        return self._last_text, self._last_end_ms, self._revision, self._last_language
