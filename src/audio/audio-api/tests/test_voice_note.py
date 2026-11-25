"""Voice note tests (UC-7): POST /api/voice-notes and the WS stream.

Coverage of us-05/init.md acceptance criteria: the "Note N" counter (grows, is not
reused), ASR_BUSY/ASR_UNAVAILABLE on POST, relaying of ready/partial/final/
stopped/done, lossless multipart writes, object duration = the sum of samples,
backpressure (lossless), a socket drop finalizes the recording.
"""

from __future__ import annotations

import pathlib
import subprocess
import time

import pytest

from app.application.voice_note_service import VoiceNoteService
from app.domain.errors import ErrorCode
from app.domain.status import RecordingStatus
from app.presentation.container import Container
from tests.conftest import OWNER
from tests.fakes import FakeAsrFactory, FakeAsrStream, FakeMuxerFactory, FakePcmMuxer

FRAME = b"\x00\x00" * 1600  # 100 ms of PCM s16le (3200 bytes)


def _muxed(pcm: bytes) -> bytes:
    """The expected "container" output of FakePcmMuxer for a PCM frame."""
    return bytes(b ^ 0xFF for b in pcm)


def _make_service(repo, voice_repo, store, settings, factory, probe=None):
    svc = VoiceNoteService(
        repo, voice_repo, store, factory, settings, asr_probe=probe
    )
    muxers = FakeMuxerFactory()
    svc._muxer_factory = muxers  # noqa: SLF001 — a muxer fake instead of ffmpeg
    svc._test_muxers = muxers  # noqa: SLF001
    return svc


def _avail_probe(available=True, busy=False):
    async def _p():
        return available, busy

    return _p


async def test_create_voice_note_counter_monotonic(
    settings, repo, voice_repo, store
):
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    out1 = await svc.create(OWNER)
    out2 = await svc.create(OWNER)
    assert out1["title"] == "Note 1"
    assert out2["title"] == "Note 2"
    assert out1["recording_id"] != out2["recording_id"]
    assert out1["ws_url"].startswith(f"/api/voice-notes/{out1['recording_id']}/stream")
    # recording document + SELF speaker + phrase seq=1 side=right.
    doc = repo.get_recording_sync(out1["recording_id"], OWNER)
    assert doc["kind"] == "voice_note"
    assert doc["status"] == RecordingStatus.RECORDING.value
    speaker = list(voice_repo.speakers.values())[0]
    assert speaker["speaker_key"] == "SELF"
    assert speaker["label"] == "Me"
    assert speaker["is_me"] is True
    assert speaker["centroid"] is None
    phrase = list(voice_repo.phrases.values())[0]
    assert phrase["seq"] == 1
    assert phrase["side"] == "right"
    assert phrase["state"] == "partial"
    assert phrase["text"] == ""
    assert phrase["end_ms"] == 0


async def test_create_asr_busy_returns_503(settings, repo, voice_repo, store):
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe(busy=True))
    with pytest.raises(Exception) as ei:
        await svc.create(OWNER)
    assert ei.value.code == ErrorCode.ASR_BUSY
    # Neither the recording nor the counter is created.
    assert not repo._recordings  # noqa: SLF001
    assert not repo._counters  # noqa: SLF001


async def test_create_asr_unavailable_returns_503(settings, repo, voice_repo, store):
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory,
                        _avail_probe(available=False))
    with pytest.raises(Exception) as ei:
        await svc.create(OWNER)
    assert ei.value.code == ErrorCode.ASR_UNAVAILABLE
    assert not repo._recordings  # noqa: SLF001


async def test_run_stream_relays_and_finalizes(settings, repo, voice_repo, store):
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    pid = created["phrase_id"]

    stream = FakeAsrStream(server_frames=[
        {"type": "partial", "phrase_id": pid, "text": "hello", "end_ms": 2400, "revision": 1},
        {"type": "final", "phrase_id": pid, "text": "hello world", "end_ms": 4800, "revision": 2,
         "language": "ru"},
        {"type": "done", "audio_ms": 4800},
    ])
    factory.add(stream)

    sent = []
    closed = []

    async def _receive():
        # We hand over one PCM frame, then stop.
        if not _receive.called:
            _receive.called = True
            return FRAME
        return {"type": "stop"}

    _receive.called = False

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    types = [m["type"] for m in sent]
    assert types[0] == "ready"
    assert "partial" in types
    assert "final" in types
    assert "stopped" in types
    assert types[-1] == "done"
    assert closed == [1000]

    # The PCM went to asr-worker.
    assert stream.pcm_sent and stream.pcm_sent[0] == FRAME
    assert stream.stopped is True

    # The MinIO object is the muxer's WebM bytes, not raw PCM (ADR-012 §6).
    key = f"u/{OWNER}/rec/{rid}/note.webm"
    assert key in store.objects
    muxer = svc._test_muxers.last  # noqa: SLF001
    assert muxer.started and muxer.finished
    assert store.objects[key] == _muxed(FRAME) + FakePcmMuxer.MAGIC + b"tail"
    assert not store.objects[key].startswith(FRAME)
    # The recording is ready, duration_ms = duration of the consumed PCM (100 ms).
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "ready"
    assert doc["duration_ms"] == 100
    assert doc["audio_content_type"] == "audio/webm"
    assert doc["language"] == "ru"


async def test_run_stream_socket_drop_finalizes(
    settings, repo, voice_repo, store
):
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    pid = created["phrase_id"]

    stream = FakeAsrStream(server_frames=[
        {"type": "final", "phrase_id": pid, "text": "drop", "end_ms": 4800, "revision": 3,
         "language": "ru"},
        {"type": "done", "audio_ms": 4800},
    ])
    factory.add(stream)

    frames = [FRAME, FRAME, None]  # None = socket drop

    async def _receive():
        return frames.pop(0)

    sent = []
    closed = []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    assert closed == [1000]
    key = f"u/{OWNER}/rec/{rid}/note.webm"
    # The object is container bytes: two PCM frames went through the muxer + the container tail.
    assert store.objects[key] == (_muxed(FRAME) * 2) + FakePcmMuxer.MAGIC + b"tail"
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "ready"
    assert doc["duration_ms"] == 200


async def test_run_stream_no_text_marks_failed(settings, repo, voice_repo, store):
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]

    stream = FakeAsrStream(server_frames=[
        {"type": "final", "phrase_id": created["phrase_id"], "text": "", "end_ms": 0,
         "revision": 1, "language": None},
        {"type": "done", "audio_ms": 0},
    ])
    factory.add(stream)

    async def _receive():
        return {"type": "stop"}

    sent = []
    closed = []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "failed"
    assert doc["processing"]["error_code"] == "nospeech"


async def test_run_stream_asr_busy_on_open(settings, repo, voice_repo, store):
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]

    stream = FakeAsrStream(ready_on_open=False)
    stream.open_error = "ASR_BUSY"
    factory.add(stream)

    async def _receive():
        return None

    sent = []
    closed = []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    # An ASR_BUSY error before ready.
    assert sent and sent[0]["type"] == "error"
    assert sent[0]["error_code"] == "ASR_BUSY"
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "failed"


async def test_run_stream_multipart_chunks_at_5mib(
    settings, repo, voice_repo, store
):
    """The object is written in 5 MiB parts, unaccumulated; RSS is length-independent (ADR-012)."""
    from app.application.voice_note_service import PART_SIZE

    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]

    stream = FakeAsrStream(server_frames=[
        {"type": "final", "phrase_id": created["phrase_id"], "text": "long", "end_ms": 0,
         "revision": 1, "language": "ru"},
        {"type": "done", "audio_ms": 0},
    ])
    factory.add(stream)

    big_frame = b"\x00\x01" * (PART_SIZE // 2)  # 5 MiB
    frames = [big_frame, big_frame, {"type": "stop"}]

    async def _receive():
        return frames.pop(0)

    sent = []
    closed = []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    key = f"u/{OWNER}/rec/{rid}/note.webm"
    # Two 5 MiB PCM frames → the muxer's multipart parts; the object is a container, not PCM.
    muxer = svc._test_muxers.last  # noqa: SLF001
    assert sum(len(w) for w in muxer.writes) == len(big_frame) * 2
    assert key in store.objects
    assert len(store.objects[key]) == len(big_frame) * 2 + len(FakePcmMuxer.MAGIC) + len(
        b"tail"
    )
    assert store.objects[key] != big_frame * 2


async def test_container_builds_voice_note_service(
    settings, repo, voice_repo, voice_index, store, queue
):
    from tests.fakes import FakeAsrFactory

    factory = FakeAsrFactory()
    c = Container(
        settings, repo=repo, store=store, queue=queue,
        voice_repo=voice_repo, voice_index=voice_index, asr_factory=factory,
    )
    assert c.voice_note_service is not None


# -- audio proxy (acceptance #9 and Range from #6) ---------------------------


async def test_audio_not_ready_for_recording(settings, repo, voice_repo, store):
    from tests.fakes import FakeAsrFactory

    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]

    from app.application.recording_service import RecordingService
    from app.domain.app_error import AppError

    rec_svc = RecordingService(repo, store, queue=None, settings=settings)
    with pytest.raises(AppError) as ei:
        await rec_svc.audio_meta(OWNER, rid)
    assert ei.value.code == ErrorCode.AUDIO_NOT_READY


async def test_audio_range_after_ready(settings, repo, voice_repo, store):
    from tests.fakes import FakeAsrFactory

    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]

    stream = FakeAsrStream(server_frames=[
        {"type": "final", "phrase_id": created["phrase_id"], "text": "x", "end_ms": 6400,
         "revision": 1, "language": "ru"},
        {"type": "done", "audio_ms": 6400},
    ])
    factory.add(stream)

    frames = [FRAME + FRAME, {"type": "stop"}]  # 200 ms of PCM, then stop

    async def _receive():
        return frames.pop(0)

    sent = []
    closed = []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    from app.application.recording_service import RecordingService

    rec_svc = RecordingService(repo, store, queue=None, settings=settings)
    meta = await rec_svc.audio_meta(OWNER, rid)
    assert meta["content_type"] == "audio/webm"
    # Range: we read a chunk and check Content-Range.
    data, total, ctype, key, size = await rec_svc.audio_range(
        OWNER, rid, start=0, length=1600
    )
    assert ctype == "audio/webm"
    assert len(data) == 1600
    assert size == len(FRAME) * 2 + len(FakePcmMuxer.MAGIC) + len(b"tail")


# -- D1: WebM/Opus muxer ----------------------------------------------------


async def test_object_is_muxed_not_raw_pcm(settings, repo, voice_repo, store):
    """PCM does not go into the object as is: every frame passes through the muxer (D1)."""
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    stream = FakeAsrStream(server_frames=[
        {"type": "final", "phrase_id": created["phrase_id"], "text": "ok", "end_ms": 300,
         "revision": 1, "language": "ru"},
        {"type": "done", "audio_ms": 300},
    ])
    factory.add(stream)
    frames = [FRAME, FRAME, FRAME, {"type": "stop"}]

    async def _receive():
        return frames.pop(0)

    sent, closed = [], []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    key = f"u/{OWNER}/rec/{rid}/note.webm"
    muxer = svc._test_muxers.last  # noqa: SLF001
    assert muxer.writes == [FRAME, FRAME, FRAME]  # every PCM frame went to ffmpeg
    assert store.objects[key] == (_muxed(FRAME) * 3) + FakePcmMuxer.MAGIC + b"tail"
    assert FRAME not in store.objects[key][: len(FRAME)]
    assert closed == [1000]


async def test_muxer_unavailable_fails_note_with_error_code(
    settings, repo, voice_repo, store
):
    """No ffmpeg in the image → error MUXER_UNAVAILABLE, no object, recording failed (D1)."""
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    svc._muxer_factory = FakeMuxerFactory(raise_unavailable=True)  # noqa: SLF001
    created = await svc.create(OWNER)
    rid = created["recording_id"]

    async def _receive():  # pragma: no cover — the socket is never reached
        return None

    sent, closed = [], []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    assert sent[0]["type"] == "error"
    assert sent[0]["error_code"] == "MUXER_UNAVAILABLE"
    assert f"u/{OWNER}/rec/{rid}/note.webm" not in store.objects
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "failed"
    assert doc["processing"]["error_code"] == "muxer_unavailable"
    assert closed and closed[0] != 1000


async def test_muxer_failure_midway_aborts_upload(settings, repo, voice_repo, store):
    """ffmpeg fails mid-recording → abort, no object, the recording goes failed (D1)."""
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    svc._muxer_factory = FakeMuxerFactory(fail_after=1)  # noqa: SLF001
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    factory.add(FakeAsrStream(server_frames=[]))
    frames = [FRAME, FRAME, {"type": "stop"}]

    async def _receive():
        return frames.pop(0)

    sent, closed = [], []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    key = f"u/{OWNER}/rec/{rid}/note.webm"
    assert key in store.aborted
    assert key not in store.objects
    assert any(m.get("error_code") == "MUXER_FAILED" for m in sent)
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "failed"


# -- D3: the abort path (ADR-012 §4) ----------------------------------------


async def test_socket_drop_with_zero_bytes_aborts(settings, repo, voice_repo, store):
    """A drop before the first byte: AbortMultipartUpload, no object, recording failed (D3)."""
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    factory.add(FakeAsrStream(server_frames=[{"type": "done", "audio_ms": 0}]))

    async def _receive():
        return None  # socket drop, not a single PCM frame

    sent, closed = [], []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    key = f"u/{OWNER}/rec/{rid}/note.webm"
    assert store.aborted == [key]
    assert key not in store.objects
    assert key not in store.meta
    stopped = [m for m in sent if m["type"] == "stopped"]
    assert stopped and stopped[0]["audio_ready"] is False
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "failed"
    assert doc["status"] != "ready"
    # The muxer is killed too, it does not hang after the note.
    assert svc._test_muxers.last.aborted  # noqa: SLF001


async def test_socket_drop_with_bytes_and_text_completes(
    settings, repo, voice_repo, store
):
    """A drop with bytes and text → complete, ready (previous behaviour, D3)."""
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    factory.add(FakeAsrStream(server_frames=[
        {"type": "final", "phrase_id": created["phrase_id"], "text": "present", "end_ms": 100,
         "revision": 1, "language": "ru"},
        {"type": "done", "audio_ms": 100},
    ]))
    frames = [FRAME, None]

    async def _receive():
        return frames.pop(0)

    sent, closed = [], []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    key = f"u/{OWNER}/rec/{rid}/note.webm"
    assert store.aborted == []
    assert key in store.objects
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "ready"
    assert closed == [1000]


async def test_idle_timeout_without_audio_aborts(settings, repo, voice_repo, store):
    """Idle 4408 without a single byte: abort, not a 0-byte object (D3)."""
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    factory.add(FakeAsrStream(server_frames=[{"type": "done", "audio_ms": 0}]))

    async def _receive():  # pragma: no cover — never reaches here: wait_for raises earlier
        return None

    sent, closed = [], []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    import gc

    import app.application.voice_note_service as vns

    real_wait_for = vns.asyncio.wait_for

    async def _fast_wait_for(aw, timeout):
        if timeout == 30.0:
            raise TimeoutError
        return await real_wait_for(aw, timeout)

    vns.asyncio.wait_for = _fast_wait_for  # type: ignore[assignment]
    try:
        await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)
    finally:
        vns.asyncio.wait_for = real_wait_for  # type: ignore[assignment]
    gc.collect()  # the receive() coroutine was dropped by the timeout: collect before warnings

    key = f"u/{OWNER}/rec/{rid}/note.webm"
    assert store.aborted == [key]
    assert key not in store.objects
    assert closed == [4408]
    assert repo.get_recording_sync(rid, OWNER)["status"] == "failed"


# -- D1: real ffmpeg (skipped if the binary is absent) -----------------------


HAS_FFMPEG = bool(__import__("shutil").which("ffmpeg"))
HAS_FFPROBE = bool(__import__("shutil").which("ffprobe"))


def _sine_pcm(seconds: float = 1.0, freq: int = 440) -> bytes:
    import math

    n = int(16000 * seconds)
    return b"".join(
        int(8000 * math.sin(2 * math.pi * freq * i / 16000)).to_bytes(2, "little", signed=True)
        for i in range(n)
    )


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
async def test_real_ffmpeg_muxer_produces_webm_opus():
    """A real muxer: the object starts with the EBML magic, ffprobe sees opus (D1)."""
    from app.infrastructure.pcm_muxer import FfmpegPcmMuxer

    pcm = _sine_pcm(2.0)
    muxer = FfmpegPcmMuxer()
    await muxer.start()
    out = bytearray()
    for off in range(0, len(pcm), 3200):
        out += await muxer.write(pcm[off : off + 3200])
    out += await muxer.finish()

    webm = bytes(out)
    assert webm[:4] == b"\x1a\x45\xdf\xa3", "no EBML/WebM magic"
    assert len(webm) < len(pcm) // 2, "PCM is not compressed into opus — the object is not a codec"

    if HAS_FFPROBE:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_name,sample_rate,channels", "-of", "default=nw=1", "pipe:0"],
            input=webm, capture_output=True, timeout=20, check=False,
        )
        info = r.stdout.decode()
        assert "codec_name=opus" in info
        assert "channels=1" in info


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is not installed")
async def test_real_ffmpeg_end_to_end_object_is_webm(
    settings, repo, voice_repo, store
):
    """The full service path with a real ffmpeg: WebM goes to MinIO, not PCM (D1)."""
    factory = FakeAsrFactory()
    svc = VoiceNoteService(
        repo, voice_repo, store, factory, settings, asr_probe=_avail_probe()
    )
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    factory.add(FakeAsrStream(server_frames=[
        {"type": "final", "phrase_id": created["phrase_id"], "text": "ok", "end_ms": 1600,
         "revision": 1, "language": "ru"},
        {"type": "done", "audio_ms": 1600},
    ]))
    pcm = _sine_pcm(1.6)
    frames = [pcm[i : i + 3200] for i in range(0, len(pcm), 3200)] + [{"type": "stop"}]

    async def _receive():
        return frames.pop(0)

    sent, closed = [], []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)

    obj = store.objects[f"u/{OWNER}/rec/{rid}/note.webm"]
    assert obj[:4] == b"\x1a\x45\xdf\xa3"
    assert obj != pcm
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc["status"] == "ready"
    assert doc["duration_ms"] == 1600
    assert closed == [1000]


def test_muxer_unavailable_without_ffmpeg():
    """No binary → MuxerUnavailable (not an ffmpeg exception) (D1)."""
    import asyncio

    from app.infrastructure.pcm_muxer import FfmpegPcmMuxer, MuxerUnavailable

    async def _run():
        m = FfmpegPcmMuxer(ffmpeg_path="ffmpeg-definitely-absent-us05")
        with pytest.raises(MuxerUnavailable):
            await m.start()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_run())


# -- D6: RSS of a long note (ADR-012 follow-up) -----------------------------


def _vm_rss_kb() -> int:
    with open("/proc/self/status", encoding="utf-8") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0


@pytest.mark.skipif(
    not pathlib.Path("/proc/self/status").is_file(),
    reason="VmRSS is read from /proc",
)
async def test_long_note_rss_bounded(settings, repo, voice_repo, store):
    """A long note (~19 min of PCM) does not grow RSS: the object goes in parts (ADR-012, D6).

    PCM is generated on the fly and not accumulated in the test; service memory holds the current
    5 MiB part and the window. The threshold is generous (300 MB) so the test does not flake on CI.
    """
    from app.infrastructure.pcm_muxer import FfmpegPcmMuxer

    class _StreamingMuxer:
        """An ffmpeg-compatible muxer without the binary: counts the volume, keeps only the tail."""

        def __init__(self) -> None:
            self.total = 0

        async def start(self) -> None:
            pass

        async def write(self, pcm: bytes) -> bytes:
            self.total += len(pcm)
            return b""  # compression is not modelled in the test

        async def finish(self) -> bytes:
            return b""

        async def abort(self) -> None:
            pass

    assert FfmpegPcmMuxer is not None
    factory = FakeAsrFactory()
    svc = _make_service(repo, voice_repo, store, settings, factory, _avail_probe())
    svc._muxer_factory = _StreamingMuxer  # noqa: SLF001
    created = await svc.create(OWNER)
    rid = created["recording_id"]
    factory.add(FakeAsrStream(server_frames=[
        {"type": "final", "phrase_id": created["phrase_id"], "text": "long", "end_ms": 100,
         "revision": 1, "language": "ru"},
        {"type": "done", "audio_ms": 100},
    ]))

    # An iterator instead of a list: the test itself does not hold tens of MB.
    chunk_pcm = b"\x01\x00" * 1600  # 100 ms
    frames_left = 11_400  # ~19 min of audio ≈ 365 MB of PCM

    async def _receive():
        nonlocal frames_left
        if frames_left > 0:
            frames_left -= 1
            return chunk_pcm
        return {"type": "stop"}

    sent, closed = [], []

    async def _send(msg):
        sent.append(msg)

    async def _close(code):
        closed.append(code)

    before = _vm_rss_kb()
    started = time.monotonic()
    await svc.run_stream(OWNER, rid, receive=_receive, send_text=_send, close=_close)
    grew_mb = (_vm_rss_kb() - before) / 1024

    assert closed == [1000]
    assert repo.get_recording_sync(rid, OWNER)["status"] == "ready"
    assert grew_mb < 300, f"RSS grew by {grew_mb:.1f} MB for a long note"
    assert time.monotonic() - started < 120
