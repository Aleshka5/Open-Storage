"""Stream tests (US-05): StreamSession (windows/revision/end_ms) and StreamHandler.

No GPU: the model is `StreamFakeModel`, the repository is `StreamFakeRepo`, the lease is
`FakeGpuLease`. Coverage: text growing with revision, monotonic end_ms, open-frame
validation (4404/not_me), one session per slot (4503), persistence to Mongo after done.
"""

from __future__ import annotations

import asyncio

import pytest

from app.application.stream_handler import (
    CLOSE_GPU_BUSY,
    CLOSE_IDLE_TIMEOUT,
    CLOSE_NOT_FOUND,
    MAX_PENDING_FRAMES,
    InvalidOpen,
    StreamHandler,
)
from app.application.stream_session import (
    BYTES_PER_SEC,
    CHUNK_S,
    MAX_BUFFER_BYTES,
    StreamSession,
)
from tests.fakes import FakeGpuLease, StreamFakeModel, StreamFakeRepo


def _handler(model=None, repo=None, lease=None, settings=None):
    from app.config import Settings

    settings = settings or Settings()
    return StreamHandler(
        settings=settings,
        model=model or StreamFakeModel(),
        repo=repo or StreamFakeRepo(),
        lease=lease or FakeGpuLease(),
    )


def _open(**kw):
    msg = {
        "type": "open",
        "recording_id": "rec-1",
        "phrase_id": "phr-1",
        "owner_user_id": "owner-1",
        "format": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
    }
    msg.update(kw)
    return msg


# -- StreamSession (pure window logic) --------------------------------------


def test_session_grows_revision_and_end_ms():
    model = StreamFakeModel(["a", "ab", "abc"])
    s = StreamSession(model)
    # 2 s PCM = 64000 bytes.
    s.feed(b"\x00" * (2 * BYTES_PER_SEC))
    assert s.should_emit_partial() is True
    text, end_ms, rev = s.transcribe()
    assert rev == 1
    assert end_ms == 2000  # 64000 bytes / 32 bytes-per-ms
    assert text == "a"

    s.feed(b"\x01" * (2 * BYTES_PER_SEC))
    text, end_ms, rev = s.transcribe()
    assert rev == 2
    assert end_ms == 4000
    assert text == "ab"  # the text is replaced as a whole

    text, end_ms, rev, lang = s.finalize()
    assert rev == 3
    assert lang == "ru"
    # Look-ahead is closed by the final: audio_ms covers everything recorded.
    assert end_ms == 4000


def test_session_partial_only_after_2s():
    model = StreamFakeModel()
    s = StreamSession(model)
    s.feed(b"\x00" * (BYTES_PER_SEC))  # 1 s — less than a chunk
    assert s.should_emit_partial() is False


# -- StreamHandler: open-frame validation -----------------------------------


def test_open_not_right_phrase_is_4404():
    h = _handler(repo=StreamFakeRepo(phrase_side="left"))
    with pytest.raises(InvalidOpen) as ei:
        h.validate_open(_open())
    assert ei.value.close_code == CLOSE_NOT_FOUND


def test_open_not_me_speaker_is_4404():
    h = _handler(repo=StreamFakeRepo(speaker_is_me=False))
    with pytest.raises(InvalidOpen) as ei:
        h.validate_open(_open())
    assert ei.value.close_code == CLOSE_NOT_FOUND


def test_open_missing_recording_is_4404():
    h = _handler(repo=StreamFakeRepo(recording_exists=False))
    with pytest.raises(InvalidOpen) as ei:
        h.validate_open(_open())
    assert ei.value.close_code == CLOSE_NOT_FOUND


def test_open_malformed_is_4400():
    h = _handler()
    with pytest.raises(InvalidOpen) as ei:
        h.validate_open({"type": "not-open"})
    assert ei.value.close_code == 4400


def test_second_session_is_4503():
    lease = FakeGpuLease()
    h = _handler(lease=lease)
    h.acquire_slot()
    assert h.active is True
    with pytest.raises(InvalidOpen) as ei:
        h.acquire_slot()
    assert ei.value.close_code == CLOSE_GPU_BUSY


# -- StreamHandler: full cycle ----------------------------------------------


async def _drain_stream(h, recording_id, phrase_id, owner_id, frames):
    sent = []

    async def _send(d):
        sent.append(d)

    async def _iter():
        for f in frames:
            yield f

    await h.loop(recording_id, phrase_id, owner_id, receive_stream=_iter(), send_json=_send)
    return sent


async def test_loop_emits_partial_final_done_and_persists():
    repo = StreamFakeRepo()
    model = StreamFakeModel(["hello", "hello world"])
    h = _handler(model=model, repo=repo)
    h.acquire_slot()

    # 4 s PCM → 2 partials, then stop.
    frames = [b"\x00" * (2 * BYTES_PER_SEC), b"\x00" * (2 * BYTES_PER_SEC), '{"type":"stop"}']
    sent = await _drain_stream(h, "rec-1", "phr-1", "owner-1", frames)

    types = [m["type"] for m in sent]
    assert "partial" in types
    assert "final" in types
    assert types[-1] == "done"
    # the final text is full (not an increment), the revision is monotonic.
    final = [m for m in sent if m["type"] == "final"][0]
    assert final["text"] == "hello world"
    assert final["language"] == "ru"
    # Each partial is written while recording (S-03): the chat polls `phrases`
    # and would otherwise stay empty until stop.
    partials = [u for u in repo.updated if u["state"] == "partial"]
    assert [u["text"] for u in partials] == ["hello", "hello world"]
    assert [u["revision"] for u in partials] == [1, 2]
    assert repo.updated[-1]["state"] == "final"
    assert repo.updated[-1]["text"] == "hello world"
    assert repo.updated[-1]["revision"] == 3
    assert not h.active  # the slot is released after done


async def test_loop_drops_session_on_break():
    repo = StreamFakeRepo()
    h = _handler(repo=repo)
    h.acquire_slot()
    # Empty input (drop) → finalize right away, the slot is released.
    sent = await _drain_stream(h, "rec-1", "phr-1", "owner-1", [])
    assert any(m["type"] == "final" for m in sent)
    assert any(m["type"] == "done" for m in sent)
    assert not h.active


# -- D2: bounded sliding window (60 s of synthetic audio) -------------------


class _RecordingModel:
    """Model fake: remembers the window size, the text grows with the calls."""

    def __init__(self) -> None:
        self.windows: list[int] = []

    def transcribe_pcm(self, pcm: bytes):
        self.windows.append(len(pcm))
        return f"t{len(self.windows)}", "ru"


def test_session_60s_buffer_bounded_revision_and_consumed_end_ms():
    """60 s PCM: buffer O(window), end_ms monotonic = consumed, revision grows (D2)."""
    model = _RecordingModel()
    s = StreamSession(model)
    frame = b"\x00" * 3200  # 100 ms = 32000 bytes/s × 0.1 s
    frame_ms = 100
    total_frames = 600  # 60 s

    end_ms_history: list[int] = []
    revisions: list[int] = []
    received_ms = 0
    max_buffer = 0

    for _ in range(total_frames):
        s.feed(frame)
        received_ms += frame_ms
        # Memory invariant: the buffer is ≤ window + one frame of slack, not the whole recording.
        assert s.buffered_bytes <= s.buffer_limit_bytes
        max_buffer = max(max_buffer, s.buffered_bytes)
        if s.should_emit_partial():
            _, end_ms, rev = s.transcribe()
            end_ms_history.append(end_ms)
            revisions.append(rev)

    text, end_ms, rev, lang = s.finalize()
    end_ms_history.append(end_ms)
    revisions.append(rev)

    # (a) the buffer does not grow with the recording: it holds only left+right context.
    assert s.buffered_bytes == 0  # the final released the buffer
    assert max_buffer <= s.buffer_limit_bytes
    # ~14 s window (+ a frame of slack), not 60 s of recording.
    assert max_buffer <= s.buffer_limit_bytes
    # The ceiling is a window constant, not a function of the recording length.
    assert s.buffer_limit_bytes < 25 * BYTES_PER_SEC  # < 25 s of audio for a 60 s recording
    # (b) end_ms is monotonic and equals the consumed audio (never more than received).
    assert end_ms_history == sorted(end_ms_history)
    assert end_ms_history[-1] == received_ms  # 60000
    for v in end_ms_history:
        assert 0 <= v <= received_ms
    assert end_ms == 60000
    assert lang == "ru"
    # (c) revision strictly grows: a partial every ~2 s + the final.
    assert revisions == list(range(1, len(revisions) + 1))
    assert len(revisions) >= total_frames * frame_ms // (CHUNK_S * 1000)
    # The model window stays within 10 s left + 2 s chunk + 2 s right.
    assert max(model.windows) <= MAX_BUFFER_BYTES
    assert text


# -- D4: idle 4408 + frame overflow 4400 ------------------------------------


async def test_idle_timeout_closes_4408():
    """No frames for idle_timeout_s → 4408; the phrase is finalized anyway (D4)."""
    repo = StreamFakeRepo()
    h = _handler(repo=repo)
    h._idle_timeout_s = 0.05  # type: ignore[attr-defined] — inject a short timeout
    h.acquire_slot()

    async def _stall():
        await asyncio.sleep(1.0)
        yield b"\x00" * 1600  # pragma: no cover — already timed out

    sent = []

    async def _send(d):
        sent.append(d)

    await h.loop("rec-1", "phr-1", "owner-1", receive_stream=_stall(), send_json=_send)

    assert h.close_code == CLOSE_IDLE_TIMEOUT
    types = [m["type"] for m in sent]
    assert "final" in types and types[-1] == "done"
    assert repo.updated and repo.updated[-1]["state"] == "final"
    assert not h.active


async def test_idle_timeout_default_is_contract_30s():
    """The idle-timeout default is 30 s (asr-worker/api.md), not an injection (D4)."""
    from app.application.stream_handler import IDLE_TIMEOUT_S

    assert IDLE_TIMEOUT_S == 30
    assert _handler()._idle_timeout_s == 30.0  # noqa: SLF001


async def test_frame_flood_over_cap_closes_4400():
    """More than 128 unprocessed frames → 4400 (asr-worker/api.md) (D4)."""
    h = _handler()
    h._max_pending_frames = 3  # type: ignore[attr-defined] — a short ceiling
    h.acquire_slot()

    async def _flood():
        for _ in range(1000):
            yield b"\x00" * 1600

    sent = []

    async def _send(d):
        sent.append(d)

    await h.loop("rec-1", "phr-1", "owner-1", receive_stream=_flood(), send_json=_send)

    assert h.close_code == 4400
    assert not h.active
    # The text produced so far is saved (final before the close).
    assert sent[-1]["type"] == "done"


async def test_pending_frames_under_cap_pass():
    """A stream within the frame ceiling is processed fully (no false 4400). (D4)."""
    h = _handler()
    h._max_pending_frames = MAX_PENDING_FRAMES
    h.acquire_slot()

    async def _few():
        for _ in range(20):
            yield b"\x00" * 1600
        yield '{"type":"stop"}'

    sent = []

    async def _send(d):
        sent.append(d)

    await h.loop("rec-1", "phr-1", "owner-1", receive_stream=_few(), send_json=_send)
    assert h.close_code == 1000
    assert sent[-1]["type"] == "done"
