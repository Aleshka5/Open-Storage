"""The language pass over a batch: a window in the wrong script is retried wider, then dropped.

Parakeet decides the language per window; on a fraction of a second it answers "Bueno." in a
Russian conversation. The batch's own majority script is the reference: retry the odd ones
out with context, keep the first Cyrillic result, drop a window that never resolves.
"""

from __future__ import annotations

from app.application.transcribe_batch import (
    TranscribeBatchHandler,
    _dominant_script_is_cyrillic,
    _expanded,
)
from app.domain.transcription import TranscriptionOutput, Turn


class ScriptedModel:
    """Returns prepared texts per call, and records the window lengths it was asked about."""

    def __init__(self, script: list[dict[int, str]]) -> None:
        self._script = script
        self.calls: list[list[int]] = []
        self.byte_windows: list[tuple[int, int]] = []

    def transcribe_windows(self, windows, *, seqs, language_hint=None):
        self.calls.append(list(seqs))
        self.byte_windows.extend((len(w), s) for w, s in zip(windows, seqs, strict=True))
        texts = self._script[len(self.calls) - 1] if len(self.calls) <= len(self._script) else {}
        return TranscriptionOutput(texts=dict(texts), language=None)


class RecordingStore:
    """A store that hands out a window of `num_bytes` bytes and remembers the ranges asked."""

    def __init__(self) -> None:
        self.ranges: list[tuple[int, int]] = []

    def read_window(self, key, *, start_byte, num_bytes):
        self.ranges.append((start_byte, num_bytes))
        return b"\x00\x00" * (num_bytes // 2)


class Repo:
    def __init__(self) -> None:
        self.upserts: list = []

    def speaker_id_for(self, owner_id, recording_id, speaker_key):  # noqa: ARG002
        return f"spk-{speaker_key}"

    def upsert(self, owner_id, recording_id, phrase):  # noqa: ARG002
        self.upserts.append(phrase)


def handler(model, store, repo) -> TranscribeBatchHandler:
    return TranscribeBatchHandler(
        settings=type("S", (), {"scratch_dir": "/tmp", "gpu_lease_heartbeat_ms": 1000})(),
        model=model,
        store=store,
        repo=repo,
        queue=None,
        lease=None,
    )


def turn(seq: int, start: int, end: int, speaker: str = "juri") -> Turn:
    return Turn(turn_id=f"t{seq}", speaker_key=speaker, start_ms=start, end_ms=end, seq=seq)


BATCH = [
    turn(1, 0, 2500),
    turn(2, 2500, 5000),
    turn(3, 5000, 5400),
]


def test_majority_script_of_a_batch():
    assert _dominant_script_is_cyrillic({1: "Он ко мне едет.", 2: "Oh."}) is True
    assert _dominant_script_is_cyrillic({1: "He is coming.", 2: "Oh."}) is False


def test_window_expansion_is_padded_then_widened():
    assert _expanded(1000, 1500, 600, 0) == (400, 2100)
    # Centred widening to 2.5 s, never below zero.
    start, end = _expanded(1200, 1500, 0, 2500)
    assert end - start == 2500
    assert _expanded(10, 110, 0, 2500)[0] == 0


def test_a_latin_window_in_a_russian_batch_is_retried_and_replaced():
    model = ScriptedModel([
        {1: "Он ко мне едет.", 2: "Bueno.", 3: "Сейчас приеду."},
        {2: "Он ко мне не едет."},  # the padded retry resolves it
    ])
    store, repo = RecordingStore(), Repo()
    handler(model, store, repo)._transcribe_batch(BATCH, "rec", "owner", "job", "key")

    assert model.calls[1] == [2]  # only the mismatched window is re-read
    assert [p.seq for p in repo.upserts] == [1, 2, 3]
    assert repo.upserts[1].text == "Он ко мне не едет."
    # The retry reads a wider byte range than the original turn (0.4 s → 1.6 s of audio).
    assert store.ranges[3][1] > store.ranges[1][1]


def test_a_window_that_never_resolves_writes_no_phrase():
    model = ScriptedModel([
        {1: "Он ко мне едет.", 2: "Bueno.", 3: "Сейчас приеду."},
        {2: "Bueno."},  # padded retry: still foreign
        {2: "Bueno."},  # 2.5 s retry: still foreign
    ])
    store, repo = RecordingStore(), Repo()
    handler(model, store, repo)._transcribe_batch(BATCH, "rec", "owner", "job", "key")

    assert [p.seq for p in repo.upserts] == [1, 3]
    assert all(p.text for p in repo.upserts)


def test_an_english_batch_is_never_retried():
    model = ScriptedModel([{1: "He is coming.", 2: "Oh.", 3: "Right."}])
    store, repo = RecordingStore(), Repo()
    handler(model, store, repo)._transcribe_batch(BATCH, "rec", "owner", "job", "key")

    assert len(model.calls) == 1
    assert len(repo.upserts) == 3


def test_empty_text_writes_no_phrase():
    model = ScriptedModel([{1: "Он ко мне едет.", 2: "", 3: "Сейчас приеду."}])
    store, repo = RecordingStore(), Repo()
    handler(model, store, repo)._transcribe_batch(BATCH, "rec", "owner", "job", "key")

    assert [p.seq for p in repo.upserts] == [1, 3]
