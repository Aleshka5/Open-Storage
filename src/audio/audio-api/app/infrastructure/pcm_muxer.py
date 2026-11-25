"""Mux PCM s16le 16 kHz mono → WebM/Opus on the fly (ADR-012 §6).

The note codec is fixed: `audio/webm` (Opus). The browser plays it without transcoding,
and the size on disk is an order of magnitude smaller than WAV. The container is assembled by an
ffmpeg subprocess as recording goes: PCM goes to `stdin`, ready WebM bytes come from `stdout` and
straight into the MinIO multipart upload — neither PCM nor WebM ever lives in memory whole.

A missing ffmpeg is no reason to write "webm" out of raw PCM (that would be a silently corrupt
object): `MuxerUnavailable` aborts the note with `error_code` `MUXER_UNAVAILABLE`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import select
import shutil
from collections.abc import Callable
from typing import Protocol

logger = logging.getLogger(__name__)

# PCM s16le 16 kHz mono on input; Opus in WebM at 32 kbit/s (speech, a note).
FFMPEG_INPUT_ARGS: tuple[str, ...] = (
    "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", "pipe:0"
)
FFMPEG_OUTPUT_ARGS: tuple[str, ...] = (
    "-c:a", "libopus", "-b:a", "32k", "-f", "webm", "pipe:1"
)

# How long to wait for ffmpeg to close at the end (flush of the last frames).
MUXER_FLUSH_TIMEOUT_S = 15.0
_READ_CHUNK = 65536


class MuxerUnavailable(RuntimeError):
    """ffmpeg is unavailable (no binary/package in the image) — nothing to record the note with."""

    error_code = "MUXER_UNAVAILABLE"


class MuxerError(RuntimeError):
    """ffmpeg exited with an error mid-recording — the object is unusable."""

    error_code = "MUXER_FAILED"


class PcmMuxer(Protocol):
    """Streaming muxer: PCM in, container bytes out (contract, not implementation)."""

    async def start(self) -> None:
        """Starts the muxer; no tool — `MuxerUnavailable`."""

    async def write(self, pcm: bytes) -> bytes:
        """Takes a chunk of PCM, returns ready container bytes (may be empty)."""

    async def finish(self) -> bytes:
        """Finishes the stream and returns the container tail; an error — `MuxerError`."""

    async def abort(self) -> None:
        """Stops the muxer abruptly without waiting for a clean `finish`."""


class FfmpegPcmMuxer:
    """One ffmpeg subprocess per session: `-i pipe:0` (PCM) → `-f webm pipe:1`.

    The pipes are our own (`os.pipe`), not `create_subprocess_exec(PIPE)`: stdout is needed as an fd
    non-blocking reads — a StreamReader waits for EOF/limit and would block the write.
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        self._ffmpeg_path = ffmpeg_path
        self._proc: asyncio.subprocess.Process | None = None
        self._pcm_w: int = -1
        self._webm_r: int = -1
        self._pending = bytearray()
        self._finished = False

    @staticmethod
    def available(ffmpeg_path: str = "ffmpeg") -> bool:
        return shutil.which(ffmpeg_path) is not None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if not self.available(self._ffmpeg_path):
            raise MuxerUnavailable("ffmpeg not found in the audio-api image")
        try:
            pcm_r, self._pcm_w = os.pipe()
            self._webm_r, webm_w = os.pipe()
        except OSError as exc:  # pragma: no cover — no fd
            raise MuxerUnavailable("could not create pipes") from exc
        os.set_blocking(self._webm_r, False)
        try:
            self._proc = await asyncio.create_subprocess_exec(
                self._ffmpeg_path,
                "-hide_banner",
                "-loglevel", "error",
                "-nostdin",
                *FFMPEG_INPUT_ARGS,
                *FFMPEG_OUTPUT_ARGS,
                stdin=pcm_r,
                stdout=webm_w,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            for fd in (pcm_r, self._pcm_w, self._webm_r, webm_w):
                _close_fd(fd)
            raise MuxerUnavailable("ffmpeg does not start") from exc
        finally:
            # Close the copies in the parent: ffmpeg sees EOF once we close our end.
            _close_fd(pcm_r)
            _close_fd(webm_w)

    def _read_available(self) -> bytes:
        """Takes everything ffmpeg has already produced without waiting for new data."""
        out = bytearray()
        while True:
            try:
                chunk = os.read(self._webm_r, _READ_CHUNK)
            except BlockingIOError:
                break
            except OSError as exc:  # pragma: no cover — the channel closed
                logger.warning("muxer_stdout_error error=%s", type(exc).__name__)
                break
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < _READ_CHUNK:
                break
        return bytes(out)

    def _write_all(self, pcm: bytes) -> None:
        """Writes PCM to ffmpeg stdin, waiting for room; reads its stdout in parallel."""
        view = memoryview(pcm)
        while view:
            try:
                n = os.write(self._pcm_w, view)
            except BlockingIOError:
                # Deadlock is ruled out: while waiting for write room we drain stdout.
                self._pending.extend(self._read_available())
                select.select([], [self._pcm_w], [], 0.05)
                continue
            except (BrokenPipeError, OSError) as exc:
                raise MuxerError("ffmpeg closed stdin") from exc
            view = view[n:]
            self._pending.extend(self._read_available())

    async def write(self, pcm: bytes) -> bytes:
        if self._proc is None or self._finished:
            raise MuxerUnavailable("muxer is not running")
        if not pcm:
            return b""
        await asyncio.to_thread(self._write_all, pcm)
        out = bytes(self._pending) + self._read_available()
        self._pending.clear()
        return out

    async def finish(self) -> bytes:
        if self._proc is None:
            raise MuxerUnavailable("muxer is not running")
        if self._finished:
            return b""
        self._finished = True
        _close_fd(self._pcm_w)
        self._pcm_w = -1
        loop = asyncio.get_running_loop()
        deadline = loop.time() + MUXER_FLUSH_TIMEOUT_S
        rest = bytearray(self._pending)
        self._pending.clear()
        while True:
            chunk = self._read_available()
            if chunk:
                rest.extend(chunk)
                continue
            if self._proc.returncode is not None:
                # The process exited and the channel gave EOF: the WebM tail has been read whole.
                break
            if loop.time() >= deadline:
                self._proc.kill()
                await self._reap()
                _close_fd(self._webm_r)
                self._webm_r = -1
                raise MuxerError("ffmpeg did not finish within the timeout")
            # Wait for data/EOF on the non-blocking fd (select in a thread, not in the loop).
            await asyncio.to_thread(select.select, [self._webm_r], [], [], 0.02)
        code = await self._reap()
        _close_fd(self._webm_r)
        self._webm_r = -1
        if code != 0:
            logger.warning("muxer_ffmpeg_failed code=%s", code)
            raise MuxerError(f"ffmpeg exit {code}")
        return bytes(rest)

    async def _reap(self) -> int | None:
        """Waits for ffmpeg to exit; kills a stubborn process."""
        assert self._proc is not None
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except TimeoutError:  # pragma: no cover
            self._proc.kill()
            await self._proc.wait()
        return self._proc.returncode

    async def abort(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except TimeoutError:  # pragma: no cover
                pass
        _close_fd(self._pcm_w)
        _close_fd(self._webm_r)
        self._pcm_w = -1
        self._webm_r = -1


def _close_fd(fd: int) -> None:
    if fd is None or fd < 0:
        return
    try:
        os.close(fd)
    except OSError:  # pragma: no cover
        pass


def default_muxer_factory(ffmpeg_path: str = "ffmpeg") -> Callable[[], PcmMuxer]:
    """Muxer factory with a fixed ffmpeg path (for settings and tests)."""

    def _make() -> PcmMuxer:
        return FfmpegPcmMuxer(ffmpeg_path)

    return _make
